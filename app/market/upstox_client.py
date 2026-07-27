# app/market/upstox_client.py
import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from app.market.instrument_mapper import InstrumentMapper
from dotenv import load_dotenv
load_dotenv()


class UpstoxClient:
    """
    Fetches REAL historical OHLC data from Upstox's V3 Historical Candle API.
    Returns a DataFrame with 'high', 'low', 'close', 'volume' columns —
    extended from close/volume-only to support ADX/ATR/VWAP.
    """

    BASE_URL = "https://api.upstox.com/v3/historical-candle"

    def __init__(self):
        self.access_token = os.getenv("UPSTOX_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError("UPSTOX_ACCESS_TOKEN not found in environment")
        self.mapper = InstrumentMapper()

    def fetch_ohlc(self, symbol: str, days: int = 60) -> pd.DataFrame:
        instrument_key = self.mapper.get_instrument_key(symbol)

        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

        url = f"{self.BASE_URL}/{instrument_key}/days/1/{to_date}/{from_date}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        candles = data["data"]["candles"]
        if not candles:
            raise ValueError(f"No candle data returned for {symbol}")

        # Each candle: [timestamp, open, high, low, close, volume, oi]
        # Upstox returns newest-first — reverse to chronological order
        candles = list(reversed(candles))

        return pd.DataFrame({
            "date":   [c[0] for c in candles],   # ISO timestamp — kept for auditability
            "high":   [c[2] for c in candles],
            "low":    [c[3] for c in candles],
            "close":  [c[4] for c in candles],
            "volume": [c[5] for c in candles],
        })