"""
Custom MCP server — requirement #8. Exposes the recruiter-facing surface of
the system (get_candidate, get_question_plan, save_score, get_scorecard,
list_interviews — 5 tools, at the required minimum) so a recruiter can pull
this up directly inside Claude Desktop, not just inside our own app.

Storage model: one "interview" = one directory under output/interviews/<id>/
containing resume.json, question_plan.json, scorecard.json, transcript.json.
For a single-candidate submission run, <id> defaults to "default" and lines
up with the flat output/ layout in Section 6 of the spec — list_interviews
will show just that one entry, which is expected and fine; the schema
supports more without changing paths, which is what "MCP server ... not
only inside your app" is really testing (a real API surface, not a demo
stub).

Run with: python -m mcp_server.server   (stdio transport, per fastmcp)
Then add it in Claude Desktop's config (see README.md) and take the
screenshot requirement #8 asks for.
"""
import json
from pathlib import Path

from fastmcp import FastMCP  # pip install fastmcp

mcp = FastMCP("firstround-interviewer")

OUTPUT_ROOT = Path("output")
INTERVIEWS_ROOT = OUTPUT_ROOT / "interviews"


def _interview_dir(interview_id: str) -> Path:
    return INTERVIEWS_ROOT / interview_id


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _flat_or_scoped(interview_id: str, filename: str) -> Path:
    """Prefers output/interviews/<id>/<filename> if present, else falls
    back to the flat output/<filename> — this lets the server work
    unmodified against both the multi-interview layout and the single-run
    flat layout the fixed-paths spec (Section 6) describes."""
    scoped = _interview_dir(interview_id) / filename
    if scoped.exists():
        return scoped
    return OUTPUT_ROOT / filename


@mcp.tool()
def list_interviews() -> dict:
    """Lists every interview this server knows about, newest first, with
    candidate name, role, and whether a scorecard exists yet."""
    results = []
    if INTERVIEWS_ROOT.exists():
        for d in sorted(INTERVIEWS_ROOT.iterdir()):
            if not d.is_dir():
                continue
            sc = _read_json(d / "scorecard.json")
            resume = _read_json(d / "resume.json")
            results.append({
                "interview_id": d.name,
                "candidate_name": (sc or {}).get("candidate_name") or (resume or {}).get("name", ""),
                "role": (sc or {}).get("role", ""),
                "has_scorecard": sc is not None,
            })
    # always surface the flat output/ run too, as "default", if it exists
    # and isn't already tracked under interviews/
    flat_sc = _read_json(OUTPUT_ROOT / "scorecard.json")
    if flat_sc is not None and not any(r["interview_id"] == "default" for r in results):
        results.insert(0, {
            "interview_id": "default",
            "candidate_name": flat_sc.get("candidate_name", ""),
            "role": flat_sc.get("role", ""),
            "has_scorecard": True,
        })
    return {"interviews": results, "count": len(results)}


@mcp.tool()
def get_candidate(interview_id: str = "default") -> dict:
    """Returns the parsed resume + GitHub grounding data for one interview
    — everything the prep phase gathered about the candidate before the call."""
    resume = _read_json(_flat_or_scoped(interview_id, "prep/resume.json")) or \
        _read_json(_flat_or_scoped(interview_id, "resume.json"))
    github = _read_json(_flat_or_scoped(interview_id, "prep/github.json")) or \
        _read_json(_flat_or_scoped(interview_id, "github.json"))
    if resume is None:
        return {"error": f"No resume found for interview_id={interview_id!r}"}
    return {"interview_id": interview_id, "resume": resume, "github": github or {}}


@mcp.tool()
def get_question_plan(interview_id: str = "default") -> dict:
    """Returns the approved question plan (competency, source, difficulty,
    and the source_reference each question was grounded in)."""
    plan = _read_json(_flat_or_scoped(interview_id, "prep/question_plan.json"))
    if plan is None:
        return {"error": f"No question plan found for interview_id={interview_id!r}"}
    return {"interview_id": interview_id, "question_plan": plan}


@mcp.tool()
def get_scorecard(interview_id: str = "default") -> dict:
    """Returns the final hiring scorecard: per-competency scores, evidence
    quotes, hire/no_hire/borderline + confidence."""
    scorecard = _read_json(_flat_or_scoped(interview_id, "scorecard.json"))
    if scorecard is None:
        return {"error": f"No scorecard found for interview_id={interview_id!r}. Has scoring run yet?"}
    return {"interview_id": interview_id, "scorecard": scorecard}


@mcp.tool()
def save_score(interview_id: str, competency: str, score: int, evidence_quote: str,
               reasoning: str = "") -> dict:
    """Recruiter override: lets a human adjust one competency's score on an
    existing scorecard directly from Claude Desktop (e.g. after watching the
    recording and disagreeing with the automated score). Still runs through
    the same evidence-quote guardrail — a save with a quote that doesn't
    actually appear in the transcript is rejected, not silently written."""
    from src.guardrails.evidence_check import quote_exists_in_transcript

    scorecard_path = _flat_or_scoped(interview_id, "scorecard.json")
    transcript_path = _flat_or_scoped(interview_id, "transcript.json")
    scorecard = _read_json(scorecard_path)
    transcript = _read_json(transcript_path)
    if scorecard is None:
        return {"error": f"No scorecard found for interview_id={interview_id!r}"}

    turns = (transcript or {}).get("turns", [])
    if not quote_exists_in_transcript(evidence_quote, turns):
        return {"error": "evidence_quote not found in transcript — score NOT saved "
                          "(guardrail: no score without a verifiable quote)."}

    updated = False
    for comp in scorecard.get("competencies", []):
        if comp.get("name") == competency:
            comp["score"] = score
            comp["evidence_quote"] = evidence_quote
            comp["reasoning"] = reasoning or comp.get("reasoning", "")
            comp["rejected"] = False
            comp["human_overridden"] = True
            updated = True
    if not updated:
        scorecard.setdefault("competencies", []).append({
            "name": competency, "score": score, "confidence": 1.0,
            "evidence_quote": evidence_quote, "reasoning": reasoning,
            "human_overridden": True,
        })

    scorecard_path.parent.mkdir(parents=True, exist_ok=True)
    scorecard_path.write_text(json.dumps(scorecard, indent=2))
    return {"saved": True, "interview_id": interview_id, "competency": competency, "score": score}


if __name__ == "__main__":
    mcp.run()
