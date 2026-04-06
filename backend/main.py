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
_SESSIONS_FILE = _BACKEND_DIR / "sessions.json"

def save_sessions_to_disk():
    """Serialize all saved sessions to a JSON file."""
    data_to_save = {}
    for tid, s in _sessions.items():
        if s.get("saved", False) or s["agent"].is_saved:
            # We only persist sessions that have been explicitly 'saved'
            data_to_save[tid] = {
                "title": s["title"],
                "saved": True,
                "history": s["agent"].threads.get(tid, {}).get("messages", []),
                "has_pdf": getattr(s["agent"], 'has_pdf', False),
                "has_image": getattr(s["agent"], 'has_image', False)
            }
    
    with open(_SESSIONS_FILE, "w", encoding="utf-8") as f:
        import json
        # Since history might contain LangChain objects, we need a custom serializer or just to_dict
        json.dump(data_to_save, f, default=str)

def load_sessions_from_disk():
    """Restore sessions from the JSON file."""
    if not _SESSIONS_FILE.exists():
        return
        
    try:
        with open(_SESSIONS_FILE, "r", encoding="utf-8") as f:
            import json
            data = json.load(f)
            
        for tid, s_data in data.items():
            agent = BasicAgent()
            agent.threads[tid] = {
                "messages": [], # We store original types as strings above, might be tricky to restore perfectly
                "title": s_data["title"]
            }
            # Add historical messages (will be strings if we used default=str, but better than nothing)
            # Actually, to be better, we'll just try to restore role/content
            for m in s_data.get("history", []):
                # If m was a LangChain object, it's now a string like "AIMessage(content='...')"
                # If it's a dict, we keep it. 
                # For this demo, we'll try to keep it simple.
                if isinstance(m, dict):
                    agent.threads[tid]["messages"].append(m)
                else:
                    # Simple heuristic: try to find role/content in the string representation
                    agent.threads[tid]["messages"].append({"role": "assistant", "content": str(m)})
            
            _sessions[tid] = {
                "agent": agent,
                "title": s_data["title"],
                "saved": True
            }
            agent.current_thread_id = tid
            agent.has_pdf = s_data.get("has_pdf", False)
            agent.has_image = s_data.get("has_image", False)
    except Exception as e:
        print(f"Error loading sessions: {e}")

# Call load on startup
load_sessions_from_disk()

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
    """Process an uploaded image for vision analysis."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    dest_name = f"{uuid.uuid4().hex}_{Path(file.filename).name}"
    dest_path = _UPLOADS_DIR / dest_name

    try:
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Empty file")
        
        # Save the image
        dest_path.write_bytes(contents)
        
        # For now, we'll just acknowledge the upload
        # In a real implementation, you could add vision analysis here
        analysis = f"Image '{file.filename}' uploaded successfully. The image has been processed and is ready for analysis."
        
    except HTTPException:
        raise
    except Exception as e:
        if dest_path.exists():
            try:
                dest_path.unlink()
            except OSError:
                pass
        raise HTTPException(status_code=500, detail=str(e)) from e

    # Tie image to thread if provided
    if thread_id:
        session = get_session(thread_id)
        session["agent"].has_image = True

    return ImageUploadResponse(
        message="Image uploaded and processed successfully",
        filename=file.filename,
        has_image=True,
        analysis=analysis
    )


@app.post("/upload/pdf", response_model=PdfUploadResponse)
async def upload_pdf(thread_id: str, file: UploadFile = File(...)):
    """Save an uploaded PDF and index it for the specific session's agent."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    dest_name = f"{uuid.uuid4().hex}_{Path(file.filename).name}"
    dest_path = _UPLOADS_DIR / dest_name

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
            
        session["agent"].has_pdf = True
        dest_path.write_bytes(contents)
        
        print(f"RESETTING PDF MEMORY for thread: {thread_id}")
        session["agent"].vector_db = None 

        # Initialize vectorstore and store in the session agent
        from tools import init_pdf_vectorstore
        db = init_pdf_vectorstore(str(dest_path))
        
        session["agent"].vector_db = db
        
        result = f"PDF '{file.filename}' indexed for this session."
    except HTTPException:
        raise
    except ValueError as e:
        print(f"VAL ERROR in UPLOAD_PDF: {e}")
        if dest_path.exists():
            try:
                dest_path.unlink()
            except OSError:
                pass
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"ERROR IN UPLOAD_PDF: {e}")
        traceback.print_exc()
        if dest_path.exists():
            try:
                dest_path.unlink()
            except OSError:
                pass
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
    tid = uuid.uuid4().hex
    _sessions[tid] = {
        "agent": BasicAgent(),
        "title": "New Chat",
        "saved": False
    }
    # Initialize the agent's internal thread as well
    _sessions[tid]["agent"].create_thread(tid)
    # We don't save to disk yet, only when 'saved' is True
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
    save_sessions_to_disk() # 👈 Persist
    return {"message": "Thread saved"}

@app.delete("/threads/{thread_id}")
def delete_thread(thread_id: str):
    if thread_id in _sessions:
        del _sessions[thread_id]
        save_sessions_to_disk()
    return {"message": "Thread deleted"}

@app.put("/threads/{thread_id}/title")
def update_thread_title(thread_id: str, payload: ThreadTitleUpdate):
    if thread_id not in _sessions:
        raise HTTPException(status_code=404, detail="Thread not found")
    _sessions[thread_id]["title"] = payload.title
    save_sessions_to_disk()
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
