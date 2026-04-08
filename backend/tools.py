from langchain_core.tools import tool
import time
import urllib.parse
import random
import os
from pydantic import BaseModel, Field

# ------------------ GLOBAL RETRIEVERS ------------------
bm25_retriever = None
guest_retriever = None

# ------------------ VECTOR DB AND STORE FOR PDFS -----------
# Note: vector_db is now managed per-session/agent to ensure isolation.

def init_pdf_vectorstore(file_path: str):
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import HuggingFaceEmbeddings

    print(f"LOADING PDF: {file_path}")
    loader = PyPDFLoader(file_path)
    docs = loader.load()
    print(f"PDF LOADED: {len(docs)} pages")

    # Split into chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100
    )
    chunks = splitter.split_documents(docs)
    print(f"SPLIT COMPLETED: {len(chunks)} chunks")

    if not chunks:
        raise ValueError("No text could be extracted from this PDF. It might be empty or a scanned image without OCR.")

    # Embeddings (free)
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    print("EMBEDDINGS INITIALIZED")

    # Store in Chroma
    print("STARTING CHROMA INDEXING...")
    db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings
    )
    print(f"Stored {len(chunks)} chunks in Chroma")
    return db

class PDFQuery(BaseModel):
    query: str = Field(description="Query from uploaded PDF")

class PDFUploadInput(BaseModel):
    file_path: str = Field(description="Path of the PDF file to upload")

@tool(args_schema=PDFUploadInput)
def upload_pdf_tool(file_path: str) -> str:
    """
    Use this tool when user wants to upload/load a PDF.

    The input must be a valid file path.
    Example:
    - "load this pdf: C:/docs/file.pdf"
    - "upload pdf /home/user/file.pdf"
    """

    if not os.path.exists(file_path):
        return f"File not found at: {file_path}"

    try:
        from tools import init_pdf_vectorstore
        result = init_pdf_vectorstore(file_path)
        return f"PDF loaded successfully. {result}"
    except Exception as e:
        return f"Error loading PDF: {e}"

def pdf_search_logic(vector_db, query: str) -> str:
    """Helper logic for PDF searching, used by the agent-bound tool."""
    if vector_db is None:
        return "No PDF loaded. Ask user to upload a PDF first."

    # Retrieve relevant chunks
    docs = vector_db.similarity_search(query, k=6)

    # Force include first chunk (important for resumes)
    try:
        first_doc = vector_db._collection.get(limit=1)["documents"][0]
        # Wrap in a simple object if needed, but similarity_search returns LangChain docs
        if not any(d.page_content == first_doc for d in docs):
            from langchain_core.documents import Document
            docs.append(Document(page_content=first_doc))
    except:
        pass
        
    return "\n\n".join([d.page_content for d in docs])

@tool
def pdf_search_tool(query: str) -> str:
    """
    ALWAYS use this tool when the user asks about the PDF.
    This is a fallback global tool. For session isolation, agents use a bound version.
    """
    return "Base tool called. Please use the session-specific PDF tool."

# ------------------ INIT ------------------
def init_guest_retriever(docs):
    from langchain_community.retrievers import BM25Retriever
    global guest_retriever
    guest_retriever = BM25Retriever.from_documents(docs)

# ------------------ SCHEMAS ------------------
class Query(BaseModel):
    query: str = Field(description="Query string")

# ------------------ TOOLS ------------------

@tool(args_schema=Query)
def guest_info_tool(query: str) -> str:
    """Use ONLY for guest/person info (name, relation, description)."""
    if guest_retriever is None:
        return "Guest retriever not initialized"
    results = guest_retriever.invoke(query)
    return "\n\n".join([doc.page_content for doc in results[:3]]) or "No data"


# ------------------ INIT ------------------
def init_retriever(docs_list):
    from langchain_community.retrievers import BM25Retriever
    global bm25_retriever
    bm25_retriever = BM25Retriever.from_documents(docs_list)

# ------------------ SCHEMAS ------------------
class SearchQuery(BaseModel):
    query: str = Field(description="Search query for real-time or unknown info")

class GuestQuery(BaseModel):
    query: str = Field(description="Guest name or relation")

class WeatherQuery(BaseModel):
    location: str = Field(description="City or location")

class HubStatsQuery(BaseModel):
    author: str = Field(description="HuggingFace username")

class FilePathQuery(BaseModel):
    file_path: str = Field(description="Safe relative file path")

class DirectoryQuery(BaseModel):
    directory: str = Field(default=".", description="Directory path")

# ------------------ TOOLS ------------------

@tool(args_schema=GuestQuery)
def guest_info_retriever(query: str) -> str:
    """Use this ONLY when asked about a guest or person from dataset."""
    global bm25_retriever

    if bm25_retriever is None:
        raise ValueError("Retriever not initialized")

    results = bm25_retriever.invoke(query)
    if not results:
        return "No data found"

    return "\n\n".join([doc.page_content for doc in results[:3]])

guest_info_tool = guest_info_retriever


@tool(args_schema=SearchQuery)
def search_the_web(query: str) -> str:
    """Use this for real-time info, unknown facts, or anything not in memory."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))

        if not results:
            return "No results"

        return "\n\n".join([
            f"{r['title']}: {r['body']}" for r in results
        ])

    except Exception as e:
        return f"Search error: {e}"

@tool(args_schema=SearchQuery)
def browser_search_tool(query: str) -> str:
    """Use this to open a real browser (Chrome) and search using Helium. 
    Ideal for complex info or when search results need more depth.
    Handles Google CAPTCHAs by falling back to DuckDuckGo.
    (Optimized Extraction)
    """
    import helium
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    try:
        options = Options()
        
        # 🚀 Production Support: Headless mode for cloud environments like Render
        if os.getenv("RENDER") or os.getenv("HEADLESS") or os.getenv("PORT"):
            print("Production environment (Render) detected. Enabling hardened headless browser mode...")
            
            # Aggressive anti-bot/stealth measures for production
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
            options.add_argument("--disable-infobars")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
        else:
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Ensure query is encoded properly
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.google.com/search?q={encoded_query}"
        
        print(f"Opening browser for query: {query}")
        try:
            helium.start_chrome(search_url, options=options)
        except Exception as startup_err:
            # 🚨 CRITICAL: If start_chrome fails, provide actionable feedback
            err_msg = str(startup_err)
            if "executable" in err_msg.lower():
                return f"Browser Error: Chrome not found in production environment (Render). Ensure the 'render-buildpack-chrome-headless' is added. Details: {err_msg}"
            return f"Browser Startup Failed: {err_msg}"
        
        # Check for CAPTCHA (/sorry)
        current_url = helium.get_driver().current_url
        if "/sorry" in current_url or "google.com/sorry" in current_url:
            print("Google CAPTCHA detected (/sorry). Switching to DuckDuckGo immediately...")
            helium.go_to(f"https://duckduckgo.com/?q={encoded_query}")
            # wait a bit for DDG to load
            time.sleep(2) 
            for _ in range(10):
                if "duckduckgo" in helium.get_driver().current_url.lower():
                    # Wait for results to actually render
                    try:
                        driver.find_element(By.ID, 'links')
                        break
                    except: pass
                time.sleep(0.5)
        
        # Check for initial content before scrolling to save time
        driver = helium.get_driver()
        
        def extract_content():
            current_url = driver.current_url
            txt = ""
            try:
                if "google.com" in current_url:
                    try:
                        # Google snippet/featured area
                        featured = driver.find_element(By.CLASS_NAME, 'LGOvwe') 
                        txt = featured.text + "\n\n"
                    except: pass
                    txt += driver.find_element(By.ID, 'search').text
                elif "duckduckgo.com" in current_url:
                    txt = driver.find_element(By.ID, 'links').text
            except: pass
            return txt if txt else driver.find_element(By.TAG_NAME, 'body').text

        main_text = extract_content()
        
        import re
        stop_words = {'what', 'is', 'the', 'of', 'how', 'much', 'many', 'does', 'whos', 'who', 'when', 'where', 'in', 'on', 'at', 'to', 'for'}
        query_words = set(w for w in re.findall(r'\w+', query.lower()) if w not in stop_words)
        if not query_words: query_words = set(re.findall(r'\w+', query.lower()))

        def get_scored_results(text, driver):
            blocks = text.split('\n')
            res = []
            seen = set()
            
            # Extract links and titles properly
            links_info = []
            try:
                # Optimized for Google/DDG result blocks
                if "google.com" in driver.current_url:
                    selectors = driver.find_elements(By.CSS_SELECTOR, 'div.g')[:3]
                    for s in selectors:
                        try:
                            title = s.find_element(By.TAG_NAME, 'h3').text
                            link = s.find_element(By.TAG_NAME, 'a').get_attribute('href')
                            if title and link: links_info.append(f"• **{title}** [Link: {link}]")
                        except: pass
                elif "duckduckgo.com" in driver.current_url:
                    # Using a more robust selector for DDG headings
                    selectors = driver.find_elements(By.CSS_SELECTOR, 'a.rn-1pw8f9h')[:3] # DDG result class
                    if not selectors:
                        selectors = driver.find_elements(By.CSS_SELECTOR, 'article h2 a')[:3]
                    
                    for s in selectors:
                        try:
                            title = s.text
                            link = s.get_attribute('href')
                            if title and link: links_info.append(f"• **{title}** [Link: {link}]")
                        except: pass
            except: pass

            for block in blocks:
                b = block.strip()
                if len(b) < 20 or len(b) > 800 or b in seen: continue
                bl = b.lower()
                score = 0
                q_matches = sum(1 for w in query_words if w in bl)
                score += q_matches * 15
                if re.search(r'\b(is|has|was|since|total|located|found|scored|won|born|created)\b', bl): score += 10
                if re.search(r'\d+|\$|₹|percent|million|billion|centur(y|ies)', bl): score += 5
                # Aggressive Clutter Penalty (Site Names/Nav) - excluding titles we just found
                if re.search(r'(wikipedia|youtube|facebook|twitter|instagram|linkedin|ago|reactions|share|more|results|people also ask|\?)', bl): score -= 25
                if b.endswith('...'): score -= 20
                
                if score > 15:
                    f = b
                    for word in query_words:
                        if len(word) > 3: f = re.sub(f'(?i)({re.escape(word)})', r'**\1**', f)
                    res.append((score, f"• {f}"))
                    seen.add(b)
            
            res.sort(key=lambda x: x[0], reverse=True)
            output_blocks = [r[1] for r in res[:4]]
            
            if links_info:
                output_blocks.append("\n**NAVIGATE FURTHER:**\n" + "\n".join(links_info))
            
            return output_blocks

        unique_results = get_scored_results(main_text, driver)
        
        # 🔹 CONDITIONAL SCROLL
        if len(unique_results) < 3:
            helium.scroll_down(num_pixels=800)
            time.sleep(1)
            main_text = extract_content()
            unique_results = get_scored_results(main_text, driver)

        if not unique_results:
            fallback = re.sub(r'\n+', ' ', main_text[:1000])
            return f"Direct Insight: {fallback}..."

        return "\n\n".join(unique_results)
            
    except Exception as e:
        print(f"Helium Error: {e}")
        return f"Browser search failed: {e}"

@tool(args_schema=Query)
def browser_click_tool(query: str) -> str:
    """Click on a piece of text, button or link in the Chrome browser. 
    Pass the text you want to click.
    """
    import helium
    from selenium.webdriver.common.by import By
    try:
        if not helium.get_driver():
            return "No browser window open. Run a search first."
        
        print(f"Clicking on: {query}")
        helium.click(query)
        time.sleep(2)
        helium.scroll_down(500)
        
        driver = helium.get_driver()
        main_text = ""
        try:
            # Try to find content area to avoid header/footer clutter
            content_selectors = ['main', 'article', '#content', '#search', '#links']
            for selector in content_selectors:
                try:
                    if selector.startswith('#'):
                        el = driver.find_element(By.ID, selector[1:])
                    else:
                        el = driver.find_element(By.TAG_NAME, selector)
                    if el.text:
                        main_text = el.text
                        break
                except:
                    continue
        except:
            pass

        if not main_text:
            main_text = driver.find_element(By.TAG_NAME, 'body').text

        return f"Clicked '{query}'. New page summary:\n\n{main_text[:2000]}..."
    except Exception as e:
        return f"Click error: {e}"

@tool
def browser_back_tool() -> str:
    """Go back to the previous page in the Chrome browser session."""
    import helium
    try:
        if not helium.get_driver():
            return "No browser window open."
        
        helium.get_driver().back()
        time.sleep(1)
        return "Went back successfully."
    except Exception as e:
        return f"Error going back: {e}"

# Export the underlying functions for calling directly in agent
# search_tool = search_the_web.func # If langchain version supports it
# For now, let's just use the functions themselves for exports where agent calls them
search_tool = search_the_web
browser_tool = browser_search_tool
click_tool = browser_click_tool
back_tool = browser_back_tool


@tool(args_schema=DirectoryQuery)
def list_files(directory: str = ".") -> str:
    """Use to see available files before reading."""
    try:
        return "\n".join(os.listdir(directory))
    except Exception as e:
        return f"Error: {e}"


@tool(args_schema=FilePathQuery)
def read_file(file_path: str) -> str:
    """Use this ALWAYS when a file is attached. Extract data before answering."""

    # 🔒 Basic safety check
    if ".." in file_path:
        return "Access denied"

    try:
        if file_path.endswith(('.xlsx', '.xls')):
            import pandas as pd
            df = pd.read_excel(file_path)
            return df.head(5).to_string()

        elif file_path.endswith('.csv'):
            import pandas as pd
            df = pd.read_csv(file_path)
            return df.head(5).to_string()

        elif file_path.endswith('.json'):
            import json
            with open(file_path) as f:
                return json.dumps(json.load(f))[:3000]

        else:
            with open(file_path, encoding='utf-8') as f:
                return f.read()[:3000]

    except Exception as e:
        return f"Error: {e}"


@tool(args_schema=WeatherQuery)
def get_weather_info(location: str) -> str:
    """Use ONLY when asked about weather."""
    data = random.choice([
        {"condition": "Rainy", "temp": 15},
        {"condition": "Clear", "temp": 25},
        {"condition": "Windy", "temp": 20}
    ])
    return f"{location}: {data['condition']}, {data['temp']}°C"

weather_info_tool = get_weather_info


@tool(args_schema=HubStatsQuery)
def get_hub_stats(author: str) -> str:
    """Use when asked about HuggingFace models or authors."""
    from huggingface_hub import list_models
    try:
        models = list(list_models(author=author, sort="downloads", direction=-1, limit=1))
        if not models:
            return "No models found"

        m = models[0]
        return f"{m.id} ({m.downloads} downloads)"

    except Exception as e:
        return f"Error: {e}"

hub_stats_tool = get_hub_stats

@tool
def save_session_tool() -> str:
    """
    Use this tool ONLY when the user explicitly asks to save the session, 
    ends the conversation (e.g., 'okay bye', 'goodbye'), or wants to 
    persist the current chat. 
    It will mark the current session as saved.
    """
    return "Session marked as saved successfully."