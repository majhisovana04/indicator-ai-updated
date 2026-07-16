# app/embedding/embedder.py (FastEmbed version)
import numpy as np
from fastembed import TextEmbedding
from app.models.chunk import Chunk


class Embedder:
    """
    Local embeddings via FastEmbed (ONNX-based, no API key needed).
    Drop-in replacement — same embed_chunks() / embed_query() interface.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self.model = TextEmbedding(model_name=model_name)

    def _embed_texts(self, texts: list[str]) -> np.ndarray:
        embeddings = list(self.model.embed(texts))  # generator → list
        return np.array(embeddings, dtype="float32")

    def embed_chunks(self, chunks: list[Chunk]) -> np.ndarray:
        texts = [chunk.content for chunk in chunks]
        return self._embed_texts(texts)

    def embed_query(self, query: str) -> np.ndarray:
        """Returns shape (1, 384) — same as before."""
        return self._embed_texts([query])
