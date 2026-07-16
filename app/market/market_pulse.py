# app/market/market_pulse.py
"""
Aggregates the existing Nifty 50 signal matrix + one India VIX quote
into a small summary object for dashboard-style display.
"""

from app.market.upstox_client import UpstoxClient
import json as _json
from app.market.upstox_quote_client import UpstoxQuoteClient
from app.redis_client import get_redis

VIX_INSTRUMENT_KEY = "NSE_INDEX|India VIX"

# Adjustable thresholds — not official, just common trader convention.
VIX_LOW_THRESHOLD = 12
VIX_HIGH_THRESHOLD = 20


def _volatility_label(vix_value: float | None) -> str:
    if vix_value is None:
        return "UNKNOWN"
    if vix_value < VIX_LOW_THRESHOLD:
        return "LOW"
    elif vix_value < VIX_HIGH_THRESHOLD:
        return "MODERATE"
    return "HIGH"


def _market_mood(bullish: int, bearish: int, total: int) -> str:
    if total == 0:
        return "NEUTRAL"
    bullish_pct = bullish / total
    bearish_pct = bearish / total
    if bullish_pct >= 0.55:
        return "BULLISH"
    elif bearish_pct >= 0.55:
        return "BEARISH"
    return "NEUTRAL"


def fetch_vix_value() -> float | None:
    """Isolated so a VIX failure never breaks the rest of the pulse."""
    try:
        client = UpstoxQuoteClient()
        quote = client.fetch_quote_by_key(VIX_INSTRUMENT_KEY)
        return quote.get("last_price")
    except Exception as e:
        print(f"[MarketPulse] VIX fetch failed, continuing without it: {e}")
        return None


def compute_market_pulse(signal_matrix: list[dict]) -> dict:
    total = len(signal_matrix)
    bullish = sum(1 for e in signal_matrix if e["ai_signal"] in ("BUY", "STRONG BUY"))
    bearish = sum(1 for e in signal_matrix if e["ai_signal"] in ("SELL", "STRONG SELL"))
    neutral = total - bullish - bearish

    momentum = round(sum(e["score"] for e in signal_matrix) / total, 1) if total else 0

    sorted_by_score = sorted(signal_matrix, key=lambda e: e["score"], reverse=True)
    top_gainers = [
        {"symbol": e["symbol"], "score": e["score"], "ai_signal": e["ai_signal"]}
        for e in sorted_by_score[:3]
    ]
    top_losers = [
        {"symbol": e["symbol"], "score": e["score"], "ai_signal": e["ai_signal"]}
        for e in sorted_by_score[-3:][::-1]
    ]

    vix_value = fetch_vix_value()

    return {
        "mood": _market_mood(bullish, bearish, total),
        "breadth": {"bullish": bullish, "bearish": bearish, "neutral": neutral, "total": total},
        "volatility": {"label": _volatility_label(vix_value), "vix_value": vix_value},
        "momentum": momentum,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
    }


def refresh_vix_only():
    """Lightweight — updates only the volatility field, every 15 min during market hours."""
    r = get_redis()
    raw = r.get("market_pulse:nifty50") if r else None
    if not raw:
        return  # full pulse hasn't run yet today, nothing to patch

    pulse = _json.loads(raw)
    vix_value = fetch_vix_value()
    pulse["volatility"] = {"label": _volatility_label(vix_value), "vix_value": vix_value}

    if r:
        r.set("market_pulse:nifty50", _json.dumps(pulse))
        r.expire("market_pulse:nifty50", 20 * 3600)