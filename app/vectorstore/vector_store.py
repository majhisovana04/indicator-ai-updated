import faiss
import pickle
from pathlib import Path
from app.models.chunk import Chunk


class VectorStore:
    """
    Wraps a FAISS index plus the Chunk metadata needed to map
    search results back to their original content.
    """

    def __init__(self, index_path: str = "vector_store.index",
                 metadata_path: str = "chunk_metadata.pkl"):
        self.index_path = Path(index_path)
        self.metadata_path = Path(metadata_path)
        self.index = None
        self.chunks: list[Chunk] = []

    def build(self, chunks: list[Chunk], embeddings):
        """
        Builds a fresh FAISS index from chunks + their embeddings.
        IMPORTANT: chunks and embeddings must be in the same order —
        FAISS returns positional indices, and we rely on
        position N in this list == embedding N.
        """
        self.chunks = chunks
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(embeddings)

    def save(self):
        faiss.write_index(self.index, str(self.index_path))
        with open(self.metadata_path, "wb") as f:
            pickle.dump(self.chunks, f)

    def load(self):
        self.index = faiss.read_index(str(self.index_path))
        with open(self.metadata_path, "rb") as f:
            self.chunks = pickle.load(f)

    def search(self, query_embedding, top_k: int = 3):
        """
        Returns the top_k closest Chunks to the query embedding,
        along with their distance scores (lower = more similar).
        """
        distances, indices = self.index.search(query_embedding, top_k)

        results = []
        for rank, idx in enumerate(indices[0]):
            if idx == -1:  # FAISS returns -1 if fewer than top_k matches exist
                continue
            results.append({
                "chunk": self.chunks[idx],
                "distance": float(distances[0][rank])
            })
        return results