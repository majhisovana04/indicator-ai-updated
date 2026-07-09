from app.market.upstox_client import UpstoxClient
from app.market.indicators import calculate_rsi, calculate_macd, calculate_sma

WATCHLIST = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "WIPRO"]


class Screener:
    def __init__(self):
        self.client = UpstoxClient()

    def analyze_company(self, symbol: str) -> dict:
        data = self.client.fetch_ohlc(symbol, days=60)
        close = data["close"]

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

    def get_top_candidates(self, top_n: int = 5) -> list[dict]:
        results = [self.analyze_company(sym) for sym in WATCHLIST]
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