# app/embedding/embedder.py
import os
import numpy as np
from huggingface_hub import InferenceClient
from app.models.chunk import Chunk
from dotenv import load_dotenv
load_dotenv()


class Embedder:
    """
    Converts text into vector embeddings using Hugging Face's
    Inference Providers (current, supported API) — no local model
    loaded into RAM. Same public interface as the local version:
    embed_chunks(), embed_query() — return shapes unchanged, so
    FAISS/cosine similarity code elsewhere needs NO changes.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        hf_token = os.getenv("HF_TOKEN")
        if not hf_token:
            raise ValueError("HF_TOKEN not found in environment — required for Hugging Face Inference")

        self.client = InferenceClient(provider="hf-inference", api_key=hf_token)

    def _embed_texts(self, texts: list[str]) -> np.ndarray:
        """
        Embeds a list of texts, one call per text (feature_extraction
        doesn't batch multiple inputs in one call the way local
        sentence-transformers did) — results are stacked in order.
        """
        vectors = [
            self.client.feature_extraction(text, model=self.model_name)
            for text in texts
        ]
        return np.array(vectors, dtype="float32")

    def embed_chunks(self, chunks: list[Chunk]):
        """
        Returns embeddings in the SAME order as the input chunks.
        This order must be preserved — it's how we map
        FAISS search results back to the correct Chunk later.
        """
        texts = [chunk.content for chunk in chunks]
        return self._embed_texts(texts)

    def embed_query(self, query: str):
        """Embeds a single user query string for search. Returns shape (1, 384)."""
        return self._embed_texts([query])