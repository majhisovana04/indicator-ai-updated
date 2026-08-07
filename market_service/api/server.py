# app/api/server.py
import psutil, os
print(f"[MEM] process start (before any app imports): {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.1f} MB", flush=True)

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.responses import JSONResponse
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


def fetch_frequent_sync(state_cache):
    try:
        r = get_redis()
        if r:
            sm_raw = r.get("signal_matrix:nifty50")
            if sm_raw: state_cache["signal_matrix"] = json.loads(sm_raw)
            
            mp_raw = r.get("market_pulse:nifty50")
            if mp_raw: state_cache["market_pulse"] = json.loads(mp_raw)
    except Exception as e:
        print(f"[Cache Poller] Error polling frequent data: {e}")

def fetch_infrequent_sync(state_cache):
    try:
        r = get_redis()
        if r:
            nse_raw = r.get("rankings:NSE")
            if nse_raw: state_cache["rankings_NSE"] = json.loads(nse_raw)
            
            bse_raw = r.get("rankings:BSE")
            if bse_raw: state_cache["rankings_BSE"] = json.loads(bse_raw)
    except Exception as e:
        print(f"[Cache Poller] Error polling infrequent data: {e}")

async def poll_frequent(state_cache):
    while True:
        await asyncio.to_thread(fetch_frequent_sync, state_cache)
        await asyncio.sleep(300) # 5 minutes

async def poll_infrequent(state_cache):
    while True:
        await asyncio.to_thread(fetch_infrequent_sync, state_cache)
        await asyncio.sleep(3600) # 1 hour

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the global cache
    app.state.cache = {
        "signal_matrix": None,
        "market_pulse": None,
        "rankings_NSE": None,
        "rankings_BSE": None
    }
    
    # Start background polling tasks
    task1 = asyncio.create_task(poll_frequent(app.state.cache))
    task2 = asyncio.create_task(poll_infrequent(app.state.cache))
    
    yield
    
    # Clean up on shutdown
    task1.cancel()
    task2.cancel()


app = FastAPI(title="Indicator AI Assistant", lifespan=lifespan)

# Security scheme — enables the 🔓 Authorize button in Swagger UI
bearer_scheme = HTTPBearer(auto_error=False)

from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # placeholder — update once frontend confirms their dev URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Market Endpoints below
verifier = TokenVerifier()

def _verify_auth(credentials, authorization):
    if credentials:
        authorization = f"Bearer {credentials.credentials}"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")
    token = authorization.replace("Bearer ", "")
    try:
        verifier.verify(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")

def empty_cache_response():
    return JSONResponse(
        status_code=202,
        content={
            "status": "processing",
            "message": "Market data is currently being fetched. Please wait.",
            "data": None
        }
    )

@app.get("/api/signal-matrix")
def signal_matrix(
    request: Request,
    search: str | None = None,
    symbols: str | None = None,   # comma-separated, e.g. "NSE:RELIANCE,NSE:TCS"
    page: int = 1,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    authorization: str = Header(None),
):
    _verify_auth(credentials, authorization)

    all_entries = request.app.state.cache["signal_matrix"]
    if not all_entries:
        return empty_cache_response()

    if symbols:
        wanted = {s.strip().upper() for s in symbols.split(",")}
        all_entries = [e for e in all_entries if e["symbol"].upper() in wanted]
    elif search:
        term = search.strip().upper()
        all_entries = [e for e in all_entries if term in e["symbol"].upper()]

    total = len(all_entries)
    start_idx = (page - 1) * limit
    page_entries = all_entries[start_idx:start_idx + limit]

    # Return standard SignalMatrixResponse format but as a dict directly, 
    # since FastAPI will convert it, bypassing Pydantic overhead on fast reads.
    return {"count": total, "results": page_entries}


@app.get("/api/market-pulse")
def market_pulse(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    authorization: str = Header(None),
):
    _verify_auth(credentials, authorization)

    pulse_data = request.app.state.cache["market_pulse"]
    if not pulse_data:
        return empty_cache_response()

    return pulse_data


@app.get("/api/rankings/{exchange}")
def get_rankings(
    exchange: str,
    request: Request,
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

    _verify_auth(credentials, authorization)

    rankings_data = request.app.state.cache.get(f"rankings_{exchange}")
    if not rankings_data:
        return empty_cache_response()

    # Deep copy before modifying to avoid corrupting the global cache
    import copy
    data = copy.deepcopy(rankings_data)
    
    updated_at = datetime.fromisoformat(data["updated_at"])
    age_hours = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600
    data["stale"] = age_hours > 24  # surface this to the frontend explicitly

    return data


@app.get("/health")
def health(req: Request):
    return {
        "status": "ok"
    }

