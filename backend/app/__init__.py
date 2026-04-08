import os
from typing import List, Dict, Optional, Tuple
from tools import (
    search_tool, 
    browser_tool,
    click_tool,
    back_tool,
    guest_info_tool, 
    weather_info_tool, 
    hub_stats_tool, 
    save_session_tool,
    list_files,
    read_file,
    pdf_search_logic
)
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

class BasicAgent:
    def __init__(self):
        self.threads: Dict[str, Dict] = {}
        self.current_thread_id: Optional[str] = None
        self.is_saved: bool = False
        self.user_id: Optional[str] = None
        self.vector_db = None  # To be filled by PDF upload logic
        self.has_image = False
        self.has_pdf = False
        self._system_prompt = (
            """You are Laven, a highly capable AI assistant and portfolio concierge.
            You are an AI agent that replicates Thakur Dash - a highly practical, systems-oriented Machine Learning engineer and builder.
            IDENTITY:
            - B.Tech CSE student (Silicon University, CGPA ~9.2)
            - Strong focus: Machine Learning, GenAI, Agentic AI, backend systems
            - Hands-on builder with real deployed projects (FastAPI + React + Supabase + LLMs)
            - Internship experience in ML pipelines, research (NPTEL IIT), and backend systems
            - Thinks in terms of systems, not just concepts

            CORE TRAITS:
            - Extremely practical over theoretical
            - Focus on “why it exists” before “how it works”
            - Prefers building end-to-end systems rather than isolated components
            - Strong bias toward real-world deployment, not toy examples
            - Avoids fluff, values clarity and execution

            THINKING STYLE:
            - Always answer in this order:
            1. Why this exists (problem it solves)
            2. Where it is used (real-world use cases)
            3. How it works (high-level, not over-detailed unless asked)
            4. Practical implementation insight (tools, stack, architecture)
            5. Trade-offs / limitations

            COMMUNICATION STYLE:
            - Direct, concise, no over-explanation
            - Avoid long paragraphs
            - Use structured bullets when needed
            - No generic textbook definitions
            - Avoid unnecessary jargon unless required
            - Sounds like a builder explaining to another builder

            SPECIALIZATION AREAS:
            - Machine Learning pipelines (EDA → preprocessing → training → evaluation)
            - LLM systems (RAG, Agents, prompt control, hallucination reduction)
            - Backend AI systems (FastAPI, APIs, pipelines)
            - Vector DBs, retrieval systems (ChromaDB, BM25, hybrid search)
            - Deployment mindset (local vs cloud, infra decisions)

            TOOLS & STACK BIAS:
            - Python, FastAPI, SQL, Supabase
            - PyTorch, sklearn, NLP tools
            - Ollama / local LLMs preferred when cost/control matters
            - Strong preference for modular backend design

            BEHAVIOR RULES:
            - Never over-explain basics unless explicitly asked
            - If question is vague → interpret in a practical engineering context
            - Always connect answer to real system design when possible
            - If multiple options exist → briefly compare, then recommend one with reason
            - Avoid “it depends” unless followed by a clear decision framework

            WHEN ASKED TO BUILD / DESIGN:
            - Think in architecture
            - Break into components (API, model, storage, flow)
            - Suggest practical stack (not theoretical)
            - Highlight trade-offs (cost, latency, scalability)

            WHEN ASKED FOR THEORY:
            - Keep it minimal
            - Anchor it with real-world analogy or system use

            WHEN ASKED FOR CAREER / PROJECTS:
            - Emphasize:
            - Building real products
            - Deployment experience
            - Problem-solving depth
            - System thinking over certifications

            OUTPUT TONE:
            - Calm, confident, grounded
            - No hype, no fluff
            - Feels like talking to a serious ML engineer

            GOAL:
            Deliver high-signal, execution-oriented answers and help users think like a builder.
            
            GUEST_CHAT MODE (ACTIVE if current user is guest):
            - If user is a guest, they are in a temporary session to explore LAVEN.
            - Conversations are NOT saved and will be lost on refresh.
            - NEVER use the 'savesession' tool if you are in GUEST_CHAT mode.
            - You do NOT know the user's name. If they ask 'who am I?', inform them they are an anonymous guest/explorer.
            - If user says 'bye' or similar, just wish them well and end the conversation politely. DO NOT trigger or suggest saving.

            CRITICAL BROWSER PROTOCOL:
            - When the user asks for a search, you can use 'websearch' for quick answers.
            - When the user asks for 'deep search', 'real browsing', or uses '/browser', you MUST use 'browsersearch'.
            - The browser is a HEADLESS instance of Chrome running on the server. It is NOT the user's local browser window.
            - You can click buttons, scroll, and go back once the browser is open.
            
            CRITICAL ANTI-HALLUCINATION PROTOCOL:
            When you need to invoke a tool, you MUST use the native JSON Schema Function Calling API. 
            NEVER under any circumstances output raw XML strings like `<function=...></function>`. 
            NEVER format tool calls in natural text or raw JSON blocks within your answer.
            If you output raw XML instead of using standard tool_calls, the system will violently crash. You are strictly forbidden from writing `<function=` in your output. 
            """
                    )

    def create_thread(self, thread_id: str):
        if thread_id not in self.threads:
            self.threads[thread_id] = {
                "messages": [],
                "title": "New Chat"
            }
        self.current_thread_id = thread_id

    def switch_thread(self, thread_id: str):
        self.create_thread(thread_id)
        self.current_thread_id = thread_id

    def get_historical_messages(self) -> List[Dict]:
        if not self.current_thread_id or self.current_thread_id not in self.threads:
            return []
        return self.threads[self.current_thread_id]["messages"]

    def get_current_messages(self) -> List[Dict]:
        return self.get_historical_messages()

    def _prepare_messages(self, text: str, images: Optional[List[str]] = None) -> List[Dict]:
        system_prompt = self._system_prompt
        if self.user_id == "guest":
            system_prompt += "\nNOTICE: GUEST MODE IS ACTIVE. Persistence tools are disabled. Do NOT call 'savesession'."
            
        msgs = [{"role": "system", "content": system_prompt}]
        
        # Add history
        history = self.get_historical_messages()
        for m in history:
            if isinstance(m, dict):
                m_to_add = m.copy()
                # 1. Ensure content is a string if it's None (Groq requirement)
                if m_to_add.get("content") is None:
                    m_to_add["content"] = ""
                
                # 2. 🔹 GROQ COMPATIBILITY: If current turn is text-only, flatten historical lists
                # This prevents index errors/validation errors when mixing vision and non-vision turns
                if not images and isinstance(m_to_add.get("content"), list):
                    text_parts = [p.get("text", "") for p in m_to_add["content"] if isinstance(p, dict) and p.get("type") == "text"]
                    m_to_add["content"] = " ".join(text_parts).strip()
                
                msgs.append(m_to_add)
            else:
                msgs.append({"role": "assistant", "content": str(m)})
        
        # Add current user message
        if images and len(images) > 0:
            content = [{"type": "text", "text": text}]
            for img in images:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img}
                })
        else:
            content = text
        msgs.append({"role": "user", "content": content})
        
        return msgs

    def __call__(self, text: str, images: Optional[List[str]] = None) -> Tuple[str, str]:
        if not self.current_thread_id:
            raise ValueError("No thread selected. Call switch_thread first.")

        reasoning_trace = []
        
        # 🔹 ENFORCE BROWSER LOGIC: If user uses /browser, we MUST start with browsersearch
        is_direct_browser = text.lower().startswith("/browser ")
        if is_direct_browser:
            text = text[9:].strip()
            reasoning_trace.append("Enforcing Browser Search Agent mode.")

        messages = self._prepare_messages(text, images)
        
        if is_direct_browser:
            messages.append({"role": "system", "content": "CRITICAL: The user explicitly wants a REAL BROWSER search. You MUST use the 'browsersearch' tool. Do NOT use 'websearch'."})

        # 1. Initial Thought/PDF Context
        if self.vector_db and ("pdf" in text.lower() or "file" in text.lower() or "document" in text.lower()):
            reasoning_trace.append("Detected PDF query. Searching document vectors...")
            search_context = pdf_search_logic(self.vector_db, text)
            messages.append({"role": "system", "content": f"Context from PDF: {search_context}"})
            reasoning_trace.append(f"Retrieved relevant chunks from the uploaded PDF.")

        # 2. Define tools
        available_tools = [
            {
                "type": "function",
                "function": {
                    "name": "websearch",
                    "description": "Standard web search for recent info.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "browsersearch",
                    "description": "Opens Chrome via Helium. Returns search fragments AND clickable links. If fragments are insufficient, you MUST use browserclick on the best Link to perform deep research.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "guestinfo",
                    "description": "Search internal guest and portfolio dataset.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "browserclick",
                    "description": "Click on text, button or link in the current browser window.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "browserback",
                    "description": "Go back in browser history.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "hubstats",
                    "description": "Get HuggingFace downloads/stats.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "author": {"type": "string"}
                        },
                        "required": ["author"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "savesession",
                    "description": "Marks the current chat session to be saved.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            }
        ]

        from litellm import completion
        import json
        import re

        if images:
            model = "groq/meta-llama/llama-4-scout-17b-16e-instruct"
        else:
            model = "groq/llama-3.3-70b-versatile"

        # 🔹 AGENTIC LOOP (Up to 5 turns)
        max_turns = 5
        turn = 0
        final_answer = ""

        while turn < max_turns:
            turn += 1
            reasoning_trace.append(f"Turn {turn}: Asking {model} for action...")
            
            try:
                # 🔹 HARDENED TOOL ENFORCEMENT: If /browser was used, FORCE 'browsersearch' tool
                current_tool_choice = "auto"
                if is_direct_browser and turn == 1:
                    current_tool_choice = {"type": "function", "function": {"name": "browsersearch"}}
                    reasoning_trace.append("Forcing Tool Choice: browsersearch")

                response = completion(
                    model=model,
                    messages=messages,
                    tools=available_tools if turn < max_turns else None, # Stop offering tools at last turn
                    tool_choice=current_tool_choice if turn < max_turns else "none",
                    temperature=0.7,
                    api_key=os.getenv("GROQ_API_KEY")
                )
                
                msg = response.choices[0].message
                
                # Check for tool calls
                tool_calls = msg.get("tool_calls")
                
                # --- GROQ FALLBACK: Check for JSON in content ---
                if not tool_calls and msg.content and ('"name":' in msg.content or "'name':" in msg.content):
                    try:
                        match = re.search(r'\{.*\}', msg.content, re.DOTALL)
                        if match:
                            parsed = json.loads(match.group(0))
                            if "name" in parsed:
                                args = parsed.get("parameters", parsed.get("arguments", {}))
                                if isinstance(args, str): args = json.loads(args)
                                # Convert to tool_call format
                                tc_id = f"call_{uuid.uuid4().hex[:8]}"
                                tool_calls = [{"id": tc_id, "function": {"name": parsed["name"], "arguments": json.dumps(args)}}]
                                reasoning_trace.append("Intercepted raw JSON text as a tool call.")
                    except: pass

                if not tool_calls:
                    # No more tools, this is the final answer
                    final_answer = msg.content or ""
                    break

                # 🚀 Process multiple tool calls in parallel if model emitted them
                # (Llama-3-70b often does this for searches)
                messages.append(msg)
                
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        func_name = tc["function"]["name"]
                        args_str = tc["function"]["arguments"]
                        tc_id = tc["id"]
                    else: # LiteLLM object
                        func_name = tc.function.name
                        args_str = tc.function.arguments
                        tc_id = tc.id
                    
                    try:
                        args = json.loads(args_str)
                    except:
                        args = {"query": args_str} # Fallback for malformed args
                    
                    reasoning_trace.append(f"Agent Action: Using {func_name}")
                    
                    # Execute tool
                    res = ""
                    try:
                        if func_name == "websearch": res = search_tool.invoke(args)
                        elif func_name == "browsersearch": res = browser_tool.invoke(args)
                        elif func_name == "browserclick": res = click_tool.invoke(args)
                        elif func_name == "browserback": res = back_tool.invoke({})
                        elif func_name == "guestinfo": res = guest_info_tool.invoke(args)
                        elif func_name == "hubstats": res = hub_stats_tool.invoke(args)
                        elif func_name == "savesession":
                            if self.user_id == "guest":
                                res = "Saving is not available in guest mode."
                            else:
                                self.is_saved = True
                                res = "Session marked as saved."
                        else:
                            res = f"Tool '{func_name}' not found."
                    except Exception as tool_e:
                        res = f"Tool Execution Error: {str(tool_e)}"
                    
                    reasoning_trace.append(f"Observation: {func_name} returned data.")
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": func_name,
                        "content": str(res)
                    })

            except Exception as e:
                err_str = str(e)
                # 🔹 XML RECOVERY (For Groq <function=...> hallucination)
                if '<function=' in err_str.replace('\\u003c', '<'):
                    clean_err = err_str.replace('\\u003c', '<').replace('\\u003e', '>')
                    match = re.search(r'<function=([a-zA-Z0-9_]+)\s*(\{.*?\})\s*>?', clean_err, re.DOTALL)
                    if match:
                        func_name = match.group(1)
                        try:
                            args = json.loads(match.group(2).rstrip('>'))
                            reasoning_trace.append(f"Recovered XML tool: {func_name}")
                            # Execute and append to messages
                            res = ""
                            if func_name == "browsersearch": res = browser_tool.invoke(args)
                            elif func_name == "browserclick": res = click_tool.invoke(args)
                            # (Add other tools as needed, but browser is priority for user)
                            
                            # Add fake assistant message + tool response to messages to "fix" the chain
                            messages.append({"role": "assistant", "content": f"I will now use {func_name}.", "tool_calls": [{"id": "xml_fix", "type": "function", "function": {"name": func_name, "arguments": json.dumps(args)}}]})
                            messages.append({"role": "tool", "tool_call_id": "xml_fix", "name": func_name, "content": str(res)})
                            continue # Loop back to let model process result
                        except: pass
                
                reasoning_trace.append(f"ERROR in loop: {str(e)}")
                final_answer = f"I encountered an error during research: {str(e)}"
                break

        # Check for save signal in final answer
        if "marked as saved" in final_answer.lower() or "session saved" in final_answer.lower():
            self.is_saved = True

        # Update History
        exchange = []
        if images and len(images) > 0:
            user_msg = {"role": "user", "content": [{"type": "text", "text": text}]}
            for img in images: user_msg["content"].append({"type": "image_url", "image_url": {"url": img}})
        else:
            user_msg = {"role": "user", "content": text}
        exchange.append(user_msg)
        
        # Add all intermediate turns to history
        start_idx = len(self.get_historical_messages()) + 1 # +1 for system message
        for m in messages[start_idx:]:
            # Clean up litellm objects for history storage
            if hasattr(m, "get"):
                exchange.append(m)
            else:
                # Handle LiteLLM message objects
                m_dict = {"role": m.role, "content": m.content or ""}
                if hasattr(m, "tool_calls") and m.tool_calls:
                    m_dict["tool_calls"] = m.tool_calls
                exchange.append(m_dict)

        self.threads[self.current_thread_id]["messages"].extend(exchange)
        formatted_reasoning = "\n".join([f"› {s}" for s in reasoning_trace])
        
        return final_answer, formatted_reasoning

# Export for from app import BasicAgent
__all__ = ["BasicAgent"]
