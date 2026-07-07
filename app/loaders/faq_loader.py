# # app/loaders/faq_loader.py
# from app.models.document import Document
# from app.models.chunk import Chunk


# class FAQLoader:

#     @staticmethod
#     def split_blocks(content: str) -> list[str]:
#         """Split FAQ markdown using '---' as the block separator."""
#         return [
#             block.strip()
#             for block in content.split("---")
#             if block.strip()
#         ]

#     def load_faq_entries(self, documents: list[Document]) -> list[dict]:
#         """
#         Extracts FAQ entries from a list of already-loaded documents.
#         """
#         faq_entries = []

#         for doc in documents:
#             if doc.doc_type != "faq":
#                 continue

#             for block in self.split_blocks(doc.content):
#                 faq_entries.append(
#                 #     {"source": doc.source,
#                 #     "content": block}
#                                 Chunk(

#                     id=-1,           # temporary

#                     content=block,

#                     source=doc.source,

#                     doc_type="faq"

#                 )
#                 )

#         return faq_entries

from app.models.document import Document
from app.models.chunk import Chunk


class FAQLoader:

    @staticmethod
    def split_blocks(content: str) -> list[str]:
        """Split FAQ markdown using '---' as the block separator."""
        return [
            block.strip()
            for block in content.split("---")
            if block.strip()
        ]

    def load_faq_entries(self, documents: list[Document]) -> list[Chunk]:
        faq_entries = []

        for doc in documents:
            if doc.doc_type != "faq":
                continue

            for block in self.split_blocks(doc.content):
                faq_entries.append(
                    Chunk(
                        id=0,  # placeholder — real ID assigned later in main.py
                        content=block,
                        source=doc.source,
                        doc_type="faq"
                    )
                )

        return faq_entries