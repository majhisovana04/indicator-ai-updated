# app/market/indicators.py
import pandas as pd
import numpy as np


# def calculate_rsi(close_prices: pd.Series, period: int = 14) -> float:
#     delta = close_prices.diff()
#     gain = delta.where(delta > 0, 0)
#     loss = -delta.where(delta < 0, 0)

#     avg_gain = gain.rolling(window=period).mean()
#     avg_loss = loss.rolling(window=period).mean()

#     rs = avg_gain / avg_loss
#     rsi = 100 - (100 / (1 + rs))
#     return round(rsi.iloc[-1], 2)

def calculate_rsi(close_prices: pd.Series, period: int = 14) -> float:
    delta = close_prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    # Wilder's smoothing, not a plain rolling mean — a hard 14-day window
    # reacts too fast and swings too far, which is why RSI was reading
    # further from 50 than TradingView/Moneycontrol on every stock tested.
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi.iloc[-1], 2)


def calculate_macd(close_prices: pd.Series):
    ema12 = close_prices.ewm(span=12, adjust=False).mean()
    ema26 = close_prices.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()

    return {
        "macd": round(macd_line.iloc[-1], 2),
        "signal": round(signal_line.iloc[-1], 2),
        "bullish_crossover": macd_line.iloc[-1] > signal_line.iloc[-1]
    }

def calculate_sma(close_prices: pd.Series, period: int = 50) -> float:
    return round(close_prices.rolling(window=period).mean().iloc[-1], 2)

# app/market/indicators.py — add this function
def check_liquidity(volume_series, min_avg_volume: int = 10000) -> dict:
    avg_volume = volume_series.mean()
    is_liquid = avg_volume >= min_avg_volume

    return {
        "is_liquid": is_liquid,
        "avg_volume": round(avg_volume, 0),
        "reason": None if is_liquid else (
            f"This stock has low average trading volume (~{int(avg_volume):,} shares/day), "
            f"which makes technical indicators like RSI and MACD unreliable — "
            f"there isn't enough trading activity to produce a meaningful signal."
        )
    }

# ── NEW: EMA ─────────────────────────────────────────────────────
def calculate_ema(close_prices: pd.Series, period: int = 20) -> float:
    """Exponential Moving Average — more weight on recent prices than SMA."""
    ema = close_prices.ewm(span=period, adjust=False).mean()
    return round(ema.iloc[-1], 2)


# ── NEW: VWAP ────────────────────────────────────────────────────
def calculate_vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> float:
    """
    Volume-Weighted Average Price, computed over the whole lookback window
    (this is a "session-style" VWAP approximation for daily-candle data,
    not true intraday VWAP which resets every trading day).
    """
    typical_price = (high + low + close) / 3
    cumulative_pv = (typical_price * volume).sum()
    cumulative_vol = volume.sum()
    if cumulative_vol == 0:
        return round(close.iloc[-1], 2)
    return round(cumulative_pv / cumulative_vol, 2)


# ── NEW: ATR ─────────────────────────────────────────────────────
def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    """Average True Range — measures volatility, not direction."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return round(atr.iloc[-1], 2)


# ── NEW: ADX (+DI / -DI included, needed to give ADX a direction) ─
# def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> dict:
#     """
#     Average Directional Index — measures TREND STRENGTH (0-100), not direction.
#     +DI / -DI (directional indicators) are computed alongside it, since ADX
#     alone can't tell you bullish vs bearish — only "trending" vs "choppy".
#     """
#     up_move = high.diff()
#     down_move = -low.diff()

#     plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
#     minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

#     prev_close = close.shift(1)
#     tr = pd.concat([
#         high - low,
#         (high - prev_close).abs(),
#         (low - prev_close).abs()
#     ], axis=1).max(axis=1)

#     atr = tr.rolling(window=period).mean()
#     plus_di = 100 * (pd.Series(plus_dm, index=high.index).rolling(window=period).mean() / atr)
#     minus_di = 100 * (pd.Series(minus_dm, index=high.index).rolling(window=period).mean() / atr)

#     dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
#     adx = dx.rolling(window=period).mean()

#     return {
#         "adx": round(adx.iloc[-1], 2) if not pd.isna(adx.iloc[-1]) else 0.0,
#         "plus_di": round(plus_di.iloc[-1], 2) if not pd.isna(plus_di.iloc[-1]) else 0.0,
#         "minus_di": round(minus_di.iloc[-1], 2) if not pd.isna(minus_di.iloc[-1]) else 0.0,
#     }
def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> dict:
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    # Wilder smoothing throughout — ATR, +DM, -DM, and DX itself all use it
    # in the original formula. Plain rolling means here is what produced the
    # ~1.5-2x inflated ADX readings vs. Moneycontrol/TradingView.
    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * (
        pd.Series(plus_dm, index=high.index).ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr
    )
    minus_di = 100 * (
        pd.Series(minus_dm, index=high.index).ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr
    )

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    return {
        "adx": round(adx.iloc[-1], 2) if not pd.isna(adx.iloc[-1]) else 0.0,
        "plus_di": round(plus_di.iloc[-1], 2) if not pd.isna(plus_di.iloc[-1]) else 0.0,
        "minus_di": round(minus_di.iloc[-1], 2) if not pd.isna(minus_di.iloc[-1]) else 0.0,
    }