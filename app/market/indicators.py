import pandas as pd


def calculate_rsi(close_prices: pd.Series, period: int = 14) -> float:
    delta = close_prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

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