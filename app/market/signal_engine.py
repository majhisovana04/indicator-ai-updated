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

from app.market.indicators import (
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