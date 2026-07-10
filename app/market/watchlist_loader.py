# app/market/watchlist_loader.py
import requests
import pandas as pd
from io import StringIO


class WatchlistLoader:
    NIFTY500_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"

    def load_symbols(self) -> list[str]:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(self.NIFTY500_URL, headers=headers, timeout=10)
        response.raise_for_status()

        df = pd.read_csv(StringIO(response.text))
        plain_symbols = df["Symbol"].tolist()

        # Nifty 500 is NSE-listed — match the composite format InstrumentMapper expects
        return [f"NSE:{symbol}" for symbol in plain_symbols]