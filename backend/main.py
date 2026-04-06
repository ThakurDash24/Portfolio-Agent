"""
FastAPI server for the chat agent. Run with: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import os
import uuid
import base64
import traceback
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import uuid

load_dotenv()

from app import BasicAgent
from tools import init_pdf_vectorstore

_BACKEND_DIR = Path(__file__).resolve().parent
_UPLOADS_DIR = _BACKEND_DIR / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Agent API", version="1.0.0")

_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session storage: thread_id -> {"agent": BasicAgent, "title": str, "saved": bool}
_sessions: Dict[str, Dict] = {}

# ---------------------------------------------------------------------------
# Supabase-backed session persistence
# ---------------------------------------------------------------------------
try:
    from supabase_client import supabase as _sb
    _SUPABASE_ENABLED = True
except Exception as _sb_err:
    print(f"[WARNING] Supabase not available: {_sb_err}")
    _SUPABASE_ENABLED = False


def save_sessions_to_db():
    """Upsert saved sessions → chat_threads + chat_messages."""
    if not _SUPABASE_ENABLED:
        return
    import json as _json

    for tid, s in _sessions.items():
        if not (s.get("saved", False) or s["agent"].is_saved):
            continue

        # 1. Upsert the thread row
        try:
            _sb.table("chat_threads").upsert({
                "id": tid,
                "title": s["title"],
                "is_saved": True,
            }).execute()
        except Exception as e:
            print(f"[Supabase] chat_threads upsert failed for {tid}: {e}")
            continue

        # 2. Replace messages – delete old rows then insert fresh
        messages = s["agent"].threads.get(tid, {}).get("messages", [])
        try:
            _sb.table("chat_messages").delete().eq("thread_id", tid).execute()
        except Exception as e:
            print(f"[Supabase] chat_messages delete failed for {tid}: {e}")

        rows = []
        for m in messages:
            if not isinstance(m, dict):
                m = {"role": "assistant", "content": str(m)}
            role = m.get("role", "assistant")
            # content can be list (multimodal) or str
            content = m.get("content", "")
            if isinstance(content, list):
                # flatten multimodal list → text only for DB storage
                content = " ".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            rows.append({
                "thread_id": tid,
                "role": role,
                "content": str(content),
                "reasoning_trace": m.get("reasoning_trace", None),
            })

        if rows:
            try:
                _sb.table("chat_messages").insert(rows).execute()
            except Exception as e:
                print(f"[Supabase] chat_messages insert failed for {tid}: {e}")


def load_sessions_from_db():
    """Restore saved sessions from Supabase on startup."""
    if not _SUPABASE_ENABLED:
        return

    try:
        threads_res = _sb.table("chat_threads").select("*").eq("is_saved", True).execute()
    except Exception as e:
        print(f"[Supabase] Failed to load threads: {e}")
        return

    for row in (threads_res.data or []):
        tid = row["id"]

        # Load messages for this thread
        try:
            msgs_res = _sb.table("chat_messages").select("*").eq("thread_id", tid).order("created_at").execute()
            raw_messages = msgs_res.data or []
        except Exception as e:
            print(f"[Supabase] Failed to load messages for {tid}: {e}")
            raw_messages = []

        agent = BasicAgent()
        agent.threads[tid] = {"messages": [], "title": row.get("title", "Chat")}
        for m in raw_messages:
            agent.threads[tid]["messages"].append({
                "role": m.get("role", "assistant"),
                "content": m.get("content", ""),
            })

        _sessions[tid] = {
            "agent": agent,
            "title": row.get("title", "Chat"),
            "saved": True,
        }
        agent.current_thread_id = tid
        agent.is_saved = True

        # Step 4.2 — Restore vector DB from documents table if PDF was previously uploaded
        try:
            docs_res = _sb.table("documents").select("metadata").eq("thread_id", tid).limit(1).execute()
            if docs_res.data:
                file_url = docs_res.data[0]["metadata"]["file_url"]
                print(f"[Supabase] Restoring PDF vector DB for thread {tid} from {file_url}")
                from tools import init_pdf_vectorstore
                agent.vector_db = init_pdf_vectorstore(file_url)
                agent.has_pdf = True
        except Exception as e:
            print(f"[Supabase] Document load/restore failed for {tid}: {e}")

    print(f"[Supabase] Loaded {len(threads_res.data or [])} saved thread(s) from DB.")


# Backwards-compat alias so existing call sites keep working
def save_sessions_to_disk():
    save_sessions_to_db()


# Load on startup
load_sessions_from_db()

def get_session(thread_id: str):
    # Initialize basic data retrievers if not done yet
    from tools import init_retriever, bm25_retriever
    if bm25_retriever is None:
        try:
            # Fallback data if file is missing/broken
            guest_data = [
                "Biswajit: A fellow developer and friend of Laven.",
                "Laven: The owner of this portfolio and a highly capable AI builder.",
                "Thakur Dash: A Machine Learning Engineer with experience in GenAI and backend systems."
            ]
            # Try to load from all_models.json
            import json
            if os.path.exists("all_models.json"):
                try:
                    with open("all_models.json", "r") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            guest_data = data
                except:
                    pass
            
            from langchain_core.documents import Document
            docs = [Document(page_content=d) for d in guest_data]
            init_retriever(docs)
            print("Guest retriever initialized successfully.")
        except Exception as e:
            print(f"Failed to initialize guest retriever: {e}")

    if thread_id not in _sessions:
        _sessions[thread_id] = {
            "agent": BasicAgent(),  # NEW agent per thread
            "title": "New Chat",
            "saved": False
        }
        # Force a clean start for this agent's internal state
        _sessions[thread_id]["agent"].create_thread(thread_id)
    return _sessions[thread_id]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    thread_id: Optional[str] = None
    images: Optional[List[str]] = None


class ChatResponse(BaseModel):
    response: str
    reasoning_trace: Optional[str] = None
    thread_id: str
    title: str
    saved: bool = False
    has_pdf: bool = False
    has_image: bool = False


class PdfUploadResponse(BaseModel):
    message: str
    filename: str
    has_pdf: bool = True


class ImageUploadResponse(BaseModel):
    message: str
    filename: str
    has_image: bool = True
    analysis: Optional[str] = None

class WebSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")

class WebSearchResponse(BaseModel):
    results: Optional[dict] = None
    message: str

class ThreadItem(BaseModel):
    id: str
    title: str

class ThreadTitleUpdate(BaseModel):
    title: str


@app.get("/")
def root():
    return {"message": "Agent API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/upload/image", response_model=ImageUploadResponse)
async def upload_image(file: UploadFile = File(...)):
    """Upload image to Supabase Storage and return public URL."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    try:
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Empty file")

        # Step 3.2 — Upload to Supabase Storage
        from storage import upload_file
        res = upload_file(contents, file.filename, file.content_type)

        if not res:
            raise HTTPException(status_code=500, detail="Storage upload failed")

        file_url = res["url"]
        analysis = f"Image '{file.filename}' uploaded successfully. URL: {file_url}"

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return ImageUploadResponse(
        message="Image uploaded to Supabase Storage",
        filename=file.filename,
        has_image=True,
        analysis=analysis
    )


@app.post("/upload/pdf", response_model=PdfUploadResponse)
async def upload_pdf(thread_id: str, file: UploadFile = File(...)):
    """Upload PDF to Supabase Storage and index it for the specific session's agent."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    try:
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Empty file")

        session = get_session(thread_id)

        # 🔹 STRICT CONSTRAINT: Only 1 PDF per thread
        if session["agent"].vector_db is not None or getattr(session["agent"], 'has_pdf', False):
            return PdfUploadResponse(
                message="i am a under testing small agent , can't handle much ..",
                filename=file.filename,
                has_pdf=True
            )

        # Step 4.3 — Hard DB duplicate check before proceeding
        if _SUPABASE_ENABLED:
            try:
                existing = _sb.table("documents").select("id").eq("thread_id", thread_id).execute()
                if existing.data:
                    return PdfUploadResponse(
                        message="i am a under testing small agent , can't handle much ..",
                        filename=file.filename,
                        has_pdf=True
                    )
            except Exception as e:
                print(f"[Supabase] Duplicate PDF check failed: {e}")

        session["agent"].has_pdf = True

        # Step 3.3 — Upload to Supabase Storage
        from storage import upload_file
        res = upload_file(contents, file.filename, "application/pdf")

        if not res:
            raise HTTPException(status_code=500, detail="PDF Storage upload failed")

        file_url = res["url"]
        print(f"RESETTING PDF MEMORY for thread: {thread_id}")
        session["agent"].vector_db = None

        # Step 4.1 — Insert document metadata into documents table
        if _SUPABASE_ENABLED:
            try:
                _sb.table("documents").insert({
                    "thread_id": thread_id,
                    "content": None,
                    "metadata": {
                        "file_url": file_url,
                        "filename": file.filename,
                    },
                    "embedding": None,
                }).execute()
                print(f"[Supabase] Document record created for thread {thread_id}")
            except Exception as e:
                print(f"[Supabase] Document insert failed: {e}")

        # Step 3.4 — Pass public URL directly to vectorstore (PyPDFLoader supports HTTP URLs)
        from tools import init_pdf_vectorstore
        db = init_pdf_vectorstore(file_url)

        session["agent"].vector_db = db
        result = f"PDF '{file.filename}' indexed for this session."

    except HTTPException:
        raise
    except ValueError as e:
        print(f"VAL ERROR in UPLOAD_PDF: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"ERROR IN UPLOAD_PDF: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e)) from e

    return PdfUploadResponse(
        message=result,
        filename=file.filename,
    )


@app.post("/websearch", response_model=WebSearchResponse)
def web_search(req: WebSearchRequest):
    """Perform web search using ddg search tool."""
    try:
        # Import ddg search function from tools
        from tools import search_tool
        
        # Perform the search
        search_results = search_tool(req.query)
        
        return WebSearchResponse(
            results=search_results,
            message=f"Search completed for '{req.query}'"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/threads", response_model=List[ThreadItem])
def list_threads():
    # Priority: agent.is_saved or session cache
    return [
        ThreadItem(id=tid, title=s["title"]) 
        for tid, s in _sessions.items() 
        if s.get("saved", False) or s["agent"].is_saved
    ]

@app.post("/threads/new")
def new_thread():
    from datetime import datetime, timezone
    tid = uuid.uuid4().hex
    _sessions[tid] = {
        "agent": BasicAgent(),
        "title": "New Chat",
        "saved": False
    }
    # Initialize the agent's internal thread as well
    _sessions[tid]["agent"].create_thread(tid)

    # Step 2.1 — Insert thread row into DB immediately
    if _SUPABASE_ENABLED:
        try:
            _sb.table("chat_threads").insert({
                "id": tid,
                "title": "New Chat",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "is_saved": False,
            }).execute()
        except Exception as e:
            print(f"[Supabase] Thread insert failed: {e}")

    return {"thread_id": tid}


@app.get("/thread/{thread_id}")
def get_thread(thread_id: str):
    if thread_id not in _sessions:
        raise HTTPException(status_code=404, detail="Sorry but you forgot to save it , :) ")

    session = _sessions[thread_id]
    agent = session["agent"]

    return {
        "thread_id": thread_id,
        "title": session["title"],
        "messages": agent.get_historical_messages(),
        "saved": session.get("saved", False) or agent.is_saved,
        "has_pdf": agent.has_pdf,
        "has_image": agent.has_image
    }


@app.post("/save_thread/{thread_id}")
def save_thread(thread_id: str):
    if thread_id not in _sessions:
        raise HTTPException(status_code=404, detail="Sorry but you forgot to save it , :) ")
    _sessions[thread_id]["saved"] = True
    _sessions[thread_id]["agent"].is_saved = True

    # Step 2.3 — Sync saved flag instantly to DB
    if _SUPABASE_ENABLED:
        try:
            _sb.table("chat_threads").update({"is_saved": True}).eq("id", thread_id).execute()
        except Exception as e:
            print(f"[Supabase] Save flag update failed: {e}")

    save_sessions_to_db()  # also sync messages
    return {"message": "Thread saved"}

@app.delete("/threads/{thread_id}")
def delete_thread(thread_id: str):
    if thread_id in _sessions:
        del _sessions[thread_id]

    # Step 2.4 — Cascade delete from DB
    if _SUPABASE_ENABLED:
        try:
            _sb.table("chat_messages").delete().eq("thread_id", thread_id).execute()
            _sb.table("chat_threads").delete().eq("id", thread_id).execute()
        except Exception as e:
            print(f"[Supabase] Delete failed for {thread_id}: {e}")

    return {"message": "Thread deleted"}

@app.put("/threads/{thread_id}/title")
def update_thread_title(thread_id: str, payload: ThreadTitleUpdate):
    if thread_id not in _sessions:
        raise HTTPException(status_code=404, detail="Thread not found")
    _sessions[thread_id]["title"] = payload.title

    # Step 2.2 — Update title directly in DB
    if _SUPABASE_ENABLED:
        try:
            _sb.table("chat_threads").update({"title": payload.title}).eq("id", thread_id).execute()
        except Exception as e:
            print(f"[Supabase] Title update failed: {e}")

    return {"message": "Title updated"}

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    text = req.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="message is required")
    
    if not req.thread_id:
        raise HTTPException(status_code=400, detail="thread_id required")
    
    thread_id = req.thread_id
    session = get_session(thread_id)
    agent = session["agent"]
    
    # 🔹 Bind agent to thread_id
    agent.switch_thread(thread_id)
    
    print(f"THREAD: {thread_id}")
    # BasicAgent uses threads[thread_id]['messages']
    messages_count = len(agent.get_current_messages())
    print(f"MEMORY SIZE: {messages_count}")
    
    # 🔹 STRICT CONSTRAINT: Check Multi-photo restrictions
    if req.images and len(req.images) > 0:
        if getattr(agent, 'has_image', False) or len(req.images) > 1:
            return ChatResponse(
                response="i am a under testing small agent , can't handle much ..",
                reasoning_trace="Upload blocked: Multiple images requested.",
                thread_id=thread_id,
                title=session.get("title", "Chat"),
                saved=agent.is_saved
            )
        agent.has_image = True

    try:
        # Standard async/await not used here because agent call is synchronous
        # but we use async def because it's good practice for non-blocking if we add more
        response, reasoning_trace = agent(text, images=req.images)
        
        # Smart Title Generation if it's the first message
        if session["title"] == "New Chat":
            try:
                # Ask the agent to summarize the topic in 3-5 words
                summary_prompt = f"Summarize this initial message in exactly 3-5 words for a chat title: '{text}'. Format: Just the title, no extra text."
                # Use a temp agent to avoid memory pollution in the main session
                temp_agent = BasicAgent()
                temp_agent.switch_thread("title_gen_temp")
                title_res, _ = temp_agent(summary_prompt)
                session["title"] = title_res.split('\n')[0].strip(' "')[:50]
            except Exception as e:
                print(f"Title generation error: {e}")
                session["title"] = text[:30] + "..." if len(text) > 30 else text

        # Persist if either explicitly saved or agent triggered auto-save
        if session["saved"] or agent.is_saved:
            save_sessions_to_disk()

        return ChatResponse(
            response=response, 
            reasoning_trace=reasoning_trace,
            thread_id=thread_id,
            title=session["title"],
            saved=session.get("saved", False) or agent.is_saved,
            has_pdf=agent.has_pdf,
            has_image=agent.has_image
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
