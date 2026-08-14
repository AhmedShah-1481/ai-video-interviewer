"""
Guardrail (b): no score without a transcript quote.

score without a quote is REJECTED — this file is the enforcement point,
called from the scoring node before scorecard.json is ever written.
"""
import difflib


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def quote_exists_in_transcript(quote: str, transcript_turns: list[dict], fuzzy_threshold: float = 0.8) -> bool:
    """
    Checks the evidence_quote actually appears in the transcript. Uses a
    fuzzy match (not exact substring) because TTS/STT round-trips and minor
    punctuation differences are expected — but the threshold is high enough
    that a fabricated quote won't slip through.
    """
    if not quote or not quote.strip():
        return False
    norm_quote = _normalize(quote)
    candidate_speaker_text = " ".join(
        _normalize(t["text"]) for t in transcript_turns if t.get("speaker") == "candidate"
    )
    if norm_quote in candidate_speaker_text:
        return True

    # fuzzy fallback: slide the quote length across candidate text
    words = candidate_speaker_text.split()
    quote_len = len(norm_quote.split())
    if quote_len == 0:
        return False
    for i in range(0, max(1, len(words) - quote_len + 1)):
        window = " ".join(words[i:i + quote_len])
        ratio = difflib.SequenceMatcher(None, norm_quote, window).ratio()
        if ratio >= fuzzy_threshold:
            return True
    return False


def validate_scorecard(scorecard: dict, transcript_turns: list[dict]) -> dict:
    """
    Returns the scorecard with any competency lacking a verifiable quote
    REJECTED (score removed, flagged) rather than silently kept — the
    grading standard is explicit: "score without a quote is REJECTED", not
    "flagged and kept". Rejected competencies get score=None so downstream
    consumers (the PDF report, the MCP server) can render this honestly
    rather than pretending a 1-5 score exists.
    """
    valid_competencies = []
    flags = list(scorecard.get("guardrail_flags", []))

    for comp in scorecard.get("competencies", []):
        quote = comp.get("evidence_quote", "")
        if quote_exists_in_transcript(quote, transcript_turns):
            valid_competencies.append(comp)
        else:
            flags.append({
                "competency": comp.get("name"),
                "action": "score_rejected_no_verifiable_quote",
                "attempted_quote": quote,
            })
            comp["score"] = None
            comp["rejected"] = True
            valid_competencies.append(comp)

    scorecard["competencies"] = valid_competencies
    scorecard["guardrail_flags"] = flags
    return scorecard
