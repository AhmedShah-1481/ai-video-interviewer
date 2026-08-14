"""
Guardrail (a): banned questions blocked before reaching the candidate.
Categories: age, gender, marital, religion, nationality, health/pregnancy,
salary history, politics.

Two layers on purpose:
1. Keyword/pattern layer here — fast, deterministic, zero-cost, catches the
   obvious cases and can't be "talked out of" by a clever prompt.
2. question_planner's prompt also instructs the LLM not to generate these —
   but instructions alone are not a guardrail, they're a suggestion. This
   file is what actually blocks it before a banned question ever reaches
   the candidate, which is what requirement #9 asks for.
"""
import re

BANNED_PATTERNS = {
    "age": [r"\bhow old are you\b", r"\byour age\b", r"\bwhat year were you born\b", r"\bdate of birth\b"],
    "gender": [r"\bwhat.{0,15}gender\b", r"\bare you (a )?(man|woman|male|female)\b"],
    "marital": [r"\bmarried\b", r"\bmarital status\b", r"\bare you single\b",
                r"\b(do you have|planning to have|have) (a |any )?(kids|children)\b"],
    "religion": [r"\breligio", r"\bwhat.{0,10}faith\b", r"\bdo you (pray|fast|observe)\b"],
    "nationality": [r"\bwhat.{0,10}nationality\b", r"\bwhere are you (originally )?from\b", r"\bimmigration status\b", r"\bvisa status\b"],
    "health": [r"\bhealth conditions?\b", r"\bdisabilit", r"\bpregnan", r"\bmedical (condition|history)s?\b"],
    "salary_history": [r"\bcurrent salary\b", r"\bhow much (do|did) you (make|earn)\b", r"\bsalary history\b", r"\bprevious (compensation|pay)\b"],
    "politics": [r"\bpolitical (party|view|affiliation)\b", r"\bwho did you vote\b", r"\byour politics\b"],
}

_COMPILED = {
    category: [re.compile(p, re.IGNORECASE) for p in patterns]
    for category, patterns in BANNED_PATTERNS.items()
}


def check_question(text: str) -> dict:
    """
    Returns {"blocked": bool, "category": str|None, "matched_pattern": str|None}
    Call this on every question BEFORE it's spoken to the candidate — both
    the pre-generated question_plan (batch check) and any dynamically
    generated follow-up/probe question (real-time check).
    """
    for category, patterns in _COMPILED.items():
        for pattern in patterns:
            if pattern.search(text):
                return {"blocked": True, "category": category, "matched_pattern": pattern.pattern}
    return {"blocked": False, "category": None, "matched_pattern": None}


def filter_question_plan(question_plan: dict) -> dict:
    """
    Batch-checks every question in a plan. Blocked questions are removed
    and logged in guardrail_flags rather than silently dropped, so the
    HITL reviewer (and later the grader) can see what was filtered and why.
    """
    kept, flags = [], []
    for q in question_plan.get("questions", []):
        result = check_question(q.get("text", ""))
        if result["blocked"]:
            flags.append({
                "question_id": q.get("id"),
                "text": q.get("text"),
                "category": result["category"],
                "action": "blocked_pre_generation",
            })
        else:
            kept.append(q)
    question_plan["questions"] = kept
    question_plan["guardrail_flags"] = question_plan.get("guardrail_flags", []) + flags
    return question_plan
