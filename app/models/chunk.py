# app/models/chunk.py

from dataclasses import dataclass


@dataclass
class Chunk:
    """
    Represents one searchable chunk.
    """

    id: int
    content: str
    source: str
    doc_type: str
    section: str | None = None