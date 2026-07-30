# app/routing/company_detector.py
import re
from market_service.app.market.watchlist_loader import WatchlistLoader

# Only needed for names where the real ticker abbreviates differently
# than how people actually type the company name. This list stays SMALL
# (exceptions only) — WatchlistLoader remains the single source of truth
# for which companies exist; this just patches known phrasing gaps.
ALIAS_OVERRIDES = {
    "BAJAJFINSERV": "BAJAJFINSV",
    "LARSENTOUBRO": "LT",
    "LARSENANDTOUBRO": "LT",
    "L&T": "LT",
    "MAHINDRAANDMAHINDRA": "M&M",
    "HINDUSTANUNILEVER": "HINDUNILVR",
    "STATEBANK": "SBIN",
    "STATEBANKOFINDIA": "SBIN",
    "SBI": "SBIN",
    "INFOSYS": "INFY",
    "HDFC": "HDFCBANK",   
}


def _normalize(text: str) -> str:
    """Uppercase, strip everything except letters/digits — so
    'HDFC Bank', 'hdfc-bank', 'HDFC  Bank' all normalize identically."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


class CompanyDetector:
    def __init__(self, index: str = "nifty500"):
        loader = WatchlistLoader()
        symbols = loader.load_symbols(index=index)
        raw_tickers = {s.replace("NSE:", "").upper() for s in symbols}

        # lookup: normalized_name -> real_ticker
        self._lookup = {_normalize(t): t for t in raw_tickers}
        for alias_normalized, ticker in ALIAS_OVERRIDES.items():
            if ticker in raw_tickers:  # only add aliases for tickers actually in this universe
                self._lookup[alias_normalized] = ticker

        self.company_symbols = raw_tickers

    def find_company(self, query: str) -> str | None:
        """
        Tokenizes the query and checks 3-word, then 2-word, then 1-word
        windows (normalized) against known tickers/aliases — longest
        match first, so 'HDFC Bank' matches as a unit before 'HDFC' alone
        could accidentally match something shorter.
        """
        words = re.findall(r"[A-Za-z0-9&]+", query)
        n = len(words)

        for window in (3, 2, 1):
            for i in range(n - window + 1):
                candidate = _normalize("".join(words[i:i + window]))
                if candidate in self._lookup:
                    return self._lookup[candidate]
        return None

    def mentions_company(self, query: str) -> bool:
        return self.find_company(query) is not None