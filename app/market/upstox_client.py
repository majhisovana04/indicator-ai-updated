import pandas as pd
import random


class UpstoxClient:
    """
    Fetches OHLC price data for a company.
    Currently returns DUMMY data for development.
    Swap fetch_ohlc() internals with real Upstox API calls later —
    the return shape (a DataFrame with a 'close' column) stays the same.
    """

    def fetch_ohlc(self, symbol: str, days: int = 60) -> pd.DataFrame:
        # DUMMY: random walk price data, just for testing the pipeline
        base_price = random.uniform(100, 2000)
        prices = [base_price]
        for _ in range(days - 1):
            change = random.uniform(-0.03, 0.03)
            prices.append(prices[-1] * (1 + change))

        return pd.DataFrame({"close": prices})