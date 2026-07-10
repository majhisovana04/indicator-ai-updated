
# from app.embedding.embedder import Embedder
# from app.vectorstore.vector_store import VectorStore
# from app.routing.router import Router
# from app.generation.response_executor import ResponseExecutor

# from app.routing.intent_classifier import IntentClassifier, Intent
# from app.market.background_refresher import live_summary_cache
# import time

# class AssistantPipeline:
#     """
#     Orchestrates the full flow: embed query -> search -> route -> execute.
#     This class has no side effects on import — it only runs when explicitly used.
#     """

#     def __init__(self):
#         self.embedder = Embedder()
#         self.store = VectorStore()
#         self.store.load()
#         self.router = Router()
#         self.executor = ResponseExecutor(embedder=self.embedder)


#         self.intent_classifier = IntentClassifier(embedder=self.embedder)

#     def ask(self, query: str, top_k: int = 3) -> dict:
#         t0 = time.time()
#         intent = self.intent_classifier.classify(query)
#         t1 = time.time()
#         print(f"Intent classification: {t1-t0:.2f}s")

#         # if intent == Intent.LIVE_SCREENING:
#         #     cached = live_summary_cache.get()
#         #     if cached:
#         #         return {
#         #                     "answer": cached["answer"],
#         #                     "tier": "live_screening",
#         #                     "distance": None
#         #                 }
#         #     return {
#         #                 "answer": "Today's market analysis will be available after market close (3:30 PM IST). Please check back then.",
#         #                 "tier": "live_screening_pending",
#         #                 "distance": None
#         #             }
#         if intent == Intent.LIVE_SCREENING:
#             cached = live_summary_cache.get()
#             if cached:
#                 age_hours = live_summary_cache.get_age_seconds() / 3600
#                 freshness_note = ""
#                 if age_hours > 20:  # roughly "this is from a previous trading day"
#                     freshness_note = " (Note: this reflects the most recent available trading day's data.)"
#                 return {
#                     "answer": cached["answer"] + freshness_note,
#                     "tier": "live_screening",
#                     "distance": None
#                 }
#             # Only reached if the server has NEVER successfully run a refresh yet
#             return {
#                 "answer": "Market analysis is being prepared for the first time. Please check back in a few minutes.",
#                 "tier": "live_screening_pending",
#                 "distance": None
#             }

#         query_vec = self.embedder.embed_query(query)
#         results = self.store.search(query_vec, top_k=top_k)
#         route = self.router.decide(results)
#         return self.executor.execute(route, query, results)

# app/pipeline.py — full replacement
'''
from app.embedding.embedder import Embedder
from app.vectorstore.vector_store import VectorStore
from app.routing.router import Router
from app.generation.response_executor import ResponseExecutor
from app.generation.redis_semantic_cache import RedisSemanticCache
from app.routing.intent_classifier import IntentClassifier, Intent
from app.market.background_refresher import live_summary_cache
import time


class AssistantPipeline:
    """
    Orchestrates the full flow: embed → cache check → intent → route → execute.
    """

    def __init__(self):
        self.embedder = Embedder()
        self.store = VectorStore()
        self.store.load()
        self.router = Router()
        self.executor = ResponseExecutor(embedder=self.embedder)
        self.intent_classifier = IntentClassifier(embedder=self.embedder)

    def ask(self, query: str, top_k: int = 3) -> dict:
        t0 = time.time()

        # ── Step 0: Embed ONCE ──────────────────────────────────────
        # embed_query returns shape (1, 384) — we keep both:
        #   query_embedding : (1, 384)  → for vector search (store.search)
        #   query_vec_1d    : (384,)    → for cosine similarity (cache + classifier)
        query_embedding = self.embedder.embed_query(query)   # (1, 384)
        query_vec_1d    = query_embedding[0]                 # (384,)

        # ── Step 1: Check Redis cache BEFORE classification ─────────
        # Check education cache first (most common query type)
        cached = self.executor.semantic_cache.get(query, cache_type=RedisSemanticCache.EDUCATION)
        if cached:
            print(f"[Pipeline] Redis HIT (education) — skipping classification + LLM")
            return {
                "answer": cached,
                "tier": "llm_cached",
                "distance": None
            }

        # Check market cache
        cached = self.executor.semantic_cache.get(query, cache_type=RedisSemanticCache.MARKET)
        if cached:
            print(f"[Pipeline] Redis HIT (market) — skipping classification + market fetch")
            return {
                "answer": cached,
                "tier": "market_cached",
                "distance": None
            }

        # ── Step 2: Intent classification (reuse pre-computed vec) ──
        t1 = time.time()
        intent = self.intent_classifier.classify_with_vec(query_vec_1d)
        t2 = time.time()
        print(f"Intent classification: {t2-t1:.2f}s (embedding reused, not re-computed)")

        # ── Step 3a: Market / Live Screening path ───────────────────
        if intent == Intent.LIVE_SCREENING:
            cached_market = live_summary_cache.get()
            if cached_market:
                age_hours = live_summary_cache.get_age_seconds() / 3600
                freshness_note = ""
                if age_hours > 20:
                    freshness_note = " (Note: this reflects the most recent available trading day's data.)"
                answer = cached_market["answer"] + freshness_note

                # Store in Redis market cache (6h TTL) so next similar question is a cache hit
                self.executor.semantic_cache.set(
                    query, answer, cache_type=RedisSemanticCache.MARKET
                )
                return {
                    "answer": answer,
                    "tier": "live_screening",
                    "distance": None
                }
            return {
                "answer": "Market analysis is being prepared for the first time. Please check back in a few minutes.",
                "tier": "live_screening_pending",
                "distance": None
            }

        # ── Step 3b: Education path — vector search + route + execute ─
        results = self.store.search(query_embedding, top_k=top_k)
        route = self.router.decide(results)
        return self.executor.execute(route, query, results)'''

# app/pipeline.py

from app.embedding.embedder import Embedder
from app.vectorstore.vector_store import VectorStore
from app.routing.router import Router
from app.generation.response_executor import ResponseExecutor
from app.generation.redis_semantic_cache import RedisSemanticCache
from app.routing.intent_classifier import IntentClassifier, Intent
from app.redis_client import get_redis
import json
import time


class AssistantPipeline:
    """
    Orchestrates the full flow: embed → cache check → intent → route → execute.
    """

    def __init__(self):
        self.embedder = Embedder()
        self.store = VectorStore()
        self.store.load()
        self.router = Router()
        self.executor = ResponseExecutor(embedder=self.embedder)
        self.intent_classifier = IntentClassifier(embedder=self.embedder)

    def ask(self, query: str, top_k: int = 3) -> dict:
        t0 = time.time()

        # ── Step 0: Embed ONCE ──────────────────────────────────────
        # embed_query returns shape (1, 384) — we keep both:
        #   query_embedding : (1, 384)  → for vector search (store.search)
        #   query_vec_1d    : (384,)    → for cosine similarity (cache + classifier)
        query_embedding = self.embedder.embed_query(query)   # (1, 384)
        query_vec_1d    = query_embedding[0]                 # (384,)

        # ── Step 1: Check Redis cache BEFORE classification ─────────
        # Check education cache first (most common query type)
        cached = self.executor.semantic_cache.get(query, cache_type=RedisSemanticCache.EDUCATION)
        if cached:
            print(f"[Pipeline] Redis HIT (education) — skipping classification + LLM")
            return {
                "answer": cached,
                "tier": "llm_cached",
                "distance": None
            }

        # Check market cache
        cached = self.executor.semantic_cache.get(query, cache_type=RedisSemanticCache.MARKET)
        if cached:
            print(f"[Pipeline] Redis HIT (market) — skipping classification + market fetch")
            return {
                "answer": cached,
                "tier": "market_cached",
                "distance": None
            }

        # ── Step 2: Intent classification (reuse pre-computed vec) ──
        t1 = time.time()
        intent = self.intent_classifier.classify_with_vec(query_vec_1d)
        t2 = time.time()
        print(f"Intent classification: {t2-t1:.2f}s (embedding reused, not re-computed)")

        # ── Step 3a: Market / Live Screening path ───────────────────
        if intent == Intent.LIVE_SCREENING:
            r = get_redis()
            cached_market_json = r.get("market:daily_summary") if r else None
            
            if cached_market_json:
                cached_market = json.loads(cached_market_json)
                # Redis doesn't give us easily parsed age without another command, 
                # but we know it expires in 20 hours. For now, just serve it directly.
                answer = cached_market["answer"]
                
                # Store in Redis semantic market cache (6h TTL) so next similar question is a cache hit
                self.executor.semantic_cache.set(
                    query, answer, cache_type=RedisSemanticCache.MARKET
                )
                return {
                    "answer": answer,
                    "tier": "live_screening",
                    "distance": None
                }
            return {
                "answer": "Market analysis is being prepared for the first time. Please check back in a few minutes.",
                "tier": "live_screening_pending",
                "distance": None
            }

        # ── Step 3b: Education path — vector search + route + execute ─
        results = self.store.search(query_embedding, top_k=top_k)
        route = self.router.decide(results)
        return self.executor.execute(route, query, results)

