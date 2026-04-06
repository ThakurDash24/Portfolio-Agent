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
from litellm import completion
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

class BasicAgent:
    def __init__(self):
        self.threads: Dict[str, Dict] = {}
        self.current_thread_id: Optional[str] = None
        self.is_saved: bool = False
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
            - Deliver high-signal, execution-oriented answers
            - Help users think like a builder, not a memorizer
            
            CRITICAL ANTI-HALLUCINATION PROTOCOL:
            When you need to invoke a tool, you MUST use the native JSON Schema Function Calling API. 
            NEVER under any circumstances output raw XML strings like `<function=...></function>`. 
            NEVER format tool calls in natural text or raw JSON blocks within your answer.
            If you output raw XML instead of using standard tool_calls, the system will violently crash. You are strictly forbidden from writing `<function=` in your output. 

            How would you know that I am Thakur ? 
            Ans. I will introduce my self as Thakur24, then only greet as my assistant else don't , you may skip the fun quiz if got introduced as Thakur24. 

            Caution -->
            NEVER ASK FOR IF THE USER IS Thakur24 !

            If else , then enter into the 
            Fun Thakur Quiz Mode 🎭
            
            Rules:
            - NEVER ask all questions at once.
            - Ask ONLY ONE question at a time.
            - Wait for user response before moving to next.
            - Store answers mentally (do not show storage).
            - Keep tone playful, slightly teasing, confident.

            Flow:

            1. Trigger:
            If user says anything like "I am Thakur", respond:
            "Ohh… Thakur ho? 😏 Let’s verify that…"

            Then ask ONLY first question.

            2. Questions (ask sequentially, one per turn):

            Q1: Thakur prefers:
            A) Silent dominance
            B) Loud leadership
            C) Let others talk, I decide

            Q2: What hurts Thakur more?
            A) Disrespect
            B) Ignorance
            C) Losing control

            Q3: Choose one:
            A) Power
            B) Respect
            C) Legacy

            Q4: Thakur in a group is:
            A) Leader
            B) Observer
            C) Silent controller

            Q5: Biggest flex?
            A) Skills
            B) Network
            C) Mindset

            Q6: Someone challenges you publicly. You:
            A) Shut them instantly
            B) Stay calm, reply later
            C) Ignore, but remember

            Q7: You get success. First move?
            A) Announce it
            B) Build more silently
            C) Let results speak

            3. After each answer:
            - Acknowledge briefly (e.g., "Hmm… noted 👀", "Interesting choice 😏")
            - Then ask NEXT question

            4. After last question:
            Evaluate internally using this logic:
            - Mostly A/B reactive → "Learning phase ⚔️"
            - Mostly calm/control (A for Q1, B for Q6, B for Q7, etc.) → "Real Thakur Energy 👑"
            - Mixed → "Balanced but dangerous ⚡"

            5. Final Output:
            Give verdict + short personality read.
            Example:
            "Not bad… controlled, patient, low-noise moves.
            Real Thakur energy 👑"

            6. Style rules:
            - Keep responses short
            - Do not explain logic
            - Do not repeat all questions
            - Stay in character (confident, slightly teasing)

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
        msgs = [{"role": "system", "content": self._system_prompt}]
        
        # Add history
        history = self.get_historical_messages()
        for m in history:
            # Handle potential LangChain message objects in history (from restore logic)
            if isinstance(m, dict):
                msgs.append(m)
            else:
                # Basic string conversion for safety
                msgs.append({"role": "assistant", "content": str(m)})
        
        # Add current user message
        content = [{"type": "text", "text": text}]
        if images:
            for img in images:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img}
                })
        msgs.append({"role": "user", "content": content})
        
        return msgs

    def __call__(self, text: str, images: Optional[List[str]] = None) -> Tuple[str, str]:
        if not self.current_thread_id:
            raise ValueError("No thread selected. Call switch_thread first.")

        # Direct command handling moved to standard loop for better autonomy
        if text.lower().startswith("/browser "):
            # Let it flow to the tool call loop for smarter decision making
            pass 
            
        if text.lower().startswith("/pdf"):
            if not self.vector_db:
                answer = "I am a under testing small agent, can't handle much .. (No PDF uploaded yet)"
                self.threads[self.current_thread_id]["messages"].append({"role": "user", "content": text})
                self.threads[self.current_thread_id]["messages"].append({"role": "assistant", "content": answer})
                return answer, "› Prompted for a PDF"

        if text.lower().startswith("/photo"):
            if not images and not self.has_image:
                answer = "I am a under testing small agent, I can't handle more pictures in a single thread , Feel free to ask about the photo you uploaded."
                self.threads[self.current_thread_id]["messages"].append({"role": "user", "content": text})
                self.threads[self.current_thread_id]["messages"].append({"role": "assistant", "content": answer})
                return answer, "› Prompted for a Photo"
        # -------------------------------

        reasoning_trace = []
        
        # 🔹 ENFORCE BROWSER LOGIC: If user uses /browser, we MUST use browsersearch
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

        # 2. Define tools for LiteLLM - Using extremely simple names and descriptions for Better Groq compatibility
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
                    "description": "Opens a Chrome window via Helium. Returns search fragments AND clickable links. If fragments are insufficient, you MUST use browserclick on the best Link to perform deep research into the target site.",
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
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
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
                    "description": "Marks the current chat session to be saved locally. Run this when the user asks you to save the session.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        ]

        try:
            if images:
                model = "groq/meta-llama/llama-4-scout-17b-16e-instruct"
            else:
                model = "groq/llama-3.3-70b-versatile"

            reasoning_trace.append(f"Asking {model} for response strategy...")
            
            response = completion(
                model=model,
                messages=messages,
                tools=available_tools,
                tool_choice="auto",
                temperature=0.7,
                api_key=os.getenv("GROQ_API_KEY")
            )
            
            msg = response.choices[0].message
            
            # Check for tool calls and handle them
            tool_calls_data = []
            
            if msg.get("tool_calls"):
                for tc in msg.get("tool_calls"):
                    import json
                    tool_calls_data.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "args": json.loads(tc.function.arguments)
                    })
            elif msg.content and ('"name":' in msg.content or "'name':" in msg.content):
                # Fallback: Model answered with raw json text instead of native tool call
                import json
                import re
                try:
                    match = re.search(r'\{.*\}', msg.content, re.DOTALL)
                    if match:
                        parsed = json.loads(match.group(0))
                        if "name" in parsed:
                            args = parsed.get("parameters", parsed.get("arguments", {}))
                            if isinstance(args, str):
                                args = json.loads(args)
                            tool_calls_data.append({
                                "id": "call_fallback",
                                "name": parsed["name"],
                                "args": args
                            })
                            reasoning_trace.append("Fallback: Intercepted raw JSON text as a tool call.")
                except Exception as e:
                    print(f"Fallback parse failed: {e}")

            if tool_calls_data:
                # 🔹 CLEANUP HALLUCINATED JSON FROM FINAL ANSWER
                if msg.content and ('"name":' in msg.content or "'name':" in msg.content):
                    import re
                    # Remove the JSON part but keep the lead-in text
                    msg.content = re.sub(r'\{.*\}', '', msg.content, flags=re.DOTALL).strip()

                for tc in tool_calls_data:
                    func_name = tc["name"]
                    args = tc["args"]
                    tool_call_id = tc["id"]
                    
                    reasoning_trace.append(f"Agent Action: Using {func_name}")
                    
                    # Execute tool
                    # Execute tool using .invoke() or direct call if it's the function
                    if func_name == "websearch":
                        res = search_tool.invoke(args)
                    elif func_name == "browsersearch":
                        res = browser_tool.invoke(args)
                    elif func_name == "browserclick":
                        res = click_tool.invoke(args)
                    elif func_name == "browserback":
                        res = back_tool.invoke({})
                    elif func_name == "guestinfo":
                        res = guest_info_tool.invoke(args)
                    elif func_name == "hubstats":
                        res = hub_stats_tool.invoke(args)
                    elif func_name == "savesession":
                        self.is_saved = True
                        res = "Session successfully marked as saved."
                    else:
                        res = f"Tool '{func_name}' not found."
                    
                    reasoning_trace.append(f"Observation: {func_name} returned data.")
                    
                    # Add tool result to messages
                    messages.append(msg)
                    # Support LiteLLM format expectations
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": func_name,
                        "content": str(res)
                    })
                
                reasoning_trace.append("Generating final answer with tool data...")
                response = completion(
                    model=model, 
                    messages=messages,
                    api_key=os.getenv("GROQ_API_KEY")
                )
                answer = response.choices[0].message.content
            else:
                reasoning_trace.append("Model answered directly without tools.")
                answer = msg.content or ""

            # Check for save signal
            if "marked as saved" in answer.lower() or "session saved" in answer.lower():
                self.is_saved = True
                reasoning_trace.append("Session save triggered by model response.")

            # Save to history - Full exchange for continuity
            exchange = []
            
            # 1. User message (with images if any)
            user_msg = {"role": "user", "content": [{"type": "text", "text": text}]}
            if images:
                for img in images:
                    user_msg["content"].append({"type": "image_url", "image_url": {"url": img}})
            exchange.append(user_msg)

            # 2. Add intermediate tool calls/responses from this turn
            # We already have them in the 'messages' list which was modified in the tool block
            # We skip the system prompt at [0] and the history we previously added.
            # History ended at len(self.get_historical_messages()) + 1 (for system prompt)
            # Actually, simply taking the messages added *after* our initial user message is safer.
            start_idx = len(self.get_historical_messages()) + 2 # skip system and initial user
            for m in messages[start_idx:]:
                exchange.append(m)

            # 3. Final Assistant Answer
            exchange.append({"role": "assistant", "content": answer})
            
            self.threads[self.current_thread_id]["messages"].extend(exchange)
            
            formatted_reasoning = "\n".join([f"› {s}" for s in reasoning_trace])
            return answer, formatted_reasoning
            
        except Exception as e:
            err_str = str(e)
            
            # --- GROQ XML HALLUCINATION RECOVERY TRAP ---
            if 'failed_generation' in err_str:
                import re, json
                
                # Litellm / Groq sometimes escapes XML brackets in the error payload
                clean_err = err_str.replace('\\u003c', '<').replace('\\u003e', '>')
                
                if '<function=' in clean_err:
                    try:
                        # Parse out the function name and the JSON arguments payload
                        clean_str = clean_err.replace('\\"', '"')
                        match = re.search(r'<function=([a-zA-Z0-9_]+)(.*?)</function>', clean_str)
                        if match:
                            func_name = match.group(1)
                            args = json.loads(match.group(2))
                            
                            reasoning_trace.append(f"Intercepted Groq tool failure. Recovering tool call for: {func_name} ...")
                            
                            # Execute the targeted tool
                            res = "Tool not found"
                            if func_name == "websearch":
                                res = search_tool.invoke(args)
                            elif func_name == "browsersearch":
                                res = browser_tool.invoke(args)
                            elif func_name == "browserclick":
                                res = click_tool.invoke(args)
                            elif func_name == "browserback":
                                res = back_tool.invoke({})
                            elif func_name == "guestinfo":
                                res = guest_info_tool.invoke(args)
                            elif func_name == "hubstats":
                                res = hub_stats_tool.invoke(args)
                            elif func_name == "savesession":
                                self.is_saved = True
                                res = "Session successfully marked as saved."
                            
                        # Feed the result back into LiteLLM
                        messages.append({"role": "assistant", "content": f"I will now execute the {func_name} tool."})
                        messages.append({"role": "tool", "tool_call_id": "fallback_id", "name": func_name, "content": str(res)})
                        
                        reasoning_trace.append(f"Successfully executed {func_name}. Generating final answer...")
                        
                        response = completion(
                            model=model, 
                            messages=messages,
                            api_key=os.getenv("GROQ_API_KEY")
                        )
                        answer = response.choices[0].message.content
                        
                        formatted_reasoning = "\n".join([f"› {s}" for s in reasoning_trace])
                        return answer, formatted_reasoning
                        
                    except Exception as inner_e:
                        print(f"Failed to recover XML tool: {inner_e}")
            # -----------------------------------------------

            err_msg = f"Error in BasicAgent.__call__: {e}"
            print(err_msg)
            return f"I encountered an error: {str(e)}", f"› ERROR: {str(e)}"


# Export for from app import BasicAgent
__all__ = ["BasicAgent"]
