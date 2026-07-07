from app.routing.router import Router, Route
from app.models.chunk import Chunk

router = Router()

def fake_result(doc_type, distance):
    chunk = Chunk(id=0, content="dummy", source="dummy.md", doc_type=doc_type)
    return [{"chunk": chunk, "distance": distance}]

cases = [
    ("faq", 0.39, Route.FAQ),
    ("policies", 0.62, Route.POLICY),
    ("indicators", 0.78, Route.LLM),
    ("indicators", 1.91, Route.FALLBACK),
    ("faq", 0.50, Route.LLM),
    ("policies", 1.05, Route.LLM),
    ("policies", 1.25, Route.FALLBACK), 
]

for doc_type, distance, expected in cases:
    result = router.decide(fake_result(doc_type, distance))
    status = "PASS" if result == expected else "FAIL"
    print(f"[{status}] doc_type={doc_type}, distance={distance} → got {result}, expected {expected}")