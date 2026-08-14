"""
Nodes 1-5 of Phase 1 (prep). Each is a thin wrapper: graph-level node
functions take/return InterviewState; the actual work lives in src/agents/
so it's independently testable and reusable outside the graph (the MCP
server also imports these agents directly, not through the graph).
"""
from src.agents.jd_parser import parse_jd
from src.agents.resume_parser import parse_resume, extract_pdf_text
from src.agents.github_agent import fetch_github_profile
from src.agents.gap_analysis import analyze_gaps
from src.agents.question_planner import plan_questions
from src.guardrails.banned_questions import filter_question_plan
from src.config import SETTINGS


def parse_jd_node(state: dict) -> dict:
    jd_text = state["_jd_text_raw"]
    jd = parse_jd(jd_text)
    out = {"jd": jd, "current_node": "parse_jd"}
    # Backfill role_title from the parsed JD if the CLI didn't set one
    # explicitly (--role). CLI value always wins if present.
    if not state.get("role_title") and jd.get("role_title"):
        out["role_title"] = jd["role_title"]
    return out


def parse_resume_node(state: dict) -> dict:
    text = extract_pdf_text(state["_resume_pdf_path"])
    resume = parse_resume(text)
    out = {"resume": resume, "current_node": "parse_resume"}
    # Same backfill for candidate_name from the parsed resume
    # (--candidate-name on the CLI always wins if present).
    if not state.get("candidate_name") and resume.get("name"):
        out["candidate_name"] = resume["name"]
    return out


def github_agent_node(state: dict) -> dict:
    github_url = state["resume"].get("github_url", "")
    if not github_url:
        data = {"username": "", "repos": [], "error": "no github url in resume"}
    else:
        data = fetch_github_profile(github_url, token=SETTINGS.github_token)
    return {"github_data": data, "current_node": "github_agent"}


def gap_analysis_node(state: dict) -> dict:
    result = analyze_gaps(state["jd"], state["resume"], state["github_data"])
    return {"gap_analysis": result, "current_node": "gap_analysis"}


def question_planner_node(state: dict) -> dict:
    plan = plan_questions(state["jd"], state["resume"], state["github_data"], state["gap_analysis"])
    # guardrail (a) runs BEFORE the plan ever reaches HITL review or the candidate
    plan = filter_question_plan(plan)
    return {"question_plan": plan, "current_node": "question_planner"}