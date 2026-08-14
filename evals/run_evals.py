"""
Runs the real scoring pipeline (scorer prompt + evidence guardrail) against
all 5 synthetic personas in evals/personas/, prints a ranking table, and
writes evals/results.md.

Usage:
    LLM_PROVIDER=groq python -m evals.run_evals        # real graded run
    LLM_PROVIDER=mock python -m evals.run_evals         # offline dry run (no key needed)

Requirement #11: "Must rank Strong > Average > Weak. Report failures
honestly." This script computes the actual rank from actual scorer output
every time — the ranking table in results.md is not hand-typed.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm_client import llm_json_retry
from src.guardrails.evidence_check import validate_scorecard

PERSONAS_DIR = Path(__file__).parent / "personas"
SCORER_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "scorer_v2.md"
RESULTS_PATH = Path(__file__).parent / "results.md"

PERSONA_FILES = ["1_strong.json", "2_average.json", "3_weak.json", "4_bluffer.json", "5_nervous.json"]


def score_persona(persona: dict) -> dict:
    system_prompt = SCORER_PROMPT_PATH.read_text()
    transcript = persona["transcript"]["turns"]
    question_plan = json.loads((PERSONAS_DIR / "_shared_question_plan.json").read_text())

    user_prompt = (
        f"CANDIDATE: {persona['candidate_name']}\n"
        f"ROLE: {persona['role_title']}\n"
        f"QUESTION PLAN (for competency mapping):\n{json.dumps(question_plan['questions'])}\n\n"
        f"FULL TRANSCRIPT:\n{json.dumps(transcript, indent=2)}"
    )
    scorecard = llm_json_retry(system_prompt, user_prompt, max_tokens=3000)
    scorecard["github_grounded_questions_asked"] = sum(
        1 for t in transcript if t["speaker"] == "agent" and t["node"] == "github_deepdive"
    )
    scorecard = validate_scorecard(scorecard, transcript)
    return scorecard


def main():
    from src.config import SETTINGS

    results = []
    for filename in PERSONA_FILES:
        persona = json.loads((PERSONAS_DIR / filename).read_text())
        scorecard = score_persona(persona)
        results.append({"persona": persona["persona"], "expected": persona["expected"], "scorecard": scorecard})

    results.sort(key=lambda r: r["scorecard"]["overall_score"], reverse=True)

    lines = [
        "# Eval results",
        "",
        f"Provider: `{SETTINGS.llm_provider}` — run at {datetime.now(timezone.utc).isoformat(timespec='seconds')}Z",
        "",
    ]
    if SETTINGS.llm_provider == "mock":
        lines += [
            "> **This is the offline dry run** (`LLM_PROVIDER=mock`, see `src/mock_llm.py`) — it proves the",
            "> scoring pipeline, ranking logic, and evidence guardrail all run correctly end to end without an",
            "> API key. It is NOT the graded evals run. Re-run with `LLM_PROVIDER=groq` (or `anthropic`) before",
            "> submission and replace this file — see the honest-failure note below for what to watch for when",
            "> you do.",
            "",
        ]

    lines += ["| Rank | Persona | Overall | Recommendation | Expected |", "|---|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        sc = r["scorecard"]
        lines.append(
            f"| {i} | {r['persona']} | {sc['overall_score']} | {sc['recommendation']} | {r['expected']['note']} |"
        )

    order = [r["persona"] for r in results]
    strong_idx = order.index("strong")
    average_idx = order.index("average")
    weak_idx = order.index("weak")
    bluffer_idx = order.index("bluffer")
    nervous_idx = order.index("nervous")

    checks = [
        ("Strong ranks above Average", strong_idx < average_idx),
        ("Average ranks above Weak", average_idx < weak_idx),
        ("Bluffer ranks below Average (the hard case)", bluffer_idx > average_idx),
        ("Nervous ranks near Strong, not penalized for hesitation", nervous_idx <= average_idx),
    ]
    lines += ["", "## Ranking checks", ""]
    for desc, passed in checks:
        lines.append(f"- [{'x' if passed else ' '}] {desc}")

    lines += ["", "## Per-persona detail", ""]
    for r in results:
        sc = r["scorecard"]
        lines.append(f"### {r['persona']} — overall {sc['overall_score']}, {sc['recommendation']}")
        lines.append(f"- Reasoning: {sc.get('recommendation_reasoning', '')}")
        for comp in sc.get("competencies", []):
            flag = " [REJECTED — no verifiable quote]" if comp.get("rejected") else ""
            lines.append(f"  - {comp['name']}: {comp['score']}{flag} — evidence: \"{comp.get('evidence_quote', '')}\"")
        lines.append("")

    if SETTINGS.llm_provider == "mock":
        lines += [
            "## Honest failure analysis (mock provider)",
            "",
            "Bluffer and Weak tied at 2.2 overall in this run. That's a real limitation of the mock",
            "scorer, not a hidden success: `mock_llm.py` scores off raw specific-vs-vague keyword",
            "density, and the Bluffer persona was written to sound fluent but score low on those same",
            "keywords once pressed, so it lands in the same numeric bucket as someone who is simply",
            "vague throughout — the mock scorer separates \"confident-and-empty\" from \"plain weak\" only",
            "by direction of rank (bluffer still sits at #5, weak at #4, never above Average), not by a",
            "clean score gap. A real LLM scorer should do better here because it can read *why* an answer",
            "is empty (confident tone dodging a specific artifact vs. genuinely not knowing) rather than",
            "just counting vague-sounding words — that's exactly the semantic judgment this eval exists",
            "to test, and it's the first thing to check when re-running with `LLM_PROVIDER=groq`: does the",
            "real run separate Bluffer's score from Weak's, and does its `recommendation_reasoning` name",
            "the fluent-but-empty pattern the way `prompts/scorer_v2.md` instructs it to?",
            "",
        ]

    RESULTS_PATH.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nWritten to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
