# app/generation/response_executor.py
from app.routing.router import Route
from app.generation.answer_extractor import AnswerExtractor
from app.generation.llm_generator import LLMGenerator

from app.generation.redis_semantic_cache import RedisSemanticCache
from app.embedding.embedder import Embedder

from app.generation.llm_provider_manager import ProviderExhausted

class ResponseExecutor:
    """
    Takes a Route decision + retrieval results and produces
    the final answer. Does NOT decide the route — only executes it.
    """

    def __init__(self, embedder):
        self.extractor = AnswerExtractor()
        self.llm = LLMGenerator()
        
        self.semantic_cache = RedisSemanticCache(embedder=embedder, similarity_threshold=0.82)
        

    def execute(self, route: Route, query: str, results: list) -> dict:
        top_chunk = results[0]["chunk"] if results else None
        top_distance = results[0]["distance"] if results else None

        if route == Route.FAQ:
            return {
                "answer": self.extractor.extract_answer(top_chunk),
                "tier": "faq_direct",
                "source": top_chunk.source,
                "distance": top_distance
            }

        if route == Route.POLICY:
            return {
                "answer": self.extractor.extract_answer(top_chunk),
                "tier": "policy_direct",
                "source": top_chunk.source,
                "distance": top_distance
            }
        # changes
        if route == Route.LLM:
            chunks = [r["chunk"] for r in results]
            try:
                answer_text = self.llm.generate(query, chunks)
                self.semantic_cache.set(query, answer_text, cache_type=RedisSemanticCache.EDUCATION)
                return {
                    "answer": answer_text,
                    "tier": "llm_generated",
                    "sources": [c.source for c in chunks],
                    "distance": top_distance
                }
            except RuntimeError as e:
                return {
                    "answer": str(e).replace("All LLM providers exhausted: ", ""),
                    "tier": "llm_failed",
                    "source": top_chunk.source if top_chunk else None,
                    "distance": top_distance
                }
        # Route.FALLBACK
        return {
            "answer": "I don't have information on that topic yet. I can help explain the trading indicators available on this platform.",
            "tier": "fallback",
            "source": None,
            "distance": top_distance
        }