"""resume_probe -> asks resume-sourced questions."""
from src.nodes.interview_common import ask_question_and_capture, next_question_for_source


def resume_probe_node(state: dict) -> dict:
    q = next_question_for_source(state, "resume")
    if q is None:
        return {"current_node": "resume_probe", "next_node_override": "jd_fit"}
    return ask_question_and_capture(state, q, "resume_probe")
