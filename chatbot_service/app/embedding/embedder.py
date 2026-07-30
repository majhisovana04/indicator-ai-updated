# app/embedding/embedder.py (FastEmbed version)
import os
os.environ["ORT_DISABLE_ALL_MEMORY_ARENA_SHRINKAGE"] = "0"

import numpy as np
from fastembed import TextEmbedding
from chatbot_service.app.models.chunk import Chunk


class Embedder:
    """
    Local embeddings via FastEmbed (ONNX-based, no API key needed).
    Drop-in replacement — same embed_chunks() / embed_query() interface.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        #self.model = TextEmbedding(model_name=model_name, threads=1, cache_dir="./model_cache")
        try:
            self.model = TextEmbedding(
                model_name=model_name, 
                threads=1, 
                cache_dir="./model_cache",
                providers=[
                    ("CPUExecutionProvider", {
                        "arena_extend_strategy": "kSameAsRequested",
                        "enable_cpu_mem_arena": "0",
                    })
                ]
            )
        except TypeError as e:
            print(f"[Embedder] providers argument not supported by installed fastembed version: {e}")
            print("[Embedder] Falling back to default initialization")
            self.model = TextEmbedding(model_name=model_name, threads=1, cache_dir="./model_cache")

    def _embed_texts(self, texts: list[str]) -> np.ndarray:
        embeddings = list(self.model.embed(texts))  # generator → list
        return np.array(embeddings, dtype="float32")

    def embed_chunks(self, chunks: list[Chunk]) -> np.ndarray:
        texts = [chunk.content for chunk in chunks]
        return self._embed_texts(texts)

    def embed_query(self, query: str) -> np.ndarray:
        """Returns shape (1, 384) — same as before."""
        return self._embed_texts([query])
