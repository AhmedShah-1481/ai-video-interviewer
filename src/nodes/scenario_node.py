"""scenario -> asks scenario-sourced questions (hypotheticals, debugging walk-throughs)."""
from src.nodes.interview_common import ask_question_and_capture, next_question_for_source


def scenario_node(state: dict) -> dict:
    q = next_question_for_source(state, "scenario")
    if q is None:
        return {"current_node": "scenario", "next_node_override": "candidate_qs"}
    return ask_question_and_capture(state, q, "scenario")
