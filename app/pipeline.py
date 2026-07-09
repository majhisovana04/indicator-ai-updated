
from app.embedding.embedder import Embedder
from app.vectorstore.vector_store import VectorStore
from app.routing.router import Router
from app.generation.response_executor import ResponseExecutor

from app.routing.intent_classifier import IntentClassifier, Intent
from app.market.background_refresher import live_summary_cache
import time

class AssistantPipeline:
    """
    Orchestrates the full flow: embed query -> search -> route -> execute.
    This class has no side effects on import — it only runs when explicitly used.
    """

    def __init__(self):
        self.embedder = Embedder()
        self.store = VectorStore()
        self.store.load()
        self.router = Router()
        self.executor = ResponseExecutor()


        self.intent_classifier = IntentClassifier(embedder=self.embedder)

    def ask(self, query: str, top_k: int = 3) -> dict:
        t0 = time.time()
        intent = self.intent_classifier.classify(query)
        t1 = time.time()
        print(f"Intent classification: {t1-t0:.2f}s")

        if intent == Intent.LIVE_SCREENING:
            cached = live_summary_cache.get()
            if cached:
                return {
                            "answer": cached["answer"],
                            "tier": "live_screening",
                            "distance": None
                        }
            return {
                        "answer": "Today's market analysis will be available after market close (3:30 PM IST). Please check back then.",
                        "tier": "live_screening_pending",
                        "distance": None
                    }

        query_vec = self.embedder.embed_query(query)
        results = self.store.search(query_vec, top_k=top_k)
        route = self.router.decide(results)
        return self.executor.execute(route, query, results)