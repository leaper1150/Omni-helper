import os
import re
import httpx
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# LangChain
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, SystemMessage

# Security & Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv("safe.env")

# --- SECURITY GLOBALS ---
infraction_tracker = {} 
BLACKLIST = set()       
ADMIN_STATS = {"blocked": 0, "executed": 0}

# --- SETUP ---
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Omni-Helper Master Backend")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# --- MIDDLEWARE (PRIVACY & BOUNCER) ---
def scrub_pii(text: str):
    """Locally redacts sensitive info before it hits the AI."""
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_pattern = r'\b\d{3}[-.\s]??\d{3}[-.\s]??\d{4}\b'
    text = re.sub(email_pattern, "[REDACTED_EMAIL]", text)
    text = re.sub(phone_pattern, "[REDACTED_PHONE]", text)
    return text

async def security_bouncer(request: Request):
    client_ip = request.client.host
    if client_ip in BLACKLIST:
        ADMIN_STATS["blocked"] += 1
        raise HTTPException(status_code=403, detail="BANNED: Suspicious activity detected.")
    return client_ip

@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    client_ip = request.client.host
    infraction_tracker[client_ip] = infraction_tracker.get(client_ip, 0) + 1
    if infraction_tracker[client_ip] >= 3:
        BLACKLIST.add(client_ip)
    return _rate_limit_exceeded_handler(request, exc)

# --- LANGCHAIN BRAIN ---
llm = ChatGoogleGenerativeAI(
    model="gemini-3-flash-preview", 
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.7
)

from typing import Optional

class HelperRequest(BaseModel):
    text: str = ""
    mode: str
    image_base64: Optional[str] = None

class DiscordRequest(BaseModel):
    content: str

# --- ROUTES ---
@app.post("/agent/execute", dependencies=[Depends(security_bouncer)])
@limiter.limit("5/minute")
async def execute_agent(request: Request, body: HelperRequest):
    safe_text = scrub_pii(body.text)
    
    # Advanced Prompts with Diagram support
    prompts = {
        "legal": "You are a Terms and Conditions Explainer. Summarize the text clearly and identify any confusing or restrictive clauses. Do not provide legal advice.",
        "code": "You are a senior engineer. Convert logic into clean Python/C++. If describing a system architecture, output a Mermaid.js diagram starting with ```mermaid",
        "idea": "You are a versatile and helpful General AI assistant. Answer the user's questions clearly and concisely. Format using Markdown.",
        "general": "You are a professional note-taking assistant. Provide a structured Markdown summary and organize the user's notes. If a workflow or process is described, output a Mermaid.js diagram starting with ```mermaid"
    }

    # Construct Multimodal Message
    content = []
    if safe_text:
        content.append({"type": "text", "text": safe_text})
    if body.image_base64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{body.image_base64}"}
        })

    messages = [
        SystemMessage(content=prompts.get(body.mode, prompts['general'])),
        HumanMessage(content=content)
    ]

    try:
        response = llm.invoke(messages)
        ADMIN_STATS["executed"] += 1
        
        # Extract text no matter how LangChain formats it
        ai_output = response.content
        if isinstance(ai_output, list):
            clean_text = "\n".join(
                item.get("text", "") if isinstance(item, dict) else str(item) 
                for item in ai_output
            )
        else:
            clean_text = str(ai_output)
            
        return {"output": clean_text}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/agent/discord", dependencies=[Depends(security_bouncer)])
async def dispatch_discord(body: DiscordRequest):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url: return {"status": "no_webhook"}

    async with httpx.AsyncClient() as client:
        payload = {
            "embeds": [{
                "title": "🚀 Omni-Helper Dispatch",
                "description": body.content[:2000],
                "color": 3447003,
                "footer": {"text": f"Processed at {datetime.now().strftime('%H:%M:%S')}"}
            }]
        }
        await client.post(webhook_url, json=payload)
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)