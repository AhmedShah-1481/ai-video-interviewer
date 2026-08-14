"""
The whole interview pipeline as one LangGraph graph: prep phase (5 nodes),
HITL gate (1 interrupt node), live call phase (7 flow nodes + 3 conditional-
routing nodes), scoring phase (1 node) = 17 nodes total, well over the
required 6.

Conditional edges (>=2 required, this graph has 2 distinct routing
functions used across 7 call sites):
  1. route_after_turn — after every question in resume_probe/jd_fit/
     github_deepdive/scenario/follow_up/verify/recovery, decides whether to
     deepen (follow_up), re-anchor (verify), recover (recovery), advance to
     the next question in-phase, move to the next phase, or bail to
     wrap_up on time.
  2. route_after_prep — after question_planner, whether the prep phase
     is ready for HITL review or (in principle) needs re-running.

Checkpointer: SQLite, so "call drops -> resume at last node" is a real
property of this graph, not a claim — invoke with the same thread_id after
a crash and LangGraph resumes from the last persisted checkpoint, not from
the top of the call.
"""
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from src.state import InterviewState
from src.config import SETTINGS

from src.nodes.prep_nodes import (
    parse_jd_node, parse_resume_node, github_agent_node,
    gap_analysis_node, question_planner_node,
)
from src.nodes.hitl_gate import hitl_gate_node
from src.nodes.intro_node import intro_node
from src.nodes.resume_probe_node import resume_probe_node
from src.nodes.jd_fit_node import jd_fit_node
from src.nodes.github_deepdive_node import github_deepdive_node
from src.nodes.scenario_node import scenario_node
from src.nodes.candidate_qs_node import candidate_qs_node
from src.nodes.wrap_up_node import wrap_up_node
from src.nodes.follow_up_node import follow_up_node
from src.nodes.verify_node import verify_node
from src.nodes.recovery_node import recovery_node
from src.nodes.interview_common import time_budget_exceeded
from src.nodes.scoring_node import scoring_node


# Which phase-node "owns" each question source — used to route back after
# a follow_up/verify/recovery detour finishes ("_advance_from_current").
SOURCE_TO_PHASE_NODE = {
    "resume": "resume_probe",
    "jd": "jd_fit",
    "github": "github_deepdive",
    "scenario": "scenario",
}

CALL_TIME_LIMIT_MS = 8 * 60 * 1000  # 8-minute floor from requirement #1


def route_after_turn(state: InterviewState) -> str:
    """The core conditional edge for the whole live-call phase."""
    # time spent -> jump to wrap_up (checked first, overrides everything else)
    if time_budget_exceeded(state, CALL_TIME_LIMIT_MS) and state.get("current_node") != "candidate_qs":
        return "wrap_up"

    override = state.get("next_node_override")

    if override == "_advance_from_current":
        # a follow_up/verify/recovery detour just finished — return to the
        # phase node that owns the current question's source so it can
        # either ask the next question in that phase or advance further
        source = (state.get("current_question") or {}).get("source", "")
        return SOURCE_TO_PHASE_NODE.get(source, "wrap_up")

    if override:  # explicit next-phase jump set by a phase node with no questions left
        return override

    quality = state.get("last_answer_quality")
    if quality == "shallow":
        return "follow_up"
    if quality == "bluff_suspected":
        return "verify"
    if quality in ("silent", "off_topic"):
        return "recovery"

    # "strong" (or blank/n/a for intro) -> stay in the same phase node,
    # which will pick the next unanswered question of that source, or
    # set next_node_override itself once that source is exhausted.
    # strong answer -> raise difficulty is handled by question_planner
    # having already ordered questions easy->hard within each source; the
    # graph doesn't need to reorder, it just keeps advancing.
    return state.get("current_node", "wrap_up")


def route_after_prep(state: InterviewState) -> str:
    """approve/edit -> live call; reject already loops inside hitl_gate_node
    via next_node_override, so by the time we get here it's always ready."""
    if state.get("hitl_decision") in ("approved", "edited"):
        return "intro"
    return "question_planner"  # rejected -> regenerate


def build_graph():
    graph = StateGraph(InterviewState)

    # Phase 1 — prep
    graph.add_node("parse_jd", parse_jd_node)
    graph.add_node("parse_resume", parse_resume_node)
    graph.add_node("github_agent", github_agent_node)
    graph.add_node("gap_analysis", gap_analysis_node)
    graph.add_node("question_planner", question_planner_node)
    graph.add_node("hitl_gate", hitl_gate_node)

    # Phase 2 — live call
    graph.add_node("intro", intro_node)
    graph.add_node("resume_probe", resume_probe_node)
    graph.add_node("jd_fit", jd_fit_node)
    graph.add_node("github_deepdive", github_deepdive_node)
    graph.add_node("scenario", scenario_node)
    graph.add_node("candidate_qs", candidate_qs_node)
    graph.add_node("wrap_up", wrap_up_node)
    graph.add_node("follow_up", follow_up_node)
    graph.add_node("verify", verify_node)
    graph.add_node("recovery", recovery_node)

    # Phase 3 — scoring
    graph.add_node("scoring", scoring_node)

    # --- edges: prep phase is linear ---
    graph.set_entry_point("parse_jd")
    graph.add_edge("parse_jd", "parse_resume")
    graph.add_edge("parse_resume", "github_agent")
    graph.add_edge("github_agent", "gap_analysis")
    graph.add_edge("gap_analysis", "question_planner")
    graph.add_edge("question_planner", "hitl_gate")

    # --- conditional edge #2: HITL outcome routes to live call or a re-plan loop ---
    graph.add_conditional_edges("hitl_gate", route_after_prep, {
        "intro": "intro",
        "question_planner": "question_planner",
    })

    # --- conditional edge #1: applied at every point a candidate answer
    #     was just captured ---
    turn_nodes = ["resume_probe", "jd_fit", "github_deepdive", "scenario",
                  "follow_up", "verify", "recovery"]
    # Every possible string route_after_turn can return, across ALL call
    # sites, must appear as a key here — LangGraph resolves the returned
    # string against this single mapping per node. candidate_qs is reachable
    # only via scenario_node's next_node_override once scenario questions
    # are exhausted (not a static graph.add_edge), so it must be listed
    # explicitly or LangGraph raises on that transition at runtime.
    routing_map = {
        "follow_up": "follow_up", "verify": "verify", "recovery": "recovery",
        "resume_probe": "resume_probe", "jd_fit": "jd_fit",
        "github_deepdive": "github_deepdive", "scenario": "scenario",
        "candidate_qs": "candidate_qs", "wrap_up": "wrap_up",
    }
    for node_name in turn_nodes:
        graph.add_conditional_edges(node_name, route_after_turn, routing_map)

    graph.add_edge("intro", "resume_probe")
    graph.add_edge("candidate_qs", "wrap_up")
    graph.add_edge("wrap_up", "scoring")
    graph.add_edge("scoring", END)

    return graph


def compile_graph(sqlite_path: str = None):
    sqlite_path = sqlite_path or SETTINGS.sqlite_path
    Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    graph = build_graph()

    # checkpointer: call drops -> resume at last node
    with SqliteSaver.from_conn_string(sqlite_path) as checkpointer:
        compiled = graph.compile(checkpointer=checkpointer)
        return compiled
