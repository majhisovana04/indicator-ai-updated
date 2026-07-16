# app/api/server.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.pipeline import AssistantPipeline
from app.api.schemas import ChatRequest, ChatResponse
from app.auth.token_verifier import TokenVerifier
from app.api.schemas import SignalMatrixResponse
from app.redis_client import get_redis
import json


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

# Security scheme — enables the 🔓 Authorize button in Swagger UI
bearer_scheme = HTTPBearer(auto_error=False)
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
@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, req: Request,
         credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
         authorization: str = Header(None)):
    # Support both Swagger's HTTPBearer (Authorize button) and raw Authorization header
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


@app.get("/api/signal-matrix", response_model=SignalMatrixResponse)
def signal_matrix(
    search: str | None = None,
    symbols: str | None = None,   # comma-separated, e.g. "NSE:RELIANCE,NSE:TCS"
    page: int = 1,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    authorization: str = Header(None),
):
    if credentials:
        authorization = f"Bearer {credentials.credentials}"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")
    token = authorization.replace("Bearer ", "")
    try:
        verifier.verify(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")

    r = get_redis()
    raw = r.get("signal_matrix:nifty50") if r else None
    if not raw:
        raise HTTPException(status_code=503, detail="Signal matrix not ready yet. Please check back shortly.")

    all_entries = json.loads(raw)

    if symbols:
        wanted = {s.strip().upper() for s in symbols.split(",")}
        all_entries = [e for e in all_entries if e["symbol"].upper() in wanted]
    elif search:
        term = search.strip().upper()
        all_entries = [e for e in all_entries if term in e["symbol"].upper()]

    total = len(all_entries)
    start_idx = (page - 1) * limit
    page_entries = all_entries[start_idx:start_idx + limit]

    return SignalMatrixResponse(count=total, results=page_entries)



@app.get("/api/market-pulse")
def market_pulse(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    authorization: str = Header(None),
):
    if credentials:
        authorization = f"Bearer {credentials.credentials}"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")
    token = authorization.replace("Bearer ", "")
    try:
        verifier.verify(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")

    r = get_redis()
    raw = r.get("market_pulse:nifty50") if r else None
    if not raw:
        raise HTTPException(status_code=503, detail="Market pulse not ready yet. Please check back shortly.")

    return json.loads(raw)

@app.get("/health")
def health(req: Request):
    pipeline = req.app.state.pipeline
    return {
        "status": "ok",
        "providers": pipeline.executor.llm.manager.status()
    }


