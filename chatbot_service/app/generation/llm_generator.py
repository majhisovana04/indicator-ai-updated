# app/generation/llm_generator.py
from chatbot_service.app.models.chunk import Chunk
from chatbot_service.app.generation.llm_provider_manager import LLMProviderManager, ProviderExhausted


class LLMGenerator:
    """
    Generates answers using the LLM Provider Manager.
    Automatically falls back across Gemini -> Groq -> OpenRouter -> Cerebras.
    """

    def __init__(self):
        self.manager = LLMProviderManager()

    def build_prompt(self, query: str, chunks: list[Chunk]) -> str:
        context_text = "\n\n---\n\n".join(
            f"[Source: {c.source}]\n{c.content}" for c in chunks
        )
        return f"""You are an assistant that explains trading indicators to beginners.
CONTEXT (this is the only material you may draw from):
{context_text}

USER QUESTION:
{query}

HOW TO ANSWER:
1. The CONTEXT below includes document TITLES/HEADERS as well as body text.
   A title or header is part of the answerable content — if a document is
   titled "Moving Average Convergence Divergence (MACD)", and the question
   asks what MACD stands for, THE TITLE ITSELF IS THE ANSWER. State it
   directly and confidently. Do not treat titles as decoration to be ignored.
2. You may synthesize or connect ideas ACROSS multiple context sections if
   provided — that is still grounded, not invented.
3. Do NOT introduce facts, mechanisms, causes, or explanations for anything
   the context does not address AT ALL — no title, no header, no body text
   anywhere touches it. That silence is your signal to decline, nothing else.
4. If the context only partially covers the question, answer the part it
   covers, then clearly say which part it doesn't.
5. Only if NOTHING in the context — including titles — addresses the
   question's topic, respond with exactly:
   "I don't have that knowledge. I can explain RSI,
   MACD, SMA, and how traders typically use them."

STYLE:
- Beginner-friendly, concise — prefer short paragraphs or a short bulleted
  list over long dense prose.
- Never give financial advice, price predictions, or buy/sell recommendations,
  even if asked indirectly. Explain indicators and concepts only.
- Do not mention "the context," "the provided sources," or similar
  meta-commentary about your own retrieval process in the answer — just
  answer naturally, as an assistant who knows this material.

ANSWER:"""

    def generate_from_prompt(self, prompt: str) -> str:
        """
        General-purpose method: takes ANY prompt, returns LLM text response.
        Automatically tries all providers in order. Raises RuntimeError if all fail.
        """
        try:
            return self.manager.generate(prompt)
        except ProviderExhausted as e:
            raise RuntimeError(f"All LLM providers exhausted: {e}")

    def generate(self, query: str, chunks: list[Chunk]) -> str:
        prompt = self.build_prompt(query, chunks)
        return self.generate_from_prompt(prompt)