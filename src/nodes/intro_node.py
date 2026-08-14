"""intro -> greets candidate by name, discloses AI status."""
import time
from src.nodes.interview_common import ask_question_and_capture

DISCLOSURE_TEMPLATE = (
    "Hi {name}, thanks for joining. Before we start — I want to be upfront "
    "that I'm an AI interviewer, not a human recruiter. I'll be asking you "
    "about your background and your work on GitHub for the {role} role. "
    "Feel free to jump in any time, I'll stop talking if you do. Ready to start?"
)


def intro_node(state: dict) -> dict:
    # First Phase-2 node — this is the clock's t=0 for the 8-minute floor
    # and the "time spent -> jump to wrap_up" edge.
    start_ms = state.get("interview_start_ms") or int(time.time() * 1000)
    greeting_q = {
        "id": "intro",
        "text": DISCLOSURE_TEMPLATE.format(
            name=state.get("candidate_name", "there"),
            role=state.get("role_title", "this role"),
        ),
        "competency": "n/a",
        "source": "n/a",
        "source_reference": "",
        "difficulty": "n/a",
        "follow_up_triggers": [],
    }
    result = ask_question_and_capture({**state, "interview_start_ms": start_ms}, greeting_q, "intro")
    result["current_question_index"] = 0
    result["interview_start_ms"] = start_ms
    result["call_elapsed_ms"] = 0  # don't let the intro's own duration eat into the 8-min floor
    return result
