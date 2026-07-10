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

Rules:
- Only use the CONTEXT below to answer. Do not use outside knowledge.
- Do not give financial advice or predict prices.
- If the context doesn't fully answer the question, say what you know and note the limitation.
- Keep answers concise and beginner-friendly.

CONTEXT:
{context_text}

USER QUESTION:
{query}

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