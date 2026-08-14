"""
question_planner -> 12 Qs {competency, source, difficulty}
>=3 MUST cite the candidate's real code

Validates its own output against the hard requirements before returning,
and retries once with an explicit correction message if the LLM under-shoots
the github-grounded minimum — this is the guardrail that prevents "generic
questions labeled as github" (see prompts/ITERATION_NOTES.md, v1 failure).
"""
import json
from pathlib import Path
from src.llm_client import llm_json_retry

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "question_planner_v2.md"


def _count_valid_github_questions(questions: list[dict]) -> int:
    count = 0
    for q in questions:
        if q.get("source") != "github":
            continue
        ref = (q.get("source_reference") or "").strip()
        # A valid github reference names an actual artifact, not just "github"
        if ref and ref.lower() not in {"github", "n/a", "none", ""}:
            count += 1
    return count


def plan_questions(jd: dict, resume: dict, github: dict, gap_analysis: dict) -> dict:
    system_prompt = PROMPT_PATH.read_text()
    # Truncation sized to fit comfortably under Groq's smaller-model TPM
    # limits (e.g. llama-3.1-8b-instant's 6000 TPM) as well as the larger
    # model's daily cap — a big prompt burns quota fast either way, and
    # this node runs once per interview, not something worth spending your
    # daily budget on. If you need richer GitHub context for grounding
    # quality, raise these once you're on a model/tier with more headroom.
    user_prompt = (
        f"JD:\n{json.dumps(jd, indent=2)[:1500]}\n\n"
        f"RESUME:\n{json.dumps(resume, indent=2)[:1500]}\n\n"
        f"GITHUB (repos with real source samples — cite these specifically):\n"
        f"{json.dumps(github, indent=2)[:2500]}\n\n"
        f"GAP ANALYSIS (use unsupported_claims_to_verify for verify questions):\n"
        f"{json.dumps(gap_analysis, indent=2)[:1000]}"
    )

    result = llm_json_retry(system_prompt, user_prompt, max_tokens=2000)
    questions = result.get("questions", [])

    github_count = _count_valid_github_questions(questions)
    if github_count < 3:
        correction = (
            f"GITHUB-GROUNDED QUESTION COUNT: your previous attempt only had "
            f"{github_count} valid github-grounded questions (need >=3, each "
            "with a real repo/file/commit in source_reference — not the word "
            "'github'). Same JD/RESUME/GITHUB/GAP ANALYSIS context as before. "
            "Regenerate the full 12-question plan, fixing this.\n\n" + user_prompt
        )
        result = llm_json_retry(system_prompt, correction, max_tokens=2000)
        questions = result.get("questions", [])
        github_count = _count_valid_github_questions(questions)
        if github_count < 3:
            raise ValueError(
                f"question_planner failed the >=3 github-grounded requirement twice "
                f"(got {github_count}). Check that github.json actually has source_samples "
                "— if the candidate's repos are empty or fetch failed, this is expected "
                "and should be logged, not silently passed downstream."
            )

    result["approved_by_human"] = False  # set True only by the HITL gate
    result["edits_made"] = []
    return result


def plan_questions_from_files(
    jd_path="output/prep/jd.json",
    resume_path="output/prep/resume.json",
    github_path="output/prep/github.json",
    gap_path="output/prep/gap_analysis.json",
    output_path="output/prep/question_plan.json",
) -> dict:
    jd = json.loads(Path(jd_path).read_text())
    resume = json.loads(Path(resume_path).read_text())
    github = json.loads(Path(github_path).read_text())
    gap = json.loads(Path(gap_path).read_text())
    result = plan_questions(jd, resume, github, gap)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    out = plan_questions_from_files()
    print(json.dumps(out, indent=2))