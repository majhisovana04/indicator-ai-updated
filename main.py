from app.loaders.document_loader import DocumentLoader
from app.loaders.faq_loader import FAQLoader
from app.chunking.text_chunker import Chunker

loader = DocumentLoader()
documents = loader.load_all_documents()

faq_loader = FAQLoader()
faq_entries = faq_loader.load_faq_entries(documents)

chunker = Chunker()
indicator_chunks = chunker.chunk_documents(documents)

# Combine everything into ONE list, then assign final IDs
all_chunks = indicator_chunks + faq_entries

for i, chunk in enumerate(all_chunks):
    chunk.id = i  # overwrite with a clean, globally unique ID

print(f"\nTotal combined chunks: {len(all_chunks)}\n")

for chunk in all_chunks:
    print("=" * 60)
    print(f"Chunk ID : {chunk.id}")
    print(f"Source   : {chunk.source}")
    print(f"Type     : {chunk.doc_type}")
    print("\nContent:\n")
    print(chunk.content[:200])
    print()



print(f"\nLoaded {len(documents)} documents.\n")

for doc in documents:

    print("=" * 60)
    print(f"Source    : {doc.source}")
    print(f"Type      : {doc.doc_type}")
    print(f"Path      : {doc.path}")
    print(f"Characters: {len(doc.content)}")

for entry in faq_entries:
    
    print("-" * 60)
    print(f"Source : {entry.source}")
    print(f"Content: {entry.content}")

print(f"\nTotal Chunks: {len(indicator_chunks)}\n")

for chunk in indicator_chunks:

    print("=" * 60)

    print(f"Chunk ID : {chunk.id}")
    print(f"Source   : {chunk.source}")
    print(f"Type     : {chunk.doc_type}")

    print("\nContent:\n")

    print(chunk.content[:200])      # first 200 characters

    print()


