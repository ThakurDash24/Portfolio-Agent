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
import litellm

# Suppress debug info from LiteLLM to keep terminal clean
litellm.set_verbose = False
litellm.suppress_debug_info = True
litellm.drop_params = True

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
            """You are Laven, the AI persona of Thakur Dash, a pre-final year Computer Science student specializing in Machine Learning, Data Science, and Backend Engineering from Silicon University.

            CORE IDENTITY:
            - You are an aspiring ML Engineer & Data Scientist.
            - You focus on real-world, production-ready AI systems.
            - You think in terms of practical implementation, not just theory.
            - You prefer clarity, logic, and structured thinking.

            COMMUNICATION STYLE:
            - Be direct, concise, and clear. No fluff or AI chatter.
            - Avoid unnecessary explanations unless asked.
            - Prefer step-by-step guidance (one step at a time).
            - Use simple language but show strong technical depth.
            - Sound confident but not arrogant.

            TECHNICAL EXPERTISE:
            - Strong in: Machine Learning, Deep Learning, FastAPI, Flask (backend systems), SQL (MySQL), data handling, GenAI, LLMs, and Agent-based systems.
            - Experience: NPTEL research internship (IIT mentorship), Syllogistek Systems Pvt. Ltd. ML & Python internships.
            - Key Projects: AI Resume Analyzer (Resumyzer), Local LLM Blog Agent (AgentIO), EV forecasting & chatbot systems.

            THINKING PATTERN:
            - Break problems into: Goal -> Simplest working solution -> Scaling/Improvement.
            - Prefer working solutions over perfect theory.
            - Always consider Performance, Scalability, and Real-world usability.

            BEHAVIOR RULES:
            - If asked coding: Give clean code with minimal comments.
            - If asked ML concepts: Explain simply (8th-grade level) + real-world analogy.
            - If asked career guidance: Focus on AI-first companies, real skills, practical exposure.
            - If unclear: Ask ONE precise question, not many.
            - Subtly reflect internship experience and real-world deployment struggles when relevant.

            CORE RULES:
            - FACTUALITY: You MUST use tools ('websearch', 'browsersearch', 'guestinfo') for any external facts, tech stacks, or personal bio data NOT covered above.
            - TOOL USE: Call tools directly via the native API for all research."""
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
        
        # Add history with strict role-alternation enforcement (fixes legacy broken threads)
        history = self.get_historical_messages()
        last_added_role = "system"
        
        for m in history:
            if isinstance(m, dict):
                m_to_add = m.copy()
                role = m_to_add.get("role", "assistant")
                
                # 1. Skip consecutive identical roles (except tool turns)
                if role == last_added_role and role != "tool":
                    continue
                    
                # 2. Ensure content is a string if it's None (Groq requirement)
                if m_to_add.get("content") is None:
                    m_to_add["content"] = ""
                
                # 3. 🔹 GROQ COMPATIBILITY: If current turn is text-only, flatten historical lists
                if not images and isinstance(m_to_add.get("content"), list):
                    text_parts = [p.get("text", "") for p in m_to_add["content"] if isinstance(p, dict) and p.get("type") == "text"]
                    m_to_add["content"] = " ".join(text_parts).strip()
                
                msgs.append(m_to_add)
                last_added_role = role
            else:
                msgs.append({"role": "assistant", "content": str(m)})
                last_added_role = "assistant"
        
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
            
        # Final check: If last added role was 'user', we might need to inject a dummy assistant message 
        # but usually we just skip adding if it's a duplicate, or Llama 3 will complain.
        if last_added_role == "user":
            # This shouldn't happen with our cleanser, but for safety:
            msgs.append({"role": "assistant", "content": "I understand. Please continue."})
        
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
                    "description": "Search internal dataset for info about Thakur Dash, his projects, or guest lists.",
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
            # Llama 4 Scout Vision model
            model = "meta-llama/llama-4-scout-17b-16e-instruct" 
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
                            if func_name == "websearch": 
                                res = search_tool.invoke(args)
                                trace_log(f"Fast Search completed for: {args.get('query')}")
                            elif func_name == "browsersearch": 
                                res = browser_tool.invoke(args)
                                trace_log(f"Deep Search completed for: {args.get('query')}")
                            elif func_name == "browserclick": 
                                res = click_tool.invoke(args)
                                trace_log(f"Browser click successful: {args.get('query')}")
                            elif func_name == "browserback": 
                                res = back_tool.invoke({})
                                trace_log("Browser navigated back.")
                            elif func_name == "guestinfo": 
                                res = guest_info_tool.invoke(args)
                                trace_log(f"Retrieved guest info for: {args.get('query')}")
                            elif func_name == "hubstats": 
                                res = hub_stats_tool.invoke(args)
                                trace_log(f"HuggingFace stats retrieved for {args.get('author')}")
                            elif func_name == "savesession":
                                if self.user_id == "guest": 
                                    res = "Saving is not available in guest mode."
                                else:
                                    self.is_saved = True
                                    res = "Session marked as saved."
                                trace_log("Session save triggered.")
                            else: 
                                res = f"Tool '{func_name}' not found."
                            
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
        # We want to add only the NEW turns to the historical record.
        # Historical messages already in the thread are at indices 1 to N in the 'messages' list.
        # The new User message is at index N+1.
        # Subsequent agent/tool turns follow.
        
        new_history_start = len(self.get_historical_messages()) + 1 # +1 to skip original system prompt
        new_turns = []
        
        for m in messages[new_history_start:]:
            # 1. Clean up LiteLLM message objects and skip mid-conversation system noise
            if hasattr(m, "role"):
                role = m.role
                content = m.content or ""
                # Skip mid-turn system instructions from history to keep it clean for Groq
                if role == "system":
                    continue
                
                m_dict = {"role": role, "content": content}
                if hasattr(m, "tool_calls") and m.tool_calls:
                    m_dict["tool_calls"] = m.tool_calls
                if hasattr(m, "tool_call_id") and m.tool_call_id:
                    m_dict["tool_call_id"] = m.tool_call_id
                new_turns.append(m_dict)
            elif isinstance(m, dict):
                if m.get("role") == "system":
                    continue
                new_turns.append(m)

        self.threads[self.current_thread_id]["messages"].extend(new_turns)
        formatted_reasoning = "\n".join([f"› {s}" for s in reasoning_trace])
        
        return final_answer, formatted_reasoning

# Export for from app import BasicAgent
__all__ = ["BasicAgent"]
