"""github_deepdive -> asks the >=3 GitHub-grounded questions. Highest-value
node for requirement #4 — this is where 'walk me through that commit'
style questions actually get spoken."""
from src.nodes.interview_common import ask_question_and_capture, next_question_for_source


def github_deepdive_node(state: dict) -> dict:
    q = next_question_for_source(state, "github")
    if q is None:
        return {"current_node": "github_deepdive", "next_node_override": "scenario"}
    return ask_question_and_capture(state, q, "github_deepdive")
