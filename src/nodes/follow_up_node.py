"""
shallow answer -> follow_up (max 2, then move on)

Generates a deeper probe on the SAME question rather than moving to the
next one. The cap lives here, not in graph.py, so the "infinite loop = fail"
requirement has one obvious place to inspect/change during the viva
(sample live change: "change the follow-up cap from 2 to 1").
"""
from src.llm_client import llm_json_retry
from src.nodes.interview_common import ask_question_and_capture
from src.config import SETTINGS

PROBE_SYSTEM_PROMPT = """The candidate gave a shallow answer to an interview
question. Write ONE follow-up question that pushes for a specific detail
they didn't cover — a number, a trade-off, a concrete example, or (if the
question was GitHub-sourced) an actual line from their code. Keep it short,
conversational, one sentence.

Return JSON: {"follow_up_text": ""}
"""


def follow_up_node(state: dict) -> dict:
    question = state["current_question"]
    qid = question["id"]
    counts = dict(state.get("followup_counts", {}))
    used = counts.get(qid, 0)

    if used >= SETTINGS.max_follow_up_probes:
        # cap hit -> move on, this is the "max 2, then move on" requirement
        return {"current_node": "follow_up", "next_node_override": "_advance_from_current"}

    probe = llm_json_retry(
        PROBE_SYSTEM_PROMPT,
        f"QUESTION: {question['text']}\nANSWER: {state['last_candidate_answer']}",
        max_tokens=200,
    )
    probe_question = {**question, "text": probe["follow_up_text"], "source_reference": question.get("source_reference", "")}
    result = ask_question_and_capture(state, probe_question, "follow_up")

    counts[qid] = used + 1
    result["followup_counts"] = counts
    return result
