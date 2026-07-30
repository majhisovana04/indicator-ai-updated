# build_index.py
from chatbot_service.app.loaders.document_loader import DocumentLoader
from chatbot_service.app.loaders.faq_loader import FAQLoader
from chatbot_service.app.chunking.text_chunker import Chunker
from chatbot_service.app.embedding.embedder import Embedder
from chatbot_service.app.vectorstore.vector_store import VectorStore

# --- Load and chunk everything, same as main.py ---
loader = DocumentLoader()
documents = loader.load_all_documents()

faq_loader = FAQLoader()
faq_entries = faq_loader.load_faq_entries(documents)

chunker = Chunker()
indicator_and_policy_chunks = chunker.chunk_documents(documents)

all_chunks = indicator_and_policy_chunks + faq_entries

for i, chunk in enumerate(all_chunks):
    chunk.id = i

print(f"Total chunks to embed: {len(all_chunks)}")

# --- Embed ---
embedder = Embedder()
embeddings = embedder.embed_chunks(all_chunks)

# --- Build and save FAISS index ---
store = VectorStore()
store.build(all_chunks, embeddings)
store.save()

print("Vector store built and saved successfully.")