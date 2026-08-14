"""jd_fit -> asks JD-sourced questions."""
from src.nodes.interview_common import ask_question_and_capture, next_question_for_source


def jd_fit_node(state: dict) -> dict:
    q = next_question_for_source(state, "jd")
    if q is None:
        return {"current_node": "jd_fit", "next_node_override": "github_deepdive"}
    return ask_question_and_capture(state, q, "jd_fit")
