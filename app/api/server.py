# app/api/server.py
from fastapi import FastAPI, HTTPException
from app.pipeline import AssistantPipeline
from app.api.schemas import ChatRequest, ChatResponse

app = FastAPI(title="Indicator AI Assistant")

# Load the pipeline ONCE when the server starts — not every time
# someone asks a question. Loading the embedding model + FAISS index
# is slow, so we don't want to repeat it per request.
pipeline = AssistantPipeline()


@app.post("/api/bot/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        result = pipeline.ask(request.query)
    except Exception:
        raise HTTPException(status_code=503, detail="Assistant is temporarily unavailable. Please try again.")

    return ChatResponse(
        answer=result["answer"]
        # tier=result["tier"],
        # source=result.get("source"),
        # distance=result.get("distance")
    )


@app.get("/health")
def health():
    return {"status": "ok"}