# app/routing/intent_classifier.py
from enum import Enum
import numpy as np
from app.embedding.embedder import Embedder



class Intent(Enum):
    EDUCATION = "education"
    LIVE_SCREENING = "live_screening"


SCREENING_EXAMPLES = [
    "which companies should I look at today",
    "suggest some good stocks right now",
    "what's the market sentiment today",
    "is the market bullish or bearish today",
    "give me some stock picks",
    "what are today's top picks",  
    "which stocks are bullish today",
    "what should I invest in today",
    "top stocks to watch today",
    "which stocks look strong right now",
    "how will the market be today",
    "what indicators show good signals right now",  
    "which stocks have good technical signals today",
]



class IntentClassifier:
    def __init__(self, embedder=None,  threshold: float = 0.75):
        self.embedder = embedder or Embedder() 
        self.threshold = threshold
        self.example_vectors = self.embedder.model.encode(SCREENING_EXAMPLES)

    def classify(self, query: str) -> Intent:
        query_vec = self.embedder.embed_query(query)[0]

        # cosine similarity against each example
        sims = np.dot(self.example_vectors, query_vec) / (
            np.linalg.norm(self.example_vectors, axis=1) * np.linalg.norm(query_vec)
        )
        best_sim = np.max(sims)

        if best_sim >= self.threshold:
            return Intent.LIVE_SCREENING
        return Intent.EDUCATION

    def classify_with_vec(self, query_vec) -> Intent:
        """
        Same logic as classify() but accepts a pre-computed embedding vector.
        Use this when the query has already been embedded upstream
        to avoid embedding twice.
        """
        sims = np.dot(self.example_vectors, query_vec) / (
            np.linalg.norm(self.example_vectors, axis=1) * np.linalg.norm(query_vec)
        )
        best_sim = np.max(sims)
        if best_sim >= self.threshold:
            return Intent.LIVE_SCREENING
        return Intent.EDUCATION
