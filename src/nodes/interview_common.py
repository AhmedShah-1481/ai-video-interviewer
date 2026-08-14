"""
Shared by every Phase 2 node (intro, resume_probe, jd_fit, github_deepdive,
scenario, candidate_qs). Each phase node is a thin selector over this —
duplicating this logic across 6 files would mean 6 places to fix a barge-in
bug instead of 1.
"""
import time
from src.realtime.turn_manager import speak_and_listen
from src.nodes.answer_classifier import classify_answer
from src.guardrails.banned_questions import check_question


def ask_question_and_capture(state: dict, question: dict, node_name: str) -> dict:
    """
    Speaks `question`, listens for the candidate's answer (with barge-in
    handling inside turn_manager), classifies the answer, appends both
    turns to the transcript, and returns the partial state update.
    Does NOT decide routing — that's graph.py's job via conditional edges,
    this just produces the classification they route on.
    """
    guard = check_question(question["text"])
    if guard["blocked"]:
        # Real-time safety net: even though the plan was filtered pre-call,
        # a dynamically edited/regenerated question gets checked again
        # right before it's spoken — this is the "before reaching the
        # candidate" enforcement point for anything not caught upstream.
        return {
            "last_answer_quality": "",
            "guardrail_flags": state.get("guardrail_flags", []) + [{
                "action": "blocked_at_speak_time",
                "category": guard["category"],
                "text": question["text"],
            }],
            "current_node": node_name,
            "next_node_override": "recovery",
        }

    agent_turn_start = int(time.time() * 1000)
    speak_result = speak_and_listen(question["text"], node_name=node_name)
    # speak_result: {"answer_text": "", "was_interrupted": bool,
    #                "agent_text_spoken": "" (may be truncated by barge-in)}

    transcript = list(state.get("transcript", []))
    transcript.append({
        "speaker": "agent",
        "text": speak_result["agent_text_spoken"],
        "timestamp_ms": agent_turn_start,
        "node": node_name,
        "interrupted": speak_result["was_interrupted"],
    })
    candidate_turn_start = int(time.time() * 1000)
    transcript.append({
        "speaker": "candidate",
        "text": speak_result["answer_text"],
        "timestamp_ms": candidate_turn_start,
        "node": node_name,
        "interrupted": False,
    })

    classification = classify_answer(question, speak_result["answer_text"])

    # "time spent -> jump to wrap_up" needs call_elapsed_ms actually populated
    # somewhere, or that edge in route_after_turn is dead code. This is the
    # one place every phase node passes through, so it's computed here once
    # rather than duplicated per-node.
    start = state.get("interview_start_ms") or agent_turn_start
    elapsed = candidate_turn_start - start

    return {
        "transcript": transcript,
        "current_question": question,
        "last_candidate_answer": speak_result["answer_text"],
        "last_answer_quality": classification["classification"],
        "current_node": node_name,
        "barge_in_flag": speak_result["was_interrupted"],
        "call_elapsed_ms": elapsed,
    }


def next_question_for_source(state: dict, source: str) -> dict | None:
    """Pulls the next not-yet-asked question matching a given source tag."""
    plan = state["question_plan"]["questions"]
    idx = state.get("current_question_index", 0)
    asked_ids = {t["text"] for t in state.get("transcript", []) if t["speaker"] == "agent"}
    for q in plan[idx:]:
        if q["source"] == source and q["text"] not in asked_ids:
            return q
    return None


def time_budget_exceeded(state: dict, max_ms: int = 8 * 60 * 1000) -> bool:
    """time spent -> jump to wrap_up. Default 8 min floor per requirement #1."""
    return state.get("call_elapsed_ms", 0) >= max_ms
