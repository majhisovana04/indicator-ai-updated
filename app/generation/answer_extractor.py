

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