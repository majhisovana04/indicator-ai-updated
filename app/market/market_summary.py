from datetime import datetime
from app.generation.llm_generator import LLMGenerator


class MarketSummaryGenerator:
    def __init__(self):
        self.llm = LLMGenerator()

    def generate(self, candidates: list[dict], sentiment: str) -> str:
        timestamp = datetime.now().strftime("%d %b %Y, %I:%M %p")

        if not candidates:
            return (
                f"As of {timestamp}, no companies currently show strong enough "
                f"technical confluence (at least 2 agreeing signals). "
                f"Market sentiment: {sentiment}. "
                f"This reflects technical indicator signals, not investment advice."
            )

        candidate_text = "\n".join(
            f"- {c['symbol']}: {', '.join(c['signals'])}" for c in candidates
        )

        prompt = f"""You are a trading indicator assistant. Based ONLY on the technical
signals below (as of {timestamp}), write a short, beginner-friendly summary.

Market sentiment today: {sentiment}
Companies showing multiple agreeing technical signals:
{candidate_text}

Rules:
- Explain WHY each company qualified, using the listed signals.
- Describe this as "technical signals show" — never as "you should buy".
- End with: "This reflects technical indicator signals as of {timestamp}, not investment advice. Please do your own research or consult a registered advisor."
- Keep it concise and beginner-friendly.
"""
        try:
            return self.llm.generate_from_prompt(prompt)  # now uses shared retry logic
        except RuntimeError:
            # Retry+backoff already happened inside llm_generator's underlying
            # calls where used elsewhere; this is a final safety net for the
            # direct client call here. Never let this crash the scheduler.
            return (
                f"As of {timestamp}, market sentiment appears {sentiment}, but a "
                f"detailed summary could not be generated right now due to a "
                f"temporary service issue. Please check back shortly."
            )
