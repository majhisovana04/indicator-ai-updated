# from app.embedding.embedder import Embedder
# from app.vectorstore.vector_store import VectorStore
# from app.routing.router import Router
# from app.generation.response_executor import ResponseExecutor


# class AssistantPipeline:
#     def __init__(self):
#         self.embedder = Embedder()
#         self.store = VectorStore()
#         self.store.load()
#         self.router = Router()
#         self.executor = ResponseExecutor()

#     def ask(self, query: str, top_k: int = 3) -> dict:
#         query_vec = self.embedder.embed_query(query)
#         results = self.store.search(query_vec, top_k=top_k)

#         route = self.router.decide(results)
#         response = self.executor.execute(route, query, results)

#         return response


# if __name__ == "__main__":
#     pipeline = AssistantPipeline()

#     test_queries = [
#         "What does RSI above 70 mean?",
#         "Should I buy Bitcoin right now?",
#         "What is MACD used for?",
#     ]

#     for q in test_queries:
#         result = pipeline.ask(q)
#         print("=" * 60)
#         print(f"Query: {q}")
#         print(f"Tier  : {result['tier']} (distance={result['distance']})")
#         print(f"Answer: {result['answer']}")
#         print()

from app.embedding.embedder import Embedder
from app.vectorstore.vector_store import VectorStore
from app.routing.router import Router
from app.generation.response_executor import ResponseExecutor


class AssistantPipeline:
    """
    Orchestrates the full flow: embed query -> search -> route -> execute.
    This class has no side effects on import — it only runs when explicitly used.
    """

    def __init__(self):
        self.embedder = Embedder()
        self.store = VectorStore()
        self.store.load()
        self.router = Router()
        self.executor = ResponseExecutor()

    def ask(self, query: str, top_k: int = 3) -> dict:
        query_vec = self.embedder.embed_query(query)
        results = self.store.search(query_vec, top_k=top_k)
        route = self.router.decide(results)
        response = self.executor.execute(route, query, results)
        return response