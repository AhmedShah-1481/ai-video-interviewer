"""
Deterministic, keyword-based stand-in for a real LLM call. LLM_PROVIDER=mock
routes here (see llm_client._call_mock). ONLY used for offline dev/CI and
for the dry-run recorded in evals/results.md's "mock-provider pass" — the
real, graded evals run uses LLM_PROVIDER=groq or anthropic (see
evals/run_evals.py and evals/results.md for the honest split between the
two).

This intentionally does NOT try to be a good interviewer or a good judge —
it is pattern-matching on the prompt/text, not reasoning about it. Its only
job is to prove the plumbing (schemas, guardrails, routing) works when no
API key is available, and — for the scorer specifically — to give a
transparent, inspectable stand-in for "specific vs. vague" so evals/ can
run end to end offline. Read this file if you want to know exactly how the
mock score was computed; there's no hidden judgment here, just word lists.
"""
import re

SPECIFIC_MARKERS = [
    "because", "trade-off", "tradeoff", "specifically", "for example", "commit",
    "line ", "function", "token", "overlap", "threshold", "recall", "precision",
    "cosine", "embedding", "eval set", "metric", "p95", "redis", "json", "retry",
    "chunk", "line 3", "%",
]
VAGUE_MARKERS = [
    "kind of", "i guess", "just generally", "not really sure", "you know",
    "general approach", "i don't remember", "i'm not sure", "not totally sure",
    "pretty much", "industry standard", "best practice stuff", "generally speaking",
    "usually just", "in general", "honestly it's pretty much", "strong intuition",
    "good instinct", "i don't know", "not sure", "i don't have the exact",
]
# Hesitation/filler is NOT penalized — this is the whole point of the
# Nervous persona (fairness case). Listed here only so it's explicit that
# these are deliberately excluded from VAGUE_MARKERS, not forgotten.
FILLER_NOT_PENALIZED = ["um", "sorry", "let me start over", "let me think", "...", "one second"]

COMPETENCY_NODE_MAP = {
    "technical depth": "github_deepdive",
    "decomposition": "jd_fit",
    "shipping ability": "resume_probe",
    "debugging": "scenario",
    "communication": "candidate_qs",
}


def _score_text(text: str) -> tuple[int, int]:
    t = text.lower()
    specific = sum(t.count(m) for m in SPECIFIC_MARKERS)
    vague = sum(t.count(m) for m in VAGUE_MARKERS)
    return specific, vague


def _candidate_turns_for_node(transcript: list[dict], node: str) -> list[dict]:
    return [t for t in transcript if t.get("speaker") == "candidate" and t.get("node") == node]


def _first_words(text: str, n: int = 12) -> str:
    words = text.split()
    return " ".join(words[:n])


def _score_scorecard(user_prompt: str) -> dict:
    import json as _json

    # Pull transcript back out of the user prompt (scoring_node embeds it as
    # 'FULL TRANSCRIPT:\n<json>').
    m = re.search(r"FULL TRANSCRIPT:\n(.*)", user_prompt, re.DOTALL)
    transcript = _json.loads(m.group(1)) if m else []
    name_m = re.search(r"CANDIDATE: (.*)", user_prompt)
    role_m = re.search(r"ROLE: (.*)", user_prompt)
    candidate_name = name_m.group(1).strip() if name_m else ""
    role = role_m.group(1).strip() if role_m else ""

    all_candidate = [t for t in transcript if t.get("speaker") == "candidate"]
    total_specific, total_vague = 0, 0
    for t in all_candidate:
        s, v = _score_text(t["text"])
        total_specific += s
        total_vague += v

    # Bluff-collapse signal: vague density specifically on the hard
    # github_deepdive artifact-grounded questions, the ones a real answer
    # can't fake without actually knowing the code.
    gh_turns = _candidate_turns_for_node(transcript, "github_deepdive")
    gh_specific, gh_vague = 0, 0
    for t in gh_turns:
        s, v = _score_text(t["text"])
        gh_specific += s
        gh_vague += v
    bluff_collapse = len(gh_turns) > 0 and gh_vague > gh_specific

    base = 3.0 + 0.35 * total_specific - 0.55 * total_vague
    if bluff_collapse:
        base -= 1.5  # confident-but-empty on the artifact-grounded questions is the whole point of this persona
    silent_count = sum(1 for t in all_candidate if len(t["text"].split()) <= 3)
    base -= 0.8 * silent_count
    base = max(1.0, min(5.0, base))

    competencies = []
    for comp_name, node in COMPETENCY_NODE_MAP.items():
        node_turns = _candidate_turns_for_node(transcript, node)
        if node_turns:
            longest = max(node_turns, key=lambda t: len(t["text"]))
            quote = _first_words(longest["text"])
            s, v = _score_text(longest["text"])
            comp_score = 3.0 + 0.5 * s - 0.7 * v
            if node == "github_deepdive" and bluff_collapse:
                comp_score -= 1.5
        else:
            # no turn for this node (e.g. communication has no dedicated
            # node) — fall back to any candidate turn so evidence_quote is
            # still verbatim-verifiable, never fabricated.
            fallback = all_candidate[-1] if all_candidate else {"text": ""}
            quote = _first_words(fallback["text"]) if fallback["text"] else ""
            comp_score = base
        comp_score = max(1, min(5, round(comp_score)))
        confidence = 0.85 if quote else 0.3
        competencies.append({
            "name": comp_name,
            "score": comp_score,
            "confidence": confidence,
            "evidence_quote": quote,
            "reasoning": f"[mock] specific/vague markers on the {node} turn(s) scored this at {comp_score}.",
        })

    overall = round(sum(c["score"] for c in competencies) / len(competencies), 2) if competencies else base
    if overall >= 4.0:
        rec = "hire"
    elif overall <= 2.3:
        rec = "no_hire"
    else:
        rec = "borderline"

    return {
        "candidate_name": candidate_name,
        "role": role,
        "interview_date": "2026-08-13",
        "duration_seconds": 480,
        "competencies": competencies,
        "overall_score": overall,
        "recommendation": rec,
        "recommendation_reasoning": (
            f"[mock scorer] overall={overall}, bluff_collapse_detected={bluff_collapse}, "
            f"specific_markers={total_specific}, vague_markers={total_vague}, silent_turns={silent_count}."
        ),
        "strengths": [],
        "concerns": ["bluff_collapse_detected"] if bluff_collapse else [],
        "guardrail_flags": [],
        "github_grounded_questions_asked": len(gh_turns),
    }


def mock_response(system_prompt: str, user_prompt: str) -> dict:
    if "scoring agent" in system_prompt.lower():
        return _score_scorecard(user_prompt)

    if "classify a candidate" in system_prompt.lower():
        s, v = _score_text(user_prompt)
        if v > s and v >= 2:
            return {"classification": "shallow", "reasoning": "[mock] vague markers dominate"}
        if s >= 2:
            return {"classification": "strong", "reasoning": "[mock] specific markers present"}
        return {"classification": "shallow", "reasoning": "[mock] default"}

    if "follow-up question" in system_prompt.lower():
        return {"follow_up_text": "Can you be more specific — walk me through the exact detail you skipped?"}

    if "jd parsing agent" in system_prompt.lower():
        return {
            "role_title": "Role (mock-parsed)", "company": "", "location": "", "seniority": "junior",
            "must_have_skills": ["Python"], "nice_to_have_skills": [],
            "assessed_competencies": list(COMPETENCY_NODE_MAP.keys()),
        }

    if "resume parsing agent" in system_prompt.lower():
        return {"name": "Mock Candidate", "github_url": "https://github.com/mock", "email": "",
                "roles": [], "projects": [], "skills": [], "claims": []}

    if "compare a candidate" in system_prompt.lower():
        return {"skill_coverage": [], "claim_verification": [], "unsupported_claims_to_verify": []}

    if "question-planning agent" in system_prompt.lower():
        return {"questions": []}

    raise ValueError(f"mock_llm has no handler for this system_prompt (first 60 chars): {system_prompt[:60]!r}")
