# import re
# from app.models.chunk import Chunk


# class AnswerExtractor:
#     """
#     Extracts clean, user-facing text from FAQ and Policy chunks,
#     stripping markdown headers and labels.
#     """

#     @staticmethod
#     def extract_faq_answer(chunk: Chunk) -> str:
#         match = re.search(r"Answer:\s*(.+)", chunk.content, re.DOTALL)
#         if match:
#             return match.group(1).strip()
#         return chunk.content.strip()
#     @staticmethod
#     def extract_policy_response(chunk: Chunk) -> str:
#         """
#         Policy chunks (after Chunker's ## split) look like:
#             Should I buy Bitcoin?

#             I can't recommend buying or selling financial assets...
#         The first line is the question; everything after the first
#         blank line is the actual response.
#         """
#         lines = chunk.content.strip().split("\n", 1)
#         if len(lines) > 1:
#             return lines[1].strip()
#         return chunk.content.strip()

# app/generation/answer_extractor.py
from app.models.chunk import Chunk


class AnswerExtractor:
    """
    Extracts clean, user-facing text from FAQ and Policy chunks.
    Both use the same shape: "## Question" header followed by
    the answer/response text on the next line(s).
    """

    @staticmethod
    def extract_answer(chunk: Chunk) -> str:
        lines = chunk.content.strip().split("\n", 1)
        if len(lines) > 1:
            return lines[1].strip()
        return chunk.content.strip()