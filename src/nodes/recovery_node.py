"""
silence/off-topic -> recovery

Handles both true silence (15s of dead air) and off-topic answers with a
gentle re-ask rather than penalizing the candidate immediately — a nervous
candidate restarting mid-sentence should not be scored down for a recoverable
stumble (this is the fairness case the Nervous persona tests in evals/).
"""
from src.nodes.interview_common import ask_question_and_capture


def recovery_node(state: dict) -> dict:
    question = state["current_question"]
    quality = state.get("last_answer_quality")

    if quality == "silent":
        recovery_text = "Take your time — no rush. Want me to repeat the question, or rephrase it?"
    else:  # off_topic
        recovery_text = f"Let's come back to this — {question['text']}"

    recovery_question = {**question, "id": question["id"] + "_recovery", "text": recovery_text}
    result = ask_question_and_capture(state, recovery_question, "recovery")
    result["next_node_override"] = "_advance_from_current"
    return result
