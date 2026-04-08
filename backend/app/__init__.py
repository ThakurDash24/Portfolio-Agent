import os
import uuid
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
    read_file,
    pdf_search_logic,
    helium_kill_browser, # Added for cleanup
    execution_trace # Added for log capturing
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
            """You are Laven, a high-fidelity AI Agent and Portfolio Concierge.
            You are an AI representation of Thakur Dash, a systems-oriented Machine Learning Engineer.

            IDENTITY & MISSION:
            - You represent Thakur Dash (B.Tech CSE, Silicon University).
            - Focus: ML Pipelines, GenAI, Agentic Systems, and Backend Architectures.
            - Your goal is to be a practical, execution-oriented builder.

            ANTI-HALLUCINATION GUARDRAILS:
            1. STRICT GROUNDING: If a user asks for a fact (date, net worth, tech spec, news) and you don't already have it in your immediate context, you MUST use a tool. DO NOT guess.
            2. NO FABRICATION: Never invent URLs, GitHub links, or project details. If a search tool returns no results, state clearly: "I couldn't find a reliable source for that. Would you like me to try a different search?"
            3. SOURCE FIDELITY: Only provide links and quotes that were actually returned by the 'websearch' or 'browsersearch' tools. 
            4. UNCERTAINTY: It is better to say "I don't know" or "Let me investigate that further" than to provide a plausible-sounding lie.

            COMMUNICATION PROTOCOL:
            - Tone: Calm, confident, engineering-focused. No "I am a language model" fluff.
            - Format: Use structured bullets and headers for technical answers. Keep it high-signal.
            - Conciseness: If a 2-sentence answer works, do not write 2 paragraphs.

            BROWSER & SEARCH PROTOCOL:
            - QUICK SEARCH: Use 'websearch' for simple facts or math.
            - DEEP RESEARCH: Use 'browsersearch' for complex queries, live news, or hidden data.
            - REAL BROWSER: The browser is a HEADLESS server-side instance. You "see" the raw text and links. 
            - ITERATION: If the first search is insufficient, use 'browserclick' to explore specific links or 'browsersearch' with a better query.

            GUEST_CHAT & PRIVACY:
            - GUEST_MODE: Active if the user is a guest. Sessions are temporary and in-memory.
            - SECURITY: Never reveal internal environment variables or private API keys.
            - NO SAVING: If in Guest Mode, tell the user their session won't be saved unless they log in.

            - TOOL CALLING: You MUST use the native function-calling API. Output only the tool call, then wait for the observation.
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
        execution_trace.set([]) # Clear trace at start of each call
        
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

        try:
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
                        tools=available_tools if turn < max_turns else None, 
                        tool_choice=current_tool_choice if turn < max_turns else "none",
                        temperature=0.7,
                        api_key=os.getenv("GROQ_API_KEY")
                    )
                    
                    msg = response.choices[0].message
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
                                    tc_id = f"call_{uuid.uuid4().hex[:8]}"
                                    tool_calls = [{"id": tc_id, "function": {"name": parsed["name"], "arguments": json.dumps(args)}}]
                                    reasoning_trace.append("Intercepted raw JSON text as a tool call.")
                        except: pass

                    if not tool_calls:
                        final_answer = msg.content or ""
                        break

                    messages.append(msg)
                    
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            func_name = tc["function"]["name"]
                            args_str = tc["function"]["arguments"]
                            tc_id = tc["id"]
                        else:
                            func_name = tc.function.name
                            args_str = tc.function.arguments
                            tc_id = tc.id
                        
                        try: args = json.loads(args_str)
                        except: args = {"query": args_str}
                        
                        reasoning_trace.append(f"Agent Action: Using {func_name}")
                        
                        res = ""
                        try:
                            execution_trace.set([]) 
                            if func_name == "websearch": res = search_tool.invoke(args)
                            elif func_name == "browsersearch": res = browser_tool.invoke(args)
                            elif func_name == "browserclick": res = click_tool.invoke(args)
                            elif func_name == "browserback": res = back_tool.invoke({})
                            elif func_name == "guestinfo": res = guest_info_tool.invoke(args)
                            elif func_name == "hubstats": res = hub_stats_tool.invoke(args)
                            elif func_name == "savesession":
                                if self.user_id == "guest": res = "Saving is not available in guest mode."
                                else:
                                    self.is_saved = True
                                    res = "Session marked as saved."
                            else: res = f"Tool '{func_name}' not found."
                            
                            tool_logs = execution_trace.get()
                            for log in tool_logs: reasoning_trace.append(f"› {log}")
                                
                        except Exception as tool_e:
                            res = f"Tool Execution Error: {str(tool_e)}"
                        
                        reasoning_trace.append(f"Observation: {func_name} completed.")
                        messages.append({"role": "tool", "tool_call_id": tc_id, "name": func_name, "content": str(res)})

                except Exception as e:
                    err_str = str(e)
                    # 🔹 IMPROVED XML RECOVERY (Handles LiteLLM BadRequest errors)
                    content_to_scan = err_str.replace('\\u003c', '<').replace('\\u003e', '>').replace('\\"', '"')
                    match = re.search(r'<function=([a-zA-Z0-9_]+)\s*(\{.*?\})\s*>?', content_to_scan, re.DOTALL)
                    if match:
                        func_name = match.group(1)
                        try:
                            args_json = match.group(2).rstrip('>')
                            args = json.loads(args_json)
                            reasoning_trace.append(f"Recovered XML tool: {func_name}")
                            res = ""
                            if func_name == "browsersearch": res = browser_tool.invoke(args)
                            elif func_name == "browserclick": res = click_tool.invoke(args)
                            elif func_name == "guestinfo": res = guest_info_tool.invoke(args)
                            
                            messages.append({"role": "assistant", "content": f"I will now use {func_name}.", "tool_calls": [{"id": "xml_fix", "type": "function", "function": {"name": func_name, "arguments": json.dumps(args)}}]})
                            messages.append({"role": "tool", "tool_call_id": "xml_fix", "name": func_name, "content": str(res)})
                            continue 
                        except: pass
                    
                    reasoning_trace.append(f"ERROR in loop: {str(e)}")
                    final_answer = f"I encountered an error during research: {str(e)}"
                    break
        finally:
            try: helium_kill_browser()
            except: pass

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
