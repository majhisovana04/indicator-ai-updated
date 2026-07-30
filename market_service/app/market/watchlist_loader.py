# app/market/watchlist_loader.py
import requests
import pandas as pd
from io import StringIO


class WatchlistLoader:
    """
    Loads index constituent lists from NSE Indices.
    Supports any index they publish a CSV for — just add the URL below.
    """

    INDEX_URLS = {
        "nifty50":  "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv",
        "nifty500": "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
    }

    def load_symbols(self, index: str = "nifty50") -> list[str]:
        url = self.INDEX_URLS.get(index)
        if not url:
            raise ValueError(f"Unknown index '{index}'. Available: {list(self.INDEX_URLS)}")

        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        df = pd.read_csv(StringIO(response.text))
        plain_symbols = df["Symbol"].tolist()

        return [f"NSE:{symbol}" for symbol in plain_symbols]