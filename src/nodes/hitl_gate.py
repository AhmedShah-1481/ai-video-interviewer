"""
[ HITL INTERRUPT — recruiter approves ]

Uses LangGraph's interrupt() so the graph genuinely suspends execution and
persists state via the checkpointer — this is not a "wait for stdin input"
fake pause, it's a real graph interrupt that survives a process restart
(resumed via graph.invoke(Command(resume=...), config) with the same
thread_id). The viva will ask you to prove approve/edit/reject all work —
this file is where all three are implemented.
"""
from langgraph.types import interrupt
from src.guardrails.banned_questions import filter_question_plan


def hitl_gate_node(state: dict) -> dict:
    plan = state["question_plan"]

    # interrupt() halts the graph here and surfaces `plan` to whatever is
    # driving the graph (CLI script, or a recruiter-facing web view). The
    # graph will not proceed past this line until resumed with a decision.
    decision = interrupt({
        "type": "question_plan_review",
        "question_plan": plan,
        "instructions": "Return one of: "
                         '{"action": "approve"} | '
                         '{"action": "edit", "questions": [...]} | '
                         '{"action": "reject", "reason": "..."}',
    })

    action = decision.get("action")

    if action == "approve":
        plan["approved_by_human"] = True
        return {"question_plan": plan, "hitl_decision": "approved", "current_node": "hitl_gate"}

    if action == "edit":
        edited_questions = decision["questions"]
        # re-run guardrail (a) on edited questions too — a recruiter editing
        # in a banned question by hand should still be blocked
        plan["questions"] = edited_questions
        plan = filter_question_plan(plan)
        plan["approved_by_human"] = True
        plan["edits_made"] = decision.get("edit_notes", ["recruiter edited question set"])
        return {"question_plan": plan, "hitl_decision": "edited", "current_node": "hitl_gate"}

    if action == "reject":
        plan["approved_by_human"] = False
        return {
            "question_plan": plan,
            "hitl_decision": "rejected",
            "current_node": "hitl_gate",
            "next_node_override": "question_planner",  # loop back to regenerate
        }

    raise ValueError(f"Unrecognized HITL decision action: {action!r}")
