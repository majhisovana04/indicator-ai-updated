# app/api/server.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request
from app.pipeline import AssistantPipeline
from app.api.schemas import ChatRequest, ChatResponse
from app.auth.token_verifier import TokenVerifier
# from app.auth.rate_limiter import RateLimiter

from app.auth.redis_rate_limiter import RedisRateLimiter
import time
from app.logging_setup import logger
from fastapi.middleware.cors import CORSMiddleware
from app.generation.llm_provider_manager import LLMProviderManager
provider_manager = LLMProviderManager()  

@asynccontextmanager
async def lifespan(app: FastAPI):
    # LAZY INITIALIZATION:
    # Load the heavy AI pipeline (Embedder/FAISS) here so it loads
    # AFTER the worker starts, avoiding boot timeouts and duplicate RAM spikes.
    logger.info("Initializing Assistant Pipeline...")
    app.state.pipeline = AssistantPipeline()
    yield
    # Runs once when the server shuts down (nothing needed here for now)


app = FastAPI(title="Indicator AI Assistant", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # placeholder — update once frontend confirms their dev URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pipeline is now loaded in lifespan (lazy initialization)
verifier = TokenVerifier()
rate_limiter = RedisRateLimiter(max_requests=10, window_seconds=60)

# @app.post("/api/bot/chat", response_model=ChatResponse)
# def chat(payload: ChatRequest, req: Request, authorization: str = Header(None)):
#     start_time = time.time()
#     # 1. Authentication
#     if not authorization or not authorization.startswith("Bearer "):
#         raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")

#     token = authorization.replace("Bearer ", "")
#     try:
#         user_id = verifier.verify(token)
#     except ValueError:
#         raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")

#     # 2. Rate limiting (per user)
#     if not rate_limiter.is_allowed(user_id):
#         logger.info(f"user={user_id} | query='{payload.query}' | RATE_LIMITED")
#         raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment and try again.")

#     # 3. Input validation
#     if not payload.query.strip():
#         raise HTTPException(status_code=400, detail="Query cannot be empty.")
#     if len(payload.query) > 500:
#         raise HTTPException(status_code=400, detail="Query is too long.")

#     # 4. Process (budget check happens inside pipeline -> response_executor)
#     try:
#         pipeline = req.app.state.pipeline
#         result = pipeline.ask(payload.query)
#     except Exception as e:
#         logger.error(f"user={user_id} | query='{payload.query}' | ERROR: {e}")
#         raise HTTPException(status_code=503, detail="Assistant is temporarily unavailable. Please try again.")

#     latency = time.time() - start_time
#     logger.info(f"user={user_id} | query='{payload.query}' | tier={result['tier']} | latency={latency:.2f}s")

#     return ChatResponse(
#         answer=result["answer"]
#         # tier=result["tier"],
#         # source=result.get("source"),
#         # distance=result.get("distance")
#     )


# @app.get("/health")
# def health(req: Request):
#     pipeline = req.app.state.pipeline
#     return {
#         "status": "ok",
#         "providers": pipeline.executor.llm.manager.status()
#     }
@app.post("/api/bot/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, req: Request, authorization: str = Header(None)):
    start_time = time.time()
    # 1. Authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")

    token = authorization.replace("Bearer ", "")
    try:
        user_id = verifier.verify(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")

    # 2. Rate limiting (per user)
    if not rate_limiter.is_allowed(user_id):
        logger.info(f"user={user_id} | query='{payload.query}' | RATE_LIMITED")
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment and try again.")

    # 3. Input validation
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    if len(payload.query) > 500:
        raise HTTPException(status_code=400, detail="Query is too long.")

    # 4. Process (budget check happens inside pipeline -> response_executor)
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



