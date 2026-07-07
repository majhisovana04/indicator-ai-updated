from sentence_transformers import SentenceTransformer
from app.models.chunk import Chunk


class Embedder:
    """
    Converts Chunk objects into vector embeddings using a
    local sentence-transformers model (free, runs on CPU).
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def embed_chunks(self, chunks: list[Chunk]):
        """
        Returns embeddings in the SAME order as the input chunks.
        This order must be preserved — it's how we map
        FAISS search results back to the correct Chunk later.
        """
        texts = [chunk.content for chunk in chunks]
        embeddings = self.model.encode(texts, show_progress_bar=True)
        return embeddings

    def embed_query(self, query: str):
        """Embeds a single user query string for search."""
        return self.model.encode([query])