# chatbot_service/app/api/chat_server.py
import psutil, os
import time
import json

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

from chatbot_service.app.pipeline import AssistantPipeline
from chatbot_service.app.generation.llm_provider_manager import LLMProviderManager
from core_shared.schemas import ChatRequest, ChatResponse
from core_shared.auth.token_verifier import TokenVerifier
from core_shared.auth.redis_rate_limiter import RedisRateLimiter
from core_shared.logging_setup import logger

provider_manager = LLMProviderManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # LAZY INITIALIZATION for Chatbot
    logger.info("Initializing Chat Assistant Pipeline...")
    app.state.pipeline = AssistantPipeline()
    yield

app = FastAPI(title="Indicator AI Chatbot", lifespan=lifespan)

bearer_scheme = HTTPBearer(auto_error=False)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

verifier = TokenVerifier()
# Ensure RedisRateLimiter is using the correct chat redis (will update this separately)
rate_limiter = RedisRateLimiter(max_requests=10, window_seconds=60)

@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, req: Request,
         credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
         authorization: str = Header(None)):
    
    if credentials:
        authorization = f"Bearer {credentials.credentials}"
    start_time = time.time()
    
    # 1. Authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")

    token = authorization.replace("Bearer ", "")
    try:
        user_id = verifier.verify(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")

    # 2. Rate limiting
    if not rate_limiter.is_allowed(user_id):
        logger.info(f"user={user_id} | query='{payload.query}' | RATE_LIMITED")
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment and try again.")

    # 3. Input validation
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    if len(payload.query) > 500:
        raise HTTPException(status_code=400, detail="Query is too long.")

    # 4. Process
    try:
        pipeline = req.app.state.pipeline
        result = pipeline.ask(payload.query)
    except Exception as e:
        logger.error(f"user={user_id} | query='{payload.query}' | ERROR: {e}")
        raise HTTPException(status_code=503, detail="Assistant is temporarily unavailable. Please try again.")

    latency = time.time() - start_time
    logger.info(f"user={user_id} | query='{payload.query}' | tier={result.get('tier')} | latency={latency:.2f}s")

    return ChatResponse(
        answer=result["answer"]
    )

@app.get("/health")
def health(req: Request):
    pipeline = req.app.state.pipeline
    return {
        "status": "ok",
        "providers": pipeline.executor.llm.manager.status()
    }
