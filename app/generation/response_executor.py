from app.routing.router import Route
from app.generation.answer_extractor import AnswerExtractor
from app.generation.llm_generator import LLMGenerator


class ResponseExecutor:
    """
    Takes a Route decision + retrieval results and produces
    the final answer. Does NOT decide the route — only executes it.
    """

    def __init__(self):
        self.extractor = AnswerExtractor()
        self.llm = LLMGenerator()

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

        if route == Route.LLM:
            chunks = [r["chunk"] for r in results]
            answer_text = self.llm.generate(query, chunks)
            return {
                "answer": answer_text,
                "tier": "llm_generated",
                "sources": [c.source for c in chunks],
                "distance": top_distance
            }

        # Route.FALLBACK
        return {
            "answer": "I don't have information on that topic yet. I can help explain the trading indicators available on this platform.",
            "tier": "fallback",
            "source": None,
            "distance": top_distance
        }