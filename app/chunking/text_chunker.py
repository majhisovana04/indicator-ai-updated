# app/chunking/text_chunker.py

import re

from app.models.chunk import Chunk
from app.models.document import Document


class Chunker:
    """
    Splits documents into smaller searchable chunks.
    Chunk IDs are NOT assigned here — they're assigned once,
    globally, after all chunks (indicator + faq) are combined.
    """

    def split_document(self, document: Document) -> list[Chunk]:
        if not document.content.strip():
            return []

        sections = re.split(r"\n##\s+", document.content)

        chunks = []

        for section in sections:
            section = section.strip()

            if not section:
                continue

            chunk = Chunk(
                id=0,  # placeholder — real ID assigned later in main.py
                content=section,
                source=document.source,
                doc_type=document.doc_type
            )

            chunks.append(chunk)

        return chunks

    def chunk_documents(self, documents: list[Document]) -> list[Chunk]:
        all_chunks = []

        for document in documents:
            if document.doc_type == "faq":
                continue

            chunks = self.split_document(document)
            all_chunks.extend(chunks)

        return all_chunks
