# app/market/signal_engine.py
"""
Converts raw indicator math into exactly what the UI table needs:

  RSI, EMA, SMA, MACD, VWAP, ADX, ATR  → arrow only (bullish/bearish/neutral)
  AI Signal                            → label (STRONG BUY / BUY / HOLD / SELL / STRONG SELL)
  Conf.                                → 0-100 percentage (indicator agreement)
  Score                                → 0-100 number (direction + strength)

To add/remove/reweight an indicator later, edit INDICATOR_REGISTRY only.
Set weight=0 to keep an indicator's arrow visible but exclude it from
Score/Confidence math (used here for ATR, which measures volatility,
not direction).
"""
import math
from market_service.app.market.indicators import (
    calculate_rsi, calculate_macd, calculate_sma, calculate_ema,
    calculate_vwap, calculate_atr, calculate_adx
)

INDICATOR_REGISTRY = [
    {"name": "RSI",  "weight": 1.0},
    {"name": "EMA",  "weight": 1.0},
    {"name": "SMA",  "weight": 1.0},
    {"name": "MACD", "weight": 1.2},
    {"name": "VWAP", "weight": 1.0},
    {"name": "ADX",  "weight": 0.8},
    {"name": "ATR",  "weight": 0.0},   # volatility, not direction — arrow shown, excluded from scoring
]

_WEIGHTS = {i["name"]: i["weight"] for i in INDICATOR_REGISTRY}
_ACTIVE_TOTAL_WEIGHT = sum(w for w in _WEIGHTS.values() if w > 0)


def _vote_rsi(rsi: float) -> tuple[str, float]:
    if rsi > 55:
        return "bullish", min((rsi - 50) / 50, 1.0)
    if rsi < 45:
        return "bearish", min((50 - rsi) / 50, 1.0)
    return "neutral", 0.0


def _vote_price_vs_line(close: float, line_value: float) -> tuple[str, float]:
    if line_value == 0:
        return "neutral", 0.0
    pct_diff = (close - line_value) / line_value
    if pct_diff > 0.002:
        return "bullish", min(abs(pct_diff) * 20, 1.0)
    if pct_diff < -0.002:
        return "bearish", min(abs(pct_diff) * 20, 1.0)
    return "neutral", 0.0


def _vote_macd(macd_data: dict) -> tuple[str, float]:
    gap = macd_data["macd"] - macd_data["signal"]
    strength = min(abs(gap) / max(abs(macd_data["signal"]), 1e-6), 1.0)
    return ("bullish" if macd_data["bullish_crossover"] else "bearish"), strength


def _vote_adx(adx_data: dict) -> tuple[str, float]:
    adx_strength = min(adx_data["adx"] / 50, 1.0)
    if adx_data["plus_di"] > adx_data["minus_di"]:
        return "bullish", adx_strength
    if adx_data["minus_di"] > adx_data["plus_di"]:
        return "bearish", adx_strength
    return "neutral", 0.0


def _label_from_score(score: int) -> str:
    if score >= 85: return "STRONG BUY"
    if score >= 65: return "BUY"
    if score >= 35: return "HOLD"
    if score >= 15: return "SELL"
    return "STRONG SELL"


def _sign(direction: str) -> int:
    return {"bullish": 1, "bearish": -1, "neutral": 0}[direction]


def compute_signal_matrix(symbol: str, df) -> dict:
    """
    df: DataFrame with 'high', 'low', 'close', 'volume' columns.
    Returns ONLY what the table needs — arrows, ai_signal, confidence, score.
    Raw numeric values are NOT included (they're not meant to be
    displayed on a 0-100 scale, so we don't compute/return them here
    to keep the payload small — cheaper Redis storage, faster reads
    across ~500 symbols).
    """
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    current_price = float(close.iloc[-1])

    rsi_val = calculate_rsi(close)
    ema_val = calculate_ema(close, 20)
    sma_val = calculate_sma(close, 50)
    macd_val = calculate_macd(close)
    vwap_val = calculate_vwap(high, low, close, volume)
    adx_val = calculate_adx(high, low, close, 14)
    # ATR computed only if you later want to raise its weight above 0
    # (skipped here to save CPU across a 500-symbol scan since weight=0)

    votes = {
        "RSI":  _vote_rsi(rsi_val),
        "EMA":  _vote_price_vs_line(current_price, ema_val),
        "SMA":  _vote_price_vs_line(current_price, sma_val),
        "MACD": _vote_macd(macd_val),
        "VWAP": _vote_price_vs_line(current_price, vwap_val),
        "ADX":  _vote_adx(adx_val),
        "ATR":  ("neutral", 0.0),
    }

    weighted_sum = sum(
        _WEIGHTS[name] * _sign(direction) * strength
        for name, (direction, strength) in votes.items()
        if _WEIGHTS[name] > 0
    )
    normalized = weighted_sum / _ACTIVE_TOTAL_WEIGHT   # -1.0 to +1.0
    score = max(0, min(100, round((normalized + 1) / 2 * 100)))

    overall_sign = 1 if normalized > 0 else (-1 if normalized < 0 else 0)
    agreeing_weight = sum(
        _WEIGHTS[name]
        for name, (direction, _) in votes.items()
        if _WEIGHTS[name] > 0 and _sign(direction) == overall_sign and overall_sign != 0
    )
    confidence = round((agreeing_weight / _ACTIVE_TOTAL_WEIGHT) * 100) if overall_sign != 0 else 0

    return {
        "symbol": symbol,
        "arrows": {name: direction for name, (direction, _) in votes.items()},
        "ai_signal": _label_from_score(score),
        "confidence": confidence,
        "score": score,
    }


# ── NEW: Horizon-Aware Signal Engine (Phase 0.5) ──────────────────────────────
# This provides the exact same output format but adds multi-horizon weighting
# and ADTV liquidity filtering, without breaking older pipeline scripts that 
# still call compute_signal_matrix() above.

HORIZON_WEIGHTS = {
    "short": {
        "RSI": 1.0, "EMA": 1.0, "SMA": 1.0, "SMA100": 0.0, "SMA200": 0.0,
        "MACD": 1.2, "VWAP": 1.0, "ADX": 0.8, "ATR": 0.0
    },
    "mid": {
        "RSI": 0.8, "EMA": 0.5, "SMA": 1.2, "SMA100": 1.0, "SMA200": 0.0,
        "MACD": 1.0, "VWAP": 0.5, "ADX": 1.0, "ATR": 0.0
    },
    "long": {
        "RSI": 0.0, "EMA": 0.0, "SMA": 0.5, "SMA100": 1.2, "SMA200": 1.5,
        "MACD": 0.0, "VWAP": 0.0, "ADX": 0.8, "ATR": 0.0
    }
}

LIQUIDITY_THRESHOLDS_CR = {
    "short": 20.0,  # 20 Crores ADTV
    "mid": 10.0,    # 10 Crores ADTV
    "long": 5.0,    # 5 Crores ADTV
}



def compute_horizon_signal_matrix(symbol: str, df, horizon: str = "mid") -> dict:
    if horizon not in HORIZON_WEIGHTS:
        horizon = "mid"

    weights = HORIZON_WEIGHTS[horizon]

    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    current_price = float(close.iloc[-1])

    adtv = (close * volume).tail(20).mean()
    adtv_cr = adtv / 10_000_000
    is_liquid = adtv_cr >= LIQUIDITY_THRESHOLDS_CR[horizon]

    rsi_val = calculate_rsi(close)
    ema_val = calculate_ema(close, 20)
    sma_val = calculate_sma(close, 50)
    sma100_val = calculate_sma(close, 100)
    sma200_val = calculate_sma(close, 200)
    macd_val = calculate_macd(close)
    vwap_val = calculate_vwap(high, low, close, volume)
    adx_val = calculate_adx(high, low, close, 14)

    # Track which line-based values are actually available (not NaN) BEFORE
    # voting — this is what determines whether an indicator's weight counts,
    # not what direction its vote happens to land on.
    raw_values = {
        "RSI": rsi_val, "EMA": ema_val, "SMA": sma_val,
        "SMA100": sma100_val, "SMA200": sma200_val,
        "MACD": macd_val["macd"], "VWAP": vwap_val, "ADX": adx_val["adx"],
        "ATR": 0.0,  # always excluded via weight=0 anyway
    }
    available = {name: not (isinstance(v, float) and math.isnan(v)) for name, v in raw_values.items()}

    votes = {
        "RSI":  _vote_rsi(rsi_val),
        "EMA":  _vote_price_vs_line(current_price, ema_val),
        "SMA":  _vote_price_vs_line(current_price, sma_val),
        "SMA100": _vote_price_vs_line(current_price, sma100_val),
        "SMA200": _vote_price_vs_line(current_price, sma200_val),
        "MACD": _vote_macd(macd_val),
        "VWAP": _vote_price_vs_line(current_price, vwap_val),
        "ADX":  _vote_adx(adx_val),
        "ATR":  ("neutral", 0.0),
    }

    # Effective weight excludes both weight=0 indicators AND indicators with
    # no real data — this is the actual fix. Previously active_total_weight
    # only checked `weights[name] > 0`, which let a NaN-backed "neutral"
    # vote quietly dilute the score with a weight that should not have
    # counted at all.
    active_total_weight = sum(
        w for name, w in weights.items() if w > 0 and available.get(name, True)
    )

    if active_total_weight == 0:
        return {
            "symbol": symbol, "score": 50, "ai_signal": "HOLD", "confidence": 0,
            "is_liquid": is_liquid, "adtv_cr": round(adtv_cr, 2),
            "horizon": horizon, "insufficient_data": True,
        }

    weighted_sum = sum(
        weights[name] * _sign(direction) * strength
        for name, (direction, strength) in votes.items()
        if weights[name] > 0 and available.get(name, True)
    )
    normalized = weighted_sum / active_total_weight
    score = max(0, min(100, round((normalized + 1) / 2 * 100)))

    overall_sign = 1 if normalized > 0 else (-1 if normalized < 0 else 0)
    agreeing_weight = sum(
        weights[name]
        for name, (direction, _) in votes.items()
        if weights[name] > 0 and available.get(name, True)
        and _sign(direction) == overall_sign and overall_sign != 0
    )
    confidence = round((agreeing_weight / active_total_weight) * 100) if overall_sign != 0 else 0

    return {
        "symbol": symbol,
        "arrows": {name: direction for name, (direction, _) in votes.items()},
        "ai_signal": _label_from_score(score),
        "confidence": confidence,
        "score": score,
        "is_liquid": is_liquid,
        "adtv_cr": round(adtv_cr, 2),
        "horizon": horizon,
        "insufficient_data": any(not available.get(n, True) for n, w in weights.items() if w > 0),
    }