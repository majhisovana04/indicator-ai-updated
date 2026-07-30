# app/models/document.py
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Document:
    """
    Represents one document loaded from the knowledge base.
    """

    source: str          # rsi.md
    doc_type: str        # indicators / faq / policies
    path: Path           # Full file path
    content: str         # Markdown content