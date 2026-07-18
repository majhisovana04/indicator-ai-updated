# app/generation/llm_generator.py
from app.models.chunk import Chunk
from app.generation.llm_provider_manager import LLMProviderManager, ProviderExhausted


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
1. Base your answer entirely on the CONTEXT above. This includes reading
   definitions, titles, and headers directly (e.g. if a document is titled
   "Moving Average Convergence Divergence (MACD)", stating that MACD stands
   for that phrase is using the context, not outside knowledge).
2. You may synthesize or connect ideas ACROSS multiple context sections if
   they're both provided — that is still grounded, not invented.
3. Do NOT introduce facts, mechanisms, causes, or explanations for anything
   the context does not address, even if you're confident it's true from
   general knowledge. If the context is silent on the actual question being
   asked, that silence is your answer — don't fill it in.
4. If the context only partially covers the question, answer the part it
   covers, then clearly say which part it doesn't — do not guess at the rest.
5. If the context does not address the question's topic at all, respond
   with exactly this, and nothing else:
   "I don't have knowledge on that yet. I can explain RSI,
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