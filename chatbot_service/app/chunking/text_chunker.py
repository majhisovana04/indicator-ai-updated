# app/chunking/text_chunker.py

import re

from chatbot_service.app.models.chunk import Chunk
from chatbot_service.app.models.document import Document


class Chunker:
    """
    Splits documents into smaller searchable chunks.
    Chunk IDs are NOT assigned here — they're assigned once,
    globally, after all chunks (indicator + faq) are combined.
    """

    def split_document(self, document: Document) -> list[Chunk]:
        if not document.content.strip():
            return []

        # Extract the document's top-level title (the "# ..." line),
        # if present, so it can be prepended to EVERY chunk. Without
        # this, the title becomes its own isolated, sparse chunk that
        # only sometimes ranks in top-k retrieval — meaning the LLM
        # sometimes never sees what an acronym stands for at all.
        title_match = re.search(r"(?:^|\n)\s*#\s+([^\n]+)", document.content)
        title = title_match.group(1).strip() if title_match else None

        sections = re.split(r"\n##\s+", document.content)

        chunks = []

        for section in sections:
            section = section.strip()

            if not section:
                continue
            # Skip re-adding the title to itself if this section IS the title-only chunk
            if title and section.strip("# ").strip() == title:
                continue

            content = f"{document.source} — {title}\n\n{section}" if title else section


            chunk = Chunk(
                id=0,  # placeholder — real ID assigned later in main.py
                content=content,
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
