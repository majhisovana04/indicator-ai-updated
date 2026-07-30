# app/market/screener.py
import concurrent.futures
import time
from market_service.app.market.upstox_client import UpstoxClient
from market_service.app.market.indicators import calculate_rsi, calculate_macd, calculate_sma, check_liquidity
from core_shared.watchlist_loader import WatchlistLoader


class Screener:
    def __init__(self, max_workers: int = 10):
        self.client = UpstoxClient()
        self.watchlist_loader = WatchlistLoader()
        self.max_workers = max_workers

    def analyze_company(self, symbol: str) -> dict | None:
        try:
            data = self.client.fetch_ohlc(symbol, days=60)
            close = data["close"]
            volume = data["volume"]

            liquidity = check_liquidity(volume)
            if not liquidity["is_liquid"]:
                return None

            rsi = calculate_rsi(close)
            macd = calculate_macd(close)
            sma50 = calculate_sma(close, period=50)
            current_price = close.iloc[-1]

            signals = []
            if 30 <= rsi <= 45:
                signals.append("RSI recovering from oversold zone")
            if macd["bullish_crossover"]:
                signals.append("MACD bullish crossover")
            if current_price > sma50:
                signals.append("Price trading above 50-day average")

            return {
                "symbol": symbol,
                "rsi": rsi,
                "macd_bullish": macd["bullish_crossover"],
                "signals": signals,
                "confluence_score": len(signals)
            }
        except Exception as e:
            print(f"Skipping {symbol}: {e}")
            return None

    def get_top_candidates(self, top_n: int = 5) -> list[dict]:
        symbols = self.watchlist_loader.load_symbols()
        print(f"Screening {len(symbols)} companies (Nifty 500)...")

        results = []
        start = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.analyze_company, sym): sym for sym in symbols}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        print(f"Screened {len(results)}/{len(symbols)} companies in {time.time()-start:.1f}s")

        confluent = [r for r in results if r["confluence_score"] >= 2]
        confluent.sort(key=lambda r: r["confluence_score"], reverse=True)
        return confluent[:top_n]

    def get_market_sentiment(self, results: list[dict]) -> str:
        if not results:
            return "unclear"
        bullish_count = sum(1 for r in results if r["macd_bullish"])
        ratio = bullish_count / len(results)
        if ratio > 0.6:
            return "bullish"
        elif ratio < 0.4:
            return "bearish"
        return "neutral"

    def analyze_specific_company(self, symbol: str) -> dict:
        """
        Full analysis for a user-named company — unlike get_top_candidates(),
        this NEVER silently drops the company. If liquidity is too low for
        reliable signals, it says so honestly instead of hiding the result.
        """
        data = self.client.fetch_ohlc(symbol, days=60)
        close = data["close"]
        volume = data["volume"]

        liquidity = check_liquidity(volume)

        if not liquidity["is_liquid"]:
            return {
                "symbol": symbol,
                "available": False,
                "reason": liquidity["reason"]
            }

        rsi = calculate_rsi(close)
        macd = calculate_macd(close)
        sma50 = calculate_sma(close, period=50)
        current_price = close.iloc[-1]

        signals = []
        if 30 <= rsi <= 45:
            signals.append("RSI recovering from oversold zone")
        if macd["bullish_crossover"]:
            signals.append("MACD bullish crossover")
        if current_price > sma50:
            signals.append("Price trading above 50-day average")

        return {
            "symbol": symbol,
            "available": True,
            "rsi": rsi,
            "macd_bullish": macd["bullish_crossover"],
            "signals": signals if signals else ["No strong technical signals detected at this time"]
        }