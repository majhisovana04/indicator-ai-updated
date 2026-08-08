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


# --- OLD BACKGROUND POLLING (Commented out per user request) ---
# def fetch_frequent_sync(state_cache):
#     try:
#         r = get_redis()
#         if r:
#             sm_raw = r.get("signal_matrix:nifty50")
#             if sm_raw: state_cache["signal_matrix"] = json.loads(sm_raw)
#             
#             mp_raw = r.get("market_pulse:nifty50")
#             if mp_raw: state_cache["market_pulse"] = json.loads(mp_raw)
#     except Exception as e:
#         print(f"[Cache Poller] Error polling frequent data: {e}")
# 
# def fetch_infrequent_sync(state_cache):
#     try:
#         r = get_redis()
#         if r:
#             nse_raw = r.get("rankings:NSE")
#             if nse_raw: state_cache["rankings_NSE"] = json.loads(nse_raw)
#             
#             bse_raw = r.get("rankings:BSE")
#             if bse_raw: state_cache["rankings_BSE"] = json.loads(bse_raw)
#     except Exception as e:
#         print(f"[Cache Poller] Error polling infrequent data: {e}")
# 
# async def poll_frequent(state_cache):
#     while True:
#         await asyncio.to_thread(fetch_frequent_sync, state_cache)
#         await asyncio.sleep(300) # 5 minutes
# 
# async def poll_infrequent(state_cache):
#     while True:
#         await asyncio.to_thread(fetch_infrequent_sync, state_cache)
#         await asyncio.sleep(3600) # 1 hour
# 
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # Initialize the global cache
#     app.state.cache = {
#         "signal_matrix": None,
#         "market_pulse": None,
#         "rankings_NSE": None,
#         "rankings_BSE": None
#     }
#     
#     # Start background polling tasks
#     task1 = asyncio.create_task(poll_frequent(app.state.cache))
#     task2 = asyncio.create_task(poll_infrequent(app.state.cache))
#     
#     yield
#     
#     # Clean up on shutdown
#     task1.cancel()
#     task2.cancel()
# ----------------------------------------------------------------

import threading

class TTLCache:
    """
    Minimal thread-safe cache: serves from memory if fresh, otherwise
    fetches once and updates. Correct under 1 process or 100.
    """
    def __init__(self, fetch_fn, ttl_seconds: float):
        self._fetch_fn = fetch_fn
        self._ttl = ttl_seconds
        self._value = None
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def get(self):
        now = time.monotonic()
        if self._value is not None and (now - self._fetched_at) < self._ttl:
            return self._value
        with self._lock:
            now = time.monotonic()
            if self._value is None or (now - self._fetched_at) >= self._ttl:
                self._value = self._fetch_fn()
                self._fetched_at = now
        return self._value

def _fetch_rankings(exchange: str):
    r = get_redis()
    if r:
        raw = r.get(f"rankings:{exchange}")
        return json.loads(raw) if raw else None
    return None

def _fetch_signal_matrix():
    r = get_redis()
    if r:
        raw = r.get("signal_matrix:nifty50")
        return json.loads(raw) if raw else None
    return None

def _fetch_market_pulse():
    r = get_redis()
    if r:
        raw = r.get("market_pulse:nifty50")
        return json.loads(raw) if raw else None
    return None

rankings_nse_cache = TTLCache(lambda: _fetch_rankings("NSE"), ttl_seconds=300)
rankings_bse_cache = TTLCache(lambda: _fetch_rankings("BSE"), ttl_seconds=300)
signal_matrix_cache = TTLCache(lambda: _fetch_signal_matrix(), ttl_seconds=300)
market_pulse_cache = TTLCache(lambda: _fetch_market_pulse(), ttl_seconds=300)


app = FastAPI(title="Indicator AI Assistant")

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

    all_entries = signal_matrix_cache.get()
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

    pulse_data = market_pulse_cache.get()
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

    cache = rankings_nse_cache if exchange == "NSE" else rankings_bse_cache
    rankings_data = cache.get()
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

