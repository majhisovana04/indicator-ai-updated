# app/market/company_summary.py — new, simple, no Gemini needed for the "not reliable" case
def build_company_answer(analysis: dict) -> str:
    if not analysis["available"]:
        return (
            f"I can share {analysis['symbol']}'s current price, but I can't provide "
            f"reliable technical analysis for it right now: {analysis['reason']}"
        )

    signals_text = ", ".join(analysis["signals"])
    return f"For {analysis['symbol']}: {signals_text}."