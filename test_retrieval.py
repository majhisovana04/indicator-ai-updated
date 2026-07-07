from app.embedding.embedder import Embedder
from app.vectorstore.vector_store import VectorStore

embedder = Embedder()
store = VectorStore()
store.load()

def ask(query: str, top_k: int = 3):
    query_vec = embedder.embed_query(query)
    results = store.search(query_vec, top_k=top_k)

    print(f"\nQuery: {query}")
    for r in results:
        chunk = r["chunk"]
        print(f"  [{chunk.doc_type}] {chunk.source} (id={chunk.id}, dist={r['distance']:.3f})")
        print(f"  {chunk.content}")
        print()

if __name__ == "__main__":
    ask("What does RSI above 70 mean?")
    ask("Should I buy Bitcoin right now?")
    ask("What is MACD used for?")