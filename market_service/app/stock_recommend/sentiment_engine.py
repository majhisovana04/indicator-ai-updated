"""
market_service/app/stock_recommend/sentiment_engine.py

Stage 5.5 — Sentiment Score Engine

Three independent fetchers:
  - fetch_fii_dii_signal()          : market-wide FII/DII net flow score
  - fetch_oi_trend(symbol, mapper)  : per-stock OI delta score (F&O stocks only)
  - fetch_news_sentiment(symbol, ..) : per-stock news sentiment via Gemini

All three return float | None. None = signal unavailable (data missing, API
down, cash-only stock, etc.). The composite function renormalizes weights over
whatever signals ARE present — missing signals never crash the pipeline.
"""

import os
import json
import time
import gzip
import io
import requests
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from core_shared.redis_client import get_redis
from market_service.app.market.instrument_mapper import InstrumentMapper

# ── NSE session headers ──────────────────────────────────────────────────────
_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

# Upstox API headers (token loaded once at module level)
_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "")
_UPSTOX_HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {_ACCESS_TOKEN}",
}

# Redis TTL for OI snapshots — 2 days covers weekends
_OI_SNAPSHOT_TTL = 2 * 24 * 3600


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 1: FII/DII Flow (market-wide)
# ─────────────────────────────────────────────────────────────────────────────

def _get_nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_NSE_HEADERS)
    session.get("https://www.nseindia.com", timeout=15)
    return session


def fetch_fii_dii_signal() -> float | None:
    """
    Fetches today's FII/DII net flow from NSE and returns a composite
    score in [-1.0, +1.0].

    Positive = net institutional buying (bullish), Negative = net selling.
    Returns None on any fetch failure — caller treats missing as neutral.
    """
    try:
        session = _get_nse_session()
        resp = session.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=10)
        resp.raise_for_status()
        data = resp.json()

        fii_net = 0.0
        dii_net = 0.0
        for item in data:
            category = item.get("category", "").upper()
            try:
                net = float(item.get("netValue", 0))
            except (ValueError, TypeError):
                net = 0.0

            if "FII" in category or "FPI" in category:
                fii_net = net
            elif "DII" in category:
                dii_net = net

        # Combine — both carry equal weight in the market-wide signal
        combined = fii_net + dii_net

        # Normalize: ±5000 crore is treated as a "max signal" day
        # Values beyond that are clamped to ±1.0
        MAX_FLOW = 5000.0
        score = max(-1.0, min(1.0, combined / MAX_FLOW))
        return round(score, 4)

    except Exception as e:
        print(f"  [sentiment] FII/DII fetch failed: {e}")
        return None


def store_fii_dii_today() -> None:
    """
    Fetches today's FII/DII and appends it to a Redis rolling list
    (max 30 entries = ~30 trading days). Called by the scheduler at 7:05 PM IST.
    """
    score = fetch_fii_dii_signal()
    if score is None:
        print("  [sentiment] FII/DII store skipped — fetch returned None")
        return

    r = get_redis()
    if r is None:
        print("  [sentiment] FII/DII store skipped — Redis unavailable")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    entry = json.dumps({"date": today_str, "score": score})

    r.lpush("fii_dii:history", entry)   # prepend newest entry
    r.ltrim("fii_dii:history", 0, 29)   # keep max 30 entries
    print(f"  [sentiment] FII/DII stored for {today_str}: score={score}")


def _get_fii_dii_rolling_score() -> float:
    """
    Returns the rolling average FII/DII score from Redis history.
    Falls back to today's live fetch if history is empty.
    Returns 0.0 (neutral) if everything fails.
    """
    r = get_redis()
    if r:
        raw_list = r.lrange("fii_dii:history", 0, 29)
        if raw_list:
            scores = []
            for raw in raw_list:
                try:
                    entry = json.loads(raw)
                    scores.append(float(entry["score"]))
                except Exception:
                    pass
            if scores:
                return round(sum(scores) / len(scores), 4)

    # Fallback: fetch live
    return fetch_fii_dii_signal() or 0.0


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 2: Open Interest Trend (per-stock, F&O only)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_oi_trend(symbol: str, mapper: InstrumentMapper) -> float | None:
    """
    Fetches the current OI for the stock's near-month futures contract and
    compares it to yesterday's OI snapshot stored in Redis.

    OI buildup classification:
      Price ↑ + OI ↑ = Long Buildup    → +1.0
      Price ↓ + OI ↑ = Short Buildup   → -1.0
      Price ↑ + OI ↓ = Short Covering  → +0.4
      Price ↓ + OI ↓ = Long Unwinding  → -0.4

    Returns None for cash-only stocks or on any fetch failure.
    """
    fut_key = mapper.get_futures_key(symbol)
    if fut_key is None:
        return None  # cash-only stock — no OI signal

    try:
        url = "https://api.upstox.com/v2/market-quote/quotes"
        resp = requests.get(url, headers=_UPSTOX_HEADERS,
                            params={"instrument_key": fut_key}, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        if not data:
            return None

        quote = next(iter(data.values()))
        current_oi = float(quote.get("oi", 0) or 0)
        current_price = float(quote.get("last_price", 0) or 0)

        if current_oi == 0 or current_price == 0:
            return None

        # ── Save today's snapshot to Redis for tomorrow's delta ──
        r = get_redis()
        redis_key = f"oi_snapshot:{symbol}"
        yesterday_oi = None
        yesterday_price = None

        if r:
            raw = r.get(redis_key)
            if raw:
                try:
                    snap = json.loads(raw)
                    yesterday_oi = float(snap.get("oi", 0))
                    yesterday_price = float(snap.get("price", 0))
                except Exception:
                    pass
            # Save today AFTER reading yesterday's values
            r.set(redis_key, json.dumps({"oi": current_oi, "price": current_price}),
                  ex=_OI_SNAPSHOT_TTL)

        if yesterday_oi is None or yesterday_oi == 0:
            # No previous snapshot yet — can't compute delta, return None
            # (will work correctly from Day 2 onwards)
            return None

        oi_up = current_oi > yesterday_oi
        price_up = (current_price >= yesterday_price) if yesterday_price else True

        # Classify buildup
        if price_up and oi_up:
            return 1.0    # Long Buildup — strongly bullish
        elif not price_up and oi_up:
            return -1.0   # Short Buildup — strongly bearish
        elif price_up and not oi_up:
            return 0.4    # Short Covering — weakly bullish
        else:
            return -0.4   # Long Unwinding — weakly bearish

    except Exception as e:
        print(f"  [sentiment] OI fetch failed for {symbol}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL 3: News Sentiment via Gemini (per-stock)
# ─────────────────────────────────────────────────────────────────────────────

# ── VADER pre-filter (free, offline, no LLM needed) ─────────────────────────
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _vader = SentimentIntensityAnalyzer()
    _VADER_AVAILABLE = True
except ImportError:
    _vader = None
    _VADER_AVAILABLE = False

_VADER_CONFIDENCE_THRESHOLD = 0.5   # |compound| >= this → trust VADER, skip LLM
_NEWS_BATCH_SIZE = 15                # stocks per LLM call


def _vader_score(headlines: list[str]) -> float | None:
    """Returns VADER compound score if confident enough, else None (→ needs LLM)."""
    if not _VADER_AVAILABLE or not headlines:
        return None
    scores = [_vader.polarity_scores(h)["compound"] for h in headlines]
    avg = sum(scores) / len(scores)
    if abs(avg) >= _VADER_CONFIDENCE_THRESHOLD:
        return round(avg, 4)
    return None  # ambiguous — needs LLM


def fetch_news_for_symbols(
    symbols: list[str],
    mapper: InstrumentMapper,
) -> dict[str, list[dict]]:
    """
    Fetches news articles for a list of symbols in a SINGLE Upstox batch call.
    Returns {composite_symbol: [article, ...]} — missing symbols return [].
    """
    key_to_symbol: dict[str, str] = {}
    for sym in symbols:
        try:
            key_to_symbol[mapper.get_instrument_key(sym)] = sym
        except ValueError:
            pass

    if not key_to_symbol:
        return {}

    try:
        all_news_data = {}
        all_keys = list(key_to_symbol.keys())
        chunk_size = 15
        
        for i in range(0, len(all_keys), chunk_size):
            chunk_keys = all_keys[i:i + chunk_size]
            resp = requests.get(
                "https://api.upstox.com/v2/news",
                headers=_UPSTOX_HEADERS,
                params={
                    "category": "instrument_keys",
                    "instrument_keys": ",".join(chunk_keys),
                },
                timeout=15,
            )
            resp.raise_for_status()
            chunk_data = resp.json().get("data", {})
            all_news_data.update(chunk_data)
            time.sleep(1)  # Polite delay between chunked API calls
            
        # Map instrument_key → symbol, then build symbol → articles
        return {key_to_symbol[k]: v for k, v in all_news_data.items() if k in key_to_symbol}
    except Exception as e:
        print(f"  [sentiment] Batch news fetch failed: {e}")
        return {}


def score_news_batch_llm(
    stocks_with_news: list[dict],
) -> dict[str, float]:
    """
    Scores a batch of stocks via a single LLM call.
    stocks_with_news: [{"symbol": "NSE:RELIANCE", "headlines": ["...", ...]}, ...]
    Returns {symbol: score} for stocks that LLM successfully scored.
    """
    if not stocks_with_news:
        return {}

    import re
    blocks = []
    for s in stocks_with_news:
        sym_short = s["symbol"].split(":")[-1]
        lines = "\n".join(f"  - {h}" for h in s["headlines"][:3])
        blocks.append(f"{sym_short}:\n{lines}")

    prompt = (
        "You are a stock market analyst. For each stock below, score the recent "
        "news sentiment from -1.0 (very bearish) to +1.0 (very bullish).\n"
        "Return ONLY a single JSON object mapping the stock symbol to its score.\n"
        "Example: {\"RELIANCE\": 0.6, \"TCS\": -0.2, \"HDFC\": 0.1}\n\n"
        + "\n\n".join(blocks)
        + "\n\nReturn only valid JSON. No explanation."
    )

    try:
        from chatbot_service.app.generation.llm_provider_manager import LLMProviderManager
        llm = LLMProviderManager()
        raw = llm.generate(prompt)

        json_match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
        if not json_match:
            return {}
        parsed = json.loads(json_match.group())

        # Map short symbol back to composite (e.g. "RELIANCE" → "NSE:RELIANCE")
        short_to_full = {s["symbol"].split(":")[-1]: s["symbol"] for s in stocks_with_news}
        result = {}
        for short_sym, score in parsed.items():
            full_sym = short_to_full.get(short_sym)
            if full_sym:
                result[full_sym] = max(-1.0, min(1.0, float(score)))
        return result

    except Exception as e:
        print(f"  [sentiment] Batch LLM scoring failed: {e}")
        return {}


def compute_news_scores_for_shortlist(
    symbols: list[str],
    mapper: InstrumentMapper,
) -> dict[str, float | None]:
    """
    Main entry point for news sentiment on the shortlist.

    Flow per stock:
      1. Fetch all news in one Upstox batch call (already done outside)
      2. VADER pre-filter: confident headlines → score immediately, no LLM
      3. Ambiguous headlines → collect for batch LLM scoring
      4. LLM scores batches of 15 ambiguous stocks → 3-6 calls total

    Returns {composite_symbol: score | None}
    """
    # Step 1: Deduplicate symbols by underlying to avoid fetching/scoring twice for BSE/NSE
    underlying_to_rep_sym = {}
    for sym in symbols:
        underlying = sym.split(":", 1)[1] if ":" in sym else sym
        if underlying not in underlying_to_rep_sym:
            underlying_to_rep_sym[underlying] = sym

    rep_symbols = list(underlying_to_rep_sym.values())

    print(f"  [news] Fetching news for {len(rep_symbols)} unique companies (from {len(symbols)} shortlisted rows)...")
    news_map = fetch_news_for_symbols(rep_symbols, mapper)
    print(f"  [news] News returned for {len(news_map)}/{len(rep_symbols)} companies")

    rep_scores: dict[str, float | None] = {}
    needs_llm: list[dict] = []  # stocks VADER couldn't confidently score

    # Step 2: VADER pre-filter
    for sym in rep_symbols:
        articles = news_map.get(sym, [])
        if not articles:
            rep_scores[sym] = None
            continue

        headlines = [a.get("heading", "") for a in articles[:5] if a.get("heading")]
        vader_result = _vader_score(headlines)

        if vader_result is not None:
            rep_scores[sym] = vader_result  # VADER is confident — no LLM needed
        else:
            rep_scores[sym] = None          # placeholder — will be filled by LLM
            needs_llm.append({"symbol": sym, "headlines": headlines})

    vader_count = sum(1 for s in rep_symbols if rep_scores.get(s) is not None)
    print(f"  [news] VADER scored {vader_count} companies, {len(needs_llm)} need LLM")

    # Step 3: Batch LLM scoring for ambiguous stocks
    for batch_start in range(0, len(needs_llm), _NEWS_BATCH_SIZE):
        batch = needs_llm[batch_start: batch_start + _NEWS_BATCH_SIZE]
        print(f"  [news] LLM batch {batch_start // _NEWS_BATCH_SIZE + 1}: {len(batch)} companies...")
        llm_scores = score_news_batch_llm(batch)
        rep_scores.update(llm_scores)

    # Step 4: Broadcast scores back to all original symbols (NSE and BSE)
    final_scores = {}
    for sym in symbols:
        underlying = sym.split(":", 1)[1] if ":" in sym else sym
        rep_sym = underlying_to_rep_sym[underlying]
        final_scores[sym] = rep_scores.get(rep_sym)

    return final_scores



# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITE: combine all 3 signals with renormalization
# ─────────────────────────────────────────────────────────────────────────────

def compute_sentiment_score(
    symbol: str,
    mapper: InstrumentMapper,
    fii_dii_score: float | None = None,
    news_score: float | None = None,
    oi_cache: dict | None = None,
    underlying: str | None = None,
) -> dict:
    """
    Combines all three sentiment signals into a single composite score.

    fii_dii_score: pass in a pre-fetched value to avoid N redundant NSE calls
                   (fetch once, share across all stocks in the pipeline).
    news_score:    pass in the pre-computed news sentiment score for this stock.

    Returns:
        {
            "score": float,       # -1.0 to +1.0, normalized, 0.0 if all None
            "fii_dii": str,       # label for display
            "oi_trend": str,      # label for display
            "news": str,          # label for display
            "signals_used": int   # how many of the 3 signals contributed
        }
    """
    # ── Fetch each signal ────────────────────────────────────────────────────
    fii = fii_dii_score if fii_dii_score is not None else _get_fii_dii_rolling_score()

    # OI: use cache to avoid duplicate Upstox calls for dual-listed stocks
    if oi_cache is not None and underlying is not None:
        if underlying not in oi_cache:
            oi_cache[underlying] = fetch_oi_trend(symbol, mapper)
        oi = oi_cache[underlying]
    else:
        oi = fetch_oi_trend(symbol, mapper)

    news = news_score

    # ── Assign display labels ────────────────────────────────────────────────
    def _label(score: float | None, thresholds=(0.2, -0.2)) -> str:
        if score is None:
            return "N/A"
        if score >= thresholds[0]:
            return "Bullish"
        elif score <= thresholds[1]:
            return "Bearish"
        return "Neutral"

    # ── OI trend label ───────────────────────────────────────────────────────
    def _oi_label(score: float | None) -> str:
        if score is None:
            return "N/A"
        if score >= 0.8:
            return "Long Buildup"
        elif score <= -0.8:
            return "Short Buildup"
        elif score > 0:
            return "Short Covering"
        return "Long Unwinding"

    # ── Renormalize weights over available signals ───────────────────────────
    # Base weights: FII/DII=40%, OI=40%, News=20%
    signals = [
        (fii,  0.40),
        (oi,   0.40),
        (news, 0.20),
    ]
    available = [(val, w) for val, w in signals if val is not None]

    if not available:
        composite = 0.0
    else:
        total_weight = sum(w for _, w in available)
        composite = sum(val * (w / total_weight) for val, w in available)
        composite = round(max(-1.0, min(1.0, composite)), 4)

    return {
        "score": composite,
        "fii_dii": _label(fii),
        "oi_trend": _oi_label(oi),
        "news": _label(news),
        "signals_used": len(available),
    }
