# from app.loaders.document_loader import DocumentLoader
# from app.loaders.faq_loader import FAQLoader
# from app.chunking.text_chunker import Chunker

# loader = DocumentLoader()
# documents = loader.load_all_documents()

# faq_loader = FAQLoader()
# faq_entries = faq_loader.load_faq_entries(documents)

# chunker = Chunker()
# indicator_chunks = chunker.chunk_documents(documents)

# # Combine everything into ONE list, then assign final IDs
# all_chunks = indicator_chunks + faq_entries

# for i, chunk in enumerate(all_chunks):
#     chunk.id = i  # overwrite with a clean, globally unique ID

# print(f"\nTotal combined chunks: {len(all_chunks)}\n")

# for chunk in all_chunks:
#     print("=" * 60)
#     print(f"Chunk ID : {chunk.id}")
#     print(f"Source   : {chunk.source}")
#     print(f"Type     : {chunk.doc_type}")
#     print("\nContent:\n")
#     print(chunk.content)
#     print()



# print(f"\nLoaded {len(documents)} documents.\n")

from app.pipeline import AssistantPipeline


def run_manual_tests():
    pipeline = AssistantPipeline()

    test_queries = [
        "What does RSI above 70 mean?",
        "Should I buy Bitcoin right now?",
        "What is MACD used for?",
        "How does momentum affect RSI readings?",
    ]

    for q in test_queries:
        result = pipeline.ask(q)
        print("=" * 60)
        print(f"Query: {q}")
        print(f"Tier  : {result['tier']} (distance={result['distance']})")
        print(f"Answer: {result['answer']}")
        print()


if __name__ == "__main__":
    run_manual_tests()