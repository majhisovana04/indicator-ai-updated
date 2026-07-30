# app/api/server.py
import psutil, os
print(f"[MEM] process start (before any app imports): {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB", flush=True)

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core_shared.auth.token_verifier import TokenVerifier
from core_shared.auth.redis_rate_limiter import RedisRateLimiter
from core_shared.schemas import SignalMatrixResponse
from core_shared.redis_client import get_redis
import json
from datetime import datetime, timezone


import time
from core_shared.logging_setup import logger
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Indicator AI Assistant")

# Security scheme — enables the 🔓 Authorize button in Swagger UI
bearer_scheme = HTTPBearer(auto_error=False)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # placeholder — update once frontend confirms their dev URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Market Endpoints below
verifier = TokenVerifier()
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

@app.get("/api/rankings/{exchange}")
def get_rankings(
    exchange: str,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    authorization: str = Header(None),
):
    """
    Returns the top 10 ranked stocks for short, mid, and long horizons.
    exchange must be 'nse' or 'bse'.
    """
    exchange = exchange.upper()
    if exchange not in ["NSE", "BSE"]:
        raise HTTPException(status_code=400, detail="Invalid exchange. Must be 'nse' or 'bse'.")

    # 1. Authentication
    if credentials:
        authorization = f"Bearer {credentials.credentials}"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")
    token = authorization.replace("Bearer ", "")
    try:
        verifier.verify(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")

    # 2. Fetch from Redis
    r = get_redis()
    raw = r.get(f"rankings:{exchange}") if r else None
    if not raw:
        raise HTTPException(status_code=404, detail=f"Rankings for {exchange} not ready yet. Please run the daily pipeline.")

    # 3. Return JSON payload
    data = json.loads(raw)
    updated_at = datetime.fromisoformat(data["updated_at"])
    age_hours = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600
    data["stale"] = age_hours > 24  # surface this to the frontend explicitly

    return data

@app.get("/health")
def health(req: Request):
    return {
        "status": "ok"
    }

