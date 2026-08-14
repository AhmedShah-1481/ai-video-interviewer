"""wrap_up -> closes the call, thanks candidate, sets up handoff to scoring."""
from src.realtime.turn_manager import speak_and_listen


def wrap_up_node(state: dict) -> dict:
    closing = (
        f"Thanks so much for your time, {state.get('candidate_name', 'there')} — "
        "this was really helpful. We'll be in touch with next steps soon. Have a great day!"
    )
    speak_result = speak_and_listen(closing, node_name="wrap_up", expect_answer=False)
    transcript = list(state.get("transcript", []))
    transcript.append({"speaker": "agent", "text": closing, "timestamp_ms": 0,
                        "node": "wrap_up", "interrupted": speak_result["was_interrupted"]})
    return {"transcript": transcript, "current_node": "wrap_up"}
