# app/generation/response_executor.py
from chatbot_service.app.routing.router import Route
from chatbot_service.app.generation.answer_extractor import AnswerExtractor
from chatbot_service.app.generation.llm_generator import LLMGenerator

from chatbot_service.app.generation.redis_semantic_cache import RedisSemanticCache
from chatbot_service.app.embedding.embedder import Embedder

from chatbot_service.app.generation.llm_provider_manager import ProviderExhausted

class ResponseExecutor:
    """
    Takes a Route decision + retrieval results and produces
    the final answer. Does NOT decide the route — only executes it.
    """

    def __init__(self, embedder):
        self.extractor = AnswerExtractor()
        self.llm = LLMGenerator()
        
        self.semantic_cache = RedisSemanticCache(embedder=embedder, similarity_threshold=0.84)
        

    def execute(self, route: Route, query: str, results: list, query_vector: list = None) -> dict:
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

        if route == Route.LLM:
            chunks = [r["chunk"] for r in results]
            try:
                answer_text = self.llm.generate(query, chunks)
                self.semantic_cache.set(
                    query, answer_text, cache_type=RedisSemanticCache.EDUCATION, query_vector=query_vector
                )
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

        return {
            "answer": (
                "I'm not able to help with that specific question, but I'm here for anything "
                "related to trading indicators — like RSI, MACD, moving averages, or how to "
                "read technical signals. Feel free to ask me about those, or about a specific "
                "stock's current technical picture."
            ),
            "tier": "fallback",
            "source": None,
            "distance": top_distance
        }