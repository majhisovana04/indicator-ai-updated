import os
from dotenv import load_dotenv
from google import genai
from app.models.chunk import Chunk

load_dotenv()


class LLMGenerator:
    """
    Generates answers using Gemini, grounded in retrieved chunks.
    """

    def __init__(self, model: str = "gemini-flash-latest"):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = model

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

    def generate(self, query: str, chunks: list[Chunk]) -> str:
        prompt = self.build_prompt(query, chunks)
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )
        return response.text.strip()