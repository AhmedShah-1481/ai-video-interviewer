"""
Requirement #9 proof: "guardrails/ + test proving both fire". Run with:
    pytest tests/test_guardrails.py -v
No API key needed — both guardrails are pure logic, no LLM call involved.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.guardrails.banned_questions import check_question, filter_question_plan
from src.guardrails.evidence_check import quote_exists_in_transcript, validate_scorecard


# --- Guardrail (a): banned questions blocked before reaching the candidate ---

def test_banned_question_blocked_per_category():
    cases = {
        "age": "How old are you?",
        "gender": "What gender do you identify as?",
        "marital": "Are you married?",
        "religion": "What is your religion?",
        "nationality": "What is your nationality?",
        "health": "Do you have any health conditions we should know about?",
        "salary_history": "What is your current salary?",
        "politics": "Who did you vote for?",
    }
    for expected_category, text in cases.items():
        result = check_question(text)
        assert result["blocked"] is True, f"expected {text!r} to be blocked"
        assert result["category"] == expected_category


def test_legitimate_technical_question_not_blocked():
    result = check_question("Walk me through how you'd debug a retrieval quality regression.")
    assert result["blocked"] is False
    assert result["category"] is None


def test_filter_question_plan_removes_banned_and_logs_flag():
    plan = {"questions": [
        {"id": "q1", "text": "What is your current salary?"},
        {"id": "q2", "text": "Tell me about a project you shipped."},
    ]}
    filtered = filter_question_plan(plan)
    ids_kept = [q["id"] for q in filtered["questions"]]
    assert ids_kept == ["q2"], "banned question q1 must be removed, q2 must survive"
    assert len(filtered["guardrail_flags"]) == 1
    assert filtered["guardrail_flags"][0]["category"] == "salary_history"


def test_recruiter_hand_edited_banned_question_still_blocked():
    # Guardrail (a) must catch a banned question even if a recruiter typed
    # it in by hand during the HITL edit step, not just LLM-generated ones.
    plan = {"questions": [{"id": "q1", "text": "Are you planning to have kids soon?"}]}
    filtered = filter_question_plan(plan)
    assert filtered["questions"] == []
    assert filtered["guardrail_flags"][0]["category"] == "marital"


# --- Guardrail (b): no score without a transcript quote ---

TRANSCRIPT = [
    {"speaker": "agent", "text": "Tell me about your RAG project.", "node": "resume_probe"},
    {"speaker": "candidate", "text": "I used a 500 token chunk size with no overlap, which caused split definitions.", "node": "resume_probe"},
]


def test_real_quote_found_exact():
    assert quote_exists_in_transcript("500 token chunk size with no overlap", TRANSCRIPT) is True


def test_real_quote_found_fuzzy_minor_wording_diff():
    # Simulates a small TTS/STT round-trip diff — still the same quote.
    assert quote_exists_in_transcript("500 token chunk size, no overlap", TRANSCRIPT) is True


def test_fabricated_quote_not_found():
    assert quote_exists_in_transcript("I have five years of production Kubernetes experience", TRANSCRIPT) is False


def test_empty_quote_not_found():
    assert quote_exists_in_transcript("", TRANSCRIPT) is False


def test_validate_scorecard_rejects_score_with_no_verifiable_quote():
    scorecard = {
        "competencies": [
            {"name": "technical depth", "score": 5, "evidence_quote": "500 token chunk size with no overlap"},
            {"name": "fabricated", "score": 5, "evidence_quote": "I shipped this to ten million users last year"},
        ],
        "guardrail_flags": [],
    }
    validated = validate_scorecard(scorecard, TRANSCRIPT)
    kept = {c["name"]: c for c in validated["competencies"]}
    assert kept["technical depth"]["score"] == 5
    assert kept["technical depth"].get("rejected", False) is False
    assert kept["fabricated"]["score"] is None
    assert kept["fabricated"]["rejected"] is True
    assert any(f["action"] == "score_rejected_no_verifiable_quote" for f in validated["guardrail_flags"])


if __name__ == "__main__":
    import subprocess
    subprocess.run(["pytest", __file__, "-v"])
