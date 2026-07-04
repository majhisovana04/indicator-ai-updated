import re

from app.models.chunk import Chunk
from app.models.document import Document


class Chunker:
    """
    Splits documents into smaller searchable chunks.
    """

    def __init__(self):
        self.chunk_id = 1

    def split_document(self, document: Document) -> list[Chunk]:
            # Skip empty documents
        if not document.content.strip():
            return []


        sections = re.split(r"\n##\s+", document.content)

        chunks = []

        for section in sections:

            section = section.strip()

            if not section:
                continue

            chunk = Chunk(
                id=self.chunk_id,
                content=section,
                source=document.source,
                doc_type=document.doc_type
            )

            chunks.append(chunk)

            self.chunk_id += 1

        return chunks

    def chunk_documents(self, documents: list[Document]) -> list[Chunk]:

        all_chunks = []

        for document in documents:
            # FAQ files are already split separately
            if document.doc_type == "faq":
                continue

            chunks = self.split_document(document)

            all_chunks.extend(chunks)

        return all_chunks

# import re

# from app.models.chunk import Chunk
# from app.models.document import Document


# class Chunker:
#     """
#     Splits documents into searchable chunks based on document type.
#     """

#     def split_document(self, document: Document) -> list[Chunk]:
#         """
#         Split a single document into chunks.
#         """

#         if not document.content.strip():
#             return []

#         # -------- Indicator Documents --------
#         if document.doc_type == "indicators":
#             sections = re.split(r"\n##\s+", document.content)

#         # -------- Policy Documents --------
#         elif document.doc_type == "policies":

#             # First split by ## headings
#             major_sections = re.split(r"\n##\s+", document.content)

#             sections = []

#             for part in major_sections:

#                 part = part.strip()

#                 if not part:
#                     continue

#                 # If this section contains multiple examples,
#                 # split them using ---
#                 if "---" in part:

#                     sub_sections = [
#                         block.strip()
#                         for block in part.split("---")
#                         if block.strip()
#                     ]

#                     sections.extend(sub_sections)

#                 else:
#                     sections.append(part)

#         # -------- Everything Else --------
#         else:
#             sections = [document.content]

#         chunks = []

#         for section in sections:

#             section = section.strip()

#             if not section:
#                 continue

#             chunks.append(
#                 Chunk(
#                      id=self.chunk_id,
#                     content=section,
#                     source=document.source,
#                     doc_type=document.doc_type,
#                 )
#             )

#         return chunks

#     def chunk_documents(self, documents: list[Document]) -> list[Chunk]:
#         """
#         Chunk all supported documents.
#         FAQ files are skipped because FAQLoader already processes them.
#         """

#         all_chunks = []

#         for document in documents:

#             if document.doc_type == "faq":
#                 continue

#             all_chunks.extend(self.split_document(document))

#         return all_chunks