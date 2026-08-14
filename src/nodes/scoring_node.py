"""
PHASE 3 — SCORING
transcript -> 1-5 + evidence quote + confidence
guardrail -> score without a quote is REJECTED
outputs -> scorecard.json, transcript.json, report.pdf
"""
import json
from pathlib import Path
from src.llm_client import llm_json_retry
from src.guardrails.evidence_check import validate_scorecard

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "scorer_v2.md"


def scoring_node(state: dict) -> dict:
    system_prompt = PROMPT_PATH.read_text()
    transcript = state.get("transcript", [])
    question_plan = state.get("question_plan", {})

    github_grounded_asked = sum(
        1 for t in transcript
        if t["speaker"] == "agent" and t["node"] == "github_deepdive"
    )

    # Compact JSON instead of indent=2 (whitespace alone was costing real
    # tokens), and strip question_plan down to just what the scorer needs
    # for competency mapping — the full plan objects (source_reference,
    # difficulty, follow_up_triggers) aren't needed here and this node hit
    # the same TPM ceiling the question planner did (see question_planner.py)
    # once transcripts got long enough. Scoring quality depends on the full
    # transcript being present, so that's kept complete — everything else
    # is trimmed instead.
    compact_questions = [
        {"id": q.get("id"), "text": q.get("text"), "competency": q.get("competency")}
        for q in question_plan.get("questions", [])
    ]
    user_prompt = (
        f"CANDIDATE: {state.get('candidate_name', '')}\n"
        f"ROLE: {state.get('role_title', '')}\n"
        f"QUESTION PLAN (for competency mapping):\n{json.dumps(compact_questions)}\n\n"
        f"FULL TRANSCRIPT:\n{json.dumps(transcript, separators=(',', ':'))}"
    )

    scorecard = llm_json_retry(system_prompt, user_prompt, max_tokens=1800)
    scorecard["github_grounded_questions_asked"] = github_grounded_asked
    scorecard["guardrail_flags"] = state.get("guardrail_flags", [])

    # Guardrail (b) enforcement — the actual REJECTION happens here, not
    # just in the prompt's instructions to the model.
    scorecard = validate_scorecard(scorecard, transcript)

    Path("output").mkdir(parents=True, exist_ok=True)
    Path("output/scorecard.json").write_text(json.dumps(scorecard, indent=2))
    Path("output/transcript.json").write_text(json.dumps({"turns": transcript}, indent=2))

    return {"scorecard": scorecard, "current_node": "scoring"}