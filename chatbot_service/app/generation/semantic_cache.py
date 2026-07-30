import time
import numpy as np
from chatbot_service.app.embedding.embedder import Embedder


class SemanticCache:
    """
    Remembers previously LLM-generated answers. If a new question is
    semantically close enough to one already answered recently,
    returns the saved answer instead of calling the LLM again.
    """

    def __init__(self, embedder, similarity_threshold: float = 0.90, ttl_seconds: int = 3600):
        self.embedder = embedder  # REUSE the shared embedder, don't create a new one
        self.similarity_threshold = similarity_threshold
        self.ttl_seconds = ttl_seconds
        self.entries = []  # list of {"question", "answer", "vector", "timestamp"}

    def _cosine_sim(self, a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    def get(self, query: str):
        self._evict_expired()
        query_vec = self.embedder.embed_query(query)[0]

        best_match = None
        best_sim = 0
        for entry in self.entries:
            sim = self._cosine_sim(query_vec, entry["vector"])
            if sim > best_sim:
                best_sim = sim
                best_match = entry

        if best_match and best_sim >= self.similarity_threshold:
            return best_match["answer"]
        return None

    def set(self, query: str, answer: str):
        query_vec = self.embedder.embed_query(query)[0]
        self.entries.append({
            "question": query,
            "answer": answer,
            "vector": query_vec,
            "timestamp": time.time()
        })

    def _evict_expired(self):
        now = time.time()
        self.entries = [e for e in self.entries if now - e["timestamp"] < self.ttl_seconds]