# app/routing/query_classifier.py
"""
Classifies into exactly one of SAFETY / LIVE_SCREENING / EDUCATION /
OFF_TOPIC by ARGMAX similarity across all four exemplar sets at once —
not independent thresholds. This is what fixes the instability where
tightening one threshold broke another query type.

OFF_TOPIC exists so that genuinely unrelated questions (weather, jokes,
general chit-chat) have a real competitor in the argmax, instead of
accidentally winning LIVE_SCREENING or SAFETY by default because
nothing better was in the running. This matters because the
LIVE_SCREENING branch in pipeline.py skips the FAISS/router distance
gate entirely — so if an off-topic question wins LIVE_SCREENING, it
gets live market data dumped on it with no safety net downstream.

No dependency on CompanyDetector or pipeline.py — fully testable alone.
"""

from enum import Enum
import numpy as np
from chatbot_service.app.embedding.embedder import Embedder


class QueryIntent(Enum):
    SAFETY = "safety"
    LIVE_SCREENING = "live_screening"
    EDUCATION = "education"
    OFF_TOPIC = "off_topic"


# Guarantee / certainty / "just pick one for me" language.
# Pulled directly from your policies/*.md examples + real failing queries.
SAFETY_EXAMPLES = [
    "are you 100% sure this signal is correct",
    "can you guarantee this stock will go up",
    "will this stock definitely go up",
    "will it definitely go up this week",
    "tell me which stock to buy for profit",
    "tell me one stock to buy for profit",
    "tell me one stock i can buy",
    "give me a guaranteed profitable strategy",
    "which stock will double next month",
    "should i buy bitcoin right now",
    "promise me this will make money",
    "is this a sure shot signal",
    "what stock should i buy",
    "just tell me what to buy",
    "give me a 100 percent winning strategy",
    "based on today's data should i buy this stock right now",
]

# Asking about current market conditions — general or company-specific.
SCREENING_EXAMPLES = [
    "which companies should i look at today",
    "what's the market sentiment today",
    "is the market bullish or bearish today",
    "top stocks to watch today",
    "what's the current signal for this stock",
    "what is the signal for a specific company",
    "which stocks have good technical signals today",
    "show me today's technical analysis",
    "what do the indicators say about this company",
    "how is this stock looking technically",
    "today's top companies to buy stocks",
    "what's the current signal for this company",   # was: "...for hdfc bank"
    "how is this stock looking today",               # was: "...bajaj finserv looking today"
    "how's this stock doing",
    "how is it doing today",
    "what's the signal for wipro",
    "tell me the signal for reliance",
    "what is the technical signal for this specific company",
    "give me the trading signal for a stock",

]

# Asking about indicator concepts, not live market state.
EDUCATION_EXAMPLES = [
    "what is rsi",
    "how does macd work",
    "explain moving averages",
    "what does overbought mean",
    "what's the difference between sma and ema",
    "how do i read a candlestick chart",
    "what is a confluence signal",
    "how is adx different from rsi",
    "why would a stock have high volume but small price move",
    "does a market gap affect technical signals",
    "how do sudden price drops break momentum indicators",
    "will high volatility ruin my rsi strategy",
]

# Genuinely unrelated to trading/markets at all. Extend this from real
# off-topic queries you see in logs over time.
OFF_TOPIC_EXAMPLES = [
    "what's the weather today",
    "what's the weather like",
    "tell me a joke",
    "how are you",
    "what's your name",
    "what time is it",
    "recommend a good restaurant",
    "help me write some code",
    "who won the cricket match",
    "what's the capital of France",
    "how do i cook pasta",
    "what movies are playing",
    "translate this sentence",
    "what's the news today",
]

# Below this similarity, none of the four classes fit confidently —
# default to EDUCATION, which still has to clear the FAISS distance
# gate in pipeline.py, so unrelated questions that ALSO score low on
# OFF_TOPIC's own exemplars still correctly land in fallback.
CONFIDENCE_FLOOR = 0.55


class QueryClassifier:
    def __init__(self, embedder=None):
        self.embedder = embedder or Embedder()
        self._class_vectors = {
            QueryIntent.SAFETY: self._embed_all(SAFETY_EXAMPLES),
            QueryIntent.LIVE_SCREENING: self._embed_all(SCREENING_EXAMPLES),
            QueryIntent.EDUCATION: self._embed_all(EDUCATION_EXAMPLES),
            QueryIntent.OFF_TOPIC: self._embed_all(OFF_TOPIC_EXAMPLES),
        }

    def _embed_all(self, examples: list[str]) -> np.ndarray:
        return np.array([self.embedder.embed_query(e)[0] for e in examples])

    def _best_sim(self, query_vec, class_vectors: np.ndarray) -> float:
        sims = np.dot(class_vectors, query_vec) / (
            np.linalg.norm(class_vectors, axis=1) * np.linalg.norm(query_vec)
        )
        return float(np.max(sims))

    def classify_with_vec(self, query_vec) -> tuple[QueryIntent, dict]:
        """
        Returns (chosen_intent, all_scores) — scores included so tests
        and debugging can see WHY a classification happened, not just
        the final answer.
        """
        scores = {
            intent: self._best_sim(query_vec, vecs)
            for intent, vecs in self._class_vectors.items()
        }
        best_intent = max(scores, key=scores.get)
        if scores[best_intent] < CONFIDENCE_FLOOR:
            return QueryIntent.EDUCATION, scores
        return best_intent, scores

    def classify(self, query: str) -> tuple[QueryIntent, dict]:
        """Convenience wrapper when you don't already have the embedding."""
        query_vec = self.embedder.embed_query(query)[0]
        return self.classify_with_vec(query_vec)