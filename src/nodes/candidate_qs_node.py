"""candidate_Qs -> flips it: candidate can ask the agent questions about
the (fictional) role. Not scored — just good interview practice and gives
the candidate a natural close before wrap_up."""
from src.realtime.turn_manager import speak_and_listen


def candidate_qs_node(state: dict) -> dict:
    prompt_text = "That's everything I had. Do you have any questions for me about the role or team?"
    speak_result = speak_and_listen(prompt_text, node_name="candidate_qs")

    transcript = list(state.get("transcript", []))
    transcript.append({"speaker": "agent", "text": prompt_text, "timestamp_ms": 0,
                        "node": "candidate_qs", "interrupted": speak_result["was_interrupted"]})
    transcript.append({"speaker": "candidate", "text": speak_result["answer_text"], "timestamp_ms": 0,
                        "node": "candidate_qs", "interrupted": False})
    return {"transcript": transcript, "current_node": "candidate_qs"}
