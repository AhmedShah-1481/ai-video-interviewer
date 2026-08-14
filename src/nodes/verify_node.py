"""
bluff detected -> verify ("walk me through that commit")

Distinct from follow_up: follow_up deepens a shallow answer on the same
topic; verify specifically re-anchors to a concrete GitHub artifact when
the classifier suspects the candidate is being fluent-but-empty. This is
the node that's supposed to catch persona #4 (Bluffer) in evals/.
"""
from src.nodes.interview_common import ask_question_and_capture


def verify_node(state: dict) -> dict:
    question = state["current_question"]
    ref = question.get("source_reference", "")
    if ref:
        verify_text = f"Let's get specific — walk me through {ref} line by line. What does it actually do?"
    else:
        verify_text = "Can you give me a concrete, specific example instead of the general approach?"

    verify_question = {**question, "id": question["id"] + "_verify", "text": verify_text}
    result = ask_question_and_capture(state, verify_question, "verify")
    result["next_node_override"] = "_advance_from_current"  # verify never loops further, one shot
    return result
