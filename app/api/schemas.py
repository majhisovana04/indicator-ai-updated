# app/api/schemas.py
from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    answer: str
    # tier: str
    # source: str | None = None
    # distance: float | None = None