from app.routing.router import Route
from app.generation.answer_extractor import AnswerExtractor
from app.generation.llm_generator import LLMGenerator
from app.generation.gemini_budget import GeminiDailyBudget

class ResponseExecutor:
    """
    Takes a Route decision + retrieval results and produces
    the final answer. Does NOT decide the route — only executes it.
    """

    def __init__(self):
        self.extractor = AnswerExtractor()
        self.llm = LLMGenerator()
        self.gemini_budget = GeminiDailyBudget(daily_limit=18)  # small buffer below the real 20

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
            if not self.gemini_budget.can_call():
                return {
                    "answer": "I'm currently experiencing high demand and can't generate a detailed answer right now. Here's what I know: " + top_chunk.content[:200],
                    "tier": "budget_exceeded",
                
                }
            self.gemini_budget.record_call()
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