from enum import Enum


class Route(Enum):
    """
    Possible actions after retrieval.
    """
    FAQ = "faq"
    POLICY = "policy"
    LLM = "llm"
    FALLBACK = "fallback"


FAQ_THRESHOLD = 0.5
POLICY_THRESHOLD = 1.00
GENERAL_THRESHOLD = 1.20


class Router:
    """
    Decides how the assistant should respond based on retrieval results.
    Contains NO generation logic — only routing decisions.
    """

    def decide(self, results: list) -> Route:
        """
        Parameters
        ----------
        results : list
            Output from VectorStore.search() — list of dicts with
            'chunk' and 'distance', sorted by relevance (best first).

        Returns
        -------
        Route
        """
        if not results:
            return Route.FALLBACK

        top = results[0]
        top_chunk = top["chunk"]
        top_distance = top["distance"]

        if top_chunk.doc_type == "faq" and top_distance < FAQ_THRESHOLD:
            return Route.FAQ

        if top_chunk.doc_type == "policies" and top_distance < POLICY_THRESHOLD:
            return Route.POLICY

        if top_distance < GENERAL_THRESHOLD:
            return Route.LLM

        return Route.FALLBACK