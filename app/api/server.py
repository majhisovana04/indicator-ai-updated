# app/api/server.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header
from app.pipeline import AssistantPipeline
from app.api.schemas import ChatRequest, ChatResponse
from app.market.background_refresher import start_scheduler
from app.auth.token_verifier import TokenVerifier
from app.auth.rate_limiter import RateLimiter

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts
    start_scheduler()
    yield
    # Runs once when the server shuts down (nothing needed here for now)


app = FastAPI(title="Indicator AI Assistant", lifespan=lifespan)

# Load the pipeline ONCE when the server starts — not every time
# someone asks a question. Loading the embedding model + FAISS index
# is slow, so we don't want to repeat it per request.
pipeline = AssistantPipeline()
verifier = TokenVerifier()
rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

@app.post("/api/bot/chat", response_model=ChatResponse)
def chat(request: ChatRequest, authorization: str = Header(None)):
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
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment and try again.")

    # 3. Input validation
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    if len(request.query) > 500:
        raise HTTPException(status_code=400, detail="Query is too long.")

    # 4. Process (budget check happens inside pipeline -> response_executor)
    try:
        result = pipeline.ask(request.query)
    except Exception:
        raise HTTPException(status_code=503, detail="Assistant is temporarily unavailable. Please try again.")

    return ChatResponse(
        answer=result["answer"]
        # tier=result["tier"],
        # source=result.get("source"),
        # distance=result.get("distance")
    )


@app.get("/health")
def health():
    return {"status": "ok"}


