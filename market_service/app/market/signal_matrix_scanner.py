# app/market/signal_matrix_scanner.py
"""
Computes the signal matrix for an ENTIRE index universe (not top-N —
every symbol is kept, per the "show all, let user search/select" design).
"""

import concurrent.futures
import time
from market_service.app.market.upstox_client import UpstoxClient
from core_shared.watchlist_loader import WatchlistLoader
from market_service.app.market.signal_engine import compute_signal_matrix


class SignalMatrixScanner:
    def __init__(self, max_workers: int = 10):
        self.client = UpstoxClient()
        self.watchlist_loader = WatchlistLoader()
        self.max_workers = max_workers

    def _compute_one(self, symbol: str) -> dict | None:
        try:
            df = self.client.fetch_ohlc(symbol, days=60)
            return compute_signal_matrix(symbol, df)
        except Exception as e:
            print(f"[SignalMatrixScanner] Skipping {symbol}: {e}")
            return None

    def scan_index(self, index: str = "nifty50") -> list[dict]:
        symbols = self.watchlist_loader.load_symbols(index=index)
        print(f"[SignalMatrixScanner] Scanning {len(symbols)} symbols ({index})...")

        results = []
        start = time.time()

        # max_workers=10 stays safely under Upstox's 25 req/sec limit
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._compute_one, sym): sym for sym in symbols}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        elapsed = time.time() - start
        print(f"[SignalMatrixScanner] Computed {len(results)}/{len(symbols)} symbols in {elapsed:.1f}s")
        return results