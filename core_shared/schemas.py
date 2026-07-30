# app/api/schemas.py
from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    answer: str
    # tier: str
    # source: str | None = None
    # distance: float | None = None

class SignalMatrixEntry(BaseModel):
    symbol: str
    arrows: dict[str, str]
    ai_signal: str
    confidence: int
    score: int


class SignalMatrixResponse(BaseModel):
    count: int
    results: list[SignalMatrixEntry]