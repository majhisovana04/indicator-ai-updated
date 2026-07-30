# app/loaders/document_loader.py

from pathlib import Path

from chatbot_service.app.models.document import Document


# Root knowledge base folder
KNOWLEDGE_BASE = Path("knowledge_base")


class DocumentLoader:
    """
    Loads all markdown files from the knowledge base.
    """

    def __init__(self, knowledge_base: Path = KNOWLEDGE_BASE):
        self.knowledge_base = knowledge_base

    def load_all_documents(self) -> list[Document]:
        """
        Loads every markdown file from the knowledge base.

        Returns:
            List[Document]
        """

        documents = []

        for file in self.knowledge_base.rglob("*.md"):

            document = Document(
                source=file.name,
                doc_type=file.parent.name,
                path=file,
                content=file.read_text(encoding="utf-8")
            )

            documents.append(document)

        return documents