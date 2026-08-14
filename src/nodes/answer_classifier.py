"""
Not a graph node itself — a helper called BY the interview nodes right after
capturing a candidate answer. Its output ("shallow" | "strong" | "silent" |
"off_topic" | "bluff_suspected") is what the conditional edges in graph.py
branch on. Kept separate from graph.py so the routing logic (graph.py) stays
readable and this classification logic can be unit-tested/eval'd on its own.
"""
from src.llm_client import llm_json_retry

SYSTEM_PROMPT = """You classify a candidate's interview answer. Given the
question asked (with its source_reference, if GitHub-based) and the
candidate's answer, classify it as exactly one of:

- "silent": no meaningful answer, candidate said nothing or "I don't know"
  with zero attempt
- "off_topic": answer doesn't address the question at all
- "shallow": on-topic but generic/surface-level, no specifics, no reasoning
- "strong": specific, includes reasoning or trade-offs, demonstrates real
  understanding
- "bluff_suspected": fluent and confident but vague on specifics when the
  question asked for something concrete (e.g. asked to explain a specific
  commit/file and the answer describes generically without engaging the
  actual referenced artifact)

Return JSON: {"classification": "", "reasoning": ""}
"""


def classify_answer(question: dict, answer_text: str) -> dict:
    if not answer_text or not answer_text.strip():
        return {"classification": "silent", "reasoning": "empty answer"}

    user_prompt = (
        f"QUESTION: {question.get('text')}\n"
        f"SOURCE: {question.get('source')} (reference: {question.get('source_reference')})\n"
        f"CANDIDATE ANSWER: {answer_text}"
    )
    return llm_json_retry(SYSTEM_PROMPT, user_prompt, max_tokens=300)
