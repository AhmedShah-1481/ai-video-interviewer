"""FirstRound CLI entry point.

Wires the existing project together:
    prep -> real LangGraph HITL interrupt -> interview -> scoring -> outputs.

Examples:
    python -m src.main --resume inputs/resume.pdf --jd inputs/jd.txt --mode console
    python -m src.main --resume inputs/resume.pdf --jd inputs/jd.txt --mode livekit
    python -m src.main --resume inputs/resume.pdf --jd inputs/jd.txt --mode daily

The console mode is a development/test double. The graded live interview must
use REALTIME_MODE=livekit (recommended stack, with AVATAR_PROVIDER=simli) or
the legacy REALTIME_MODE=daily, and a real consented candidate/recording.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
PREP_OUTPUT = OUTPUT / "prep"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _interrupts(result) -> list:
    """Normalise LangGraph's interrupt payload across recent versions."""
    if isinstance(result, dict) and result.get("__interrupt__"):
        value = result["__interrupt__"]
        return list(value) if isinstance(value, (tuple, list)) else [value]
    return []


def _prompt_hitl(payload: dict) -> dict:
    print("\n" + "=" * 72)
    print("HUMAN-IN-THE-LOOP: QUESTION PLAN REVIEW")
    print("=" * 72)
    questions = payload.get("question_plan", {}).get("questions", [])
    for i, q in enumerate(questions, 1):
        print(f"{i:02d}. [{q.get('source')}/{q.get('difficulty')}] {q.get('text')}")

    while True:
        action = input("\nApprove [a], edit [e], reject/regenerate [r]: ").strip().lower()
        if action in {"a", "approve"}:
            return {"action": "approve"}
        if action in {"r", "reject"}:
            reason = input("Reason (optional): ").strip()
            return {"action": "reject", "reason": reason or "Recruiter requested regeneration."}
        if action in {"e", "edit"}:
            raw = input(
                "Path to JSON file containing replacement question list "
                "(or press Enter to edit one question inline): "
            ).strip()
            if raw:
                path = Path(raw)
                if not path.is_absolute():
                    path = Path.cwd() / path
                try:
                    obj = json.loads(path.read_text(encoding="utf-8"))
                    edited = obj.get("questions", obj) if isinstance(obj, dict) else obj
                    if not isinstance(edited, list):
                        raise ValueError("JSON must be a list or {\"questions\": [...]}.")
                    return {"action": "edit", "questions": edited, "edit_notes": [f"Loaded edits from {path}"]}
                except Exception as exc:
                    print(f"Could not load edits: {exc}")
                    continue
            try:
                idx = int(input("Question number to replace (1-based): ")) - 1
                if idx < 0 or idx >= len(questions):
                    raise ValueError("question number out of range")
                new_text = input("New question text: ").strip()
                if not new_text:
                    raise ValueError("question text cannot be empty")
                edited = [dict(q) for q in questions]
                edited[idx]["text"] = new_text
                return {"action": "edit", "questions": edited,
                        "edit_notes": [f"Recruiter replaced question {idx + 1}"]}
            except ValueError as exc:
                print(f"Invalid edit: {exc}")
                continue
        print("Please choose a, e, or r.")


def _save_prep(state: dict) -> None:
    mapping = {
        "jd": state.get("jd", {}),
        "resume": state.get("resume", {}),
        "github": state.get("github_data", {}),
        "gap_analysis": state.get("gap_analysis", {}),
        "question_plan": state.get("question_plan", {}),
    }
    for name, data in mapping.items():
        _write_json(PREP_OUTPUT / f"{name}.json", data)


def _save_final(state: dict) -> None:
    scorecard = state.get("scorecard")
    transcript = state.get("transcript", [])
    if scorecard is not None:
        _write_json(OUTPUT / "scorecard.json", scorecard)
        # This was previously missing: report.pdf was printed in the final
        # summary as if it existed, but nothing actually called
        # generate_report(). Requirement #10 / the spec's output/ paths
        # need a real PDF here, not just scorecard.json.
        try:
            from src.report_generator import generate_report
            generate_report(scorecard, output_path=str(OUTPUT / "report.pdf"))
        except Exception as exc:  # noqa: BLE001 — don't let report generation
            # crash a run that otherwise completed successfully; surface it
            # loudly instead so it's obvious in the terminal output.
            print(f"WARNING: report.pdf generation failed: {exc!r}", file=sys.stderr)
    _write_json(OUTPUT / "transcript.json", {"turns": transcript})


def _start_live_call(thread_id: str, settings):
    """Connect only after HITL approval, immediately before the intro node."""
    from src.realtime.transport import get_transport

    transport = get_transport()
    room_name = f"firstround-{thread_id}"
    join_info = transport.create_room(room_name)
    print(f"\nCall room ready: {join_info}")
    if settings.realtime_mode == "livekit":
        print(f"Candidate join token:\n{transport.candidate_join_token}\n")
        print(
            "Join with LIVEKIT_URL and the candidate token in a LiveKit-compatible "
            "client. Waiting for the candidate before starting the interview..."
        )
    if hasattr(transport, "wait_for_candidate"):
        transport.wait_for_candidate()
        print("Candidate joined. Starting the interview.\n")
    return transport


def run(args: argparse.Namespace) -> int:
    jd_path = Path(args.jd).expanduser().resolve()
    resume_path = Path(args.resume).expanduser().resolve()
    if not jd_path.exists():
        print(f"JD not found: {jd_path}", file=sys.stderr)
        return 2
    if not resume_path.exists():
        print(f"Resume not found: {resume_path}", file=sys.stderr)
        return 2

    # Set mode before importing/using the graph nodes that read SETTINGS.
    os.environ["REALTIME_MODE"] = args.mode
    if args.llm_provider:
        os.environ["LLM_PROVIDER"] = args.llm_provider

    # Import config and graph only after CLI overrides are in the environment.
    # Several graph modules import SETTINGS by value at module load time.
    from src.config import SETTINGS as settings
    from src.graph import build_graph

    logging.basicConfig(
        level=logging.DEBUG if settings.livekit_rtc_debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    PREP_OUTPUT.mkdir(parents=True, exist_ok=True)
    thread_id = args.thread_id or str(uuid.uuid4())
    config = _config(thread_id)

    graph = build_graph()
    sqlite_path = args.sqlite or settings.sqlite_path
    Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"\nFirstRound | thread={thread_id}")
    print(f"LLM={settings.llm_provider} | realtime={settings.realtime_mode}")

    print("Phase 1: parsing JD, resume, GitHub, gaps, and planning questions...\n")

    initial = {
        "_jd_text_raw": jd_path.read_text(encoding="utf-8"),
        "_resume_pdf_path": str(resume_path),
        "candidate_name": args.candidate_name or "",
        "role_title": args.role or "",
        "transcript": [],
        "followup_counts": {},
        "guardrail_flags": [],
        "hitl_decision": "pending",
        "current_question_index": 0,
        "next_node_override": None,
    }

    transport = None
    try:
        # Keep the checkpointer open across every interrupt/resume invocation.
        with SqliteSaver.from_conn_string(sqlite_path) as checkpointer:
            app = graph.compile(checkpointer=checkpointer)
            result = app.invoke(initial, config=config)

            while True:
                interrupts = _interrupts(result)
                if not interrupts:
                    break
                payload = (
                    interrupts[0].value
                    if hasattr(interrupts[0], "value")
                    else interrupts[0]
                )
                decision = _prompt_hitl(payload)
                print(f"\nHITL decision: {decision['action']}")

                # A rejected plan loops back to planning. Approved/edited plans
                # cross the boundary into live media, so connect at that point.
                if (
                    decision["action"] in {"approve", "edit"}
                    and settings.realtime_mode in {"livekit", "daily"}
                    and transport is None
                ):
                    transport = _start_live_call(thread_id, settings)
                result = app.invoke(Command(resume=decision), config=config)

            snapshot = app.get_state(config)
            state = dict(snapshot.values)

        _save_prep(state)
        _save_final(state)
    except Exception as exc:
        if settings.realtime_mode == "livekit":
            from src.realtime.livekit_transport import LiveKitTransportError

            if isinstance(exc, LiveKitTransportError):
                print(f"\nLiveKit interview aborted: {exc}", file=sys.stderr)
                return 3
        raise
    finally:
        if settings.realtime_mode in {"livekit", "daily"}:
            from src.realtime.transport import close_transport

            close_transport()

    print("\n" + "=" * 72)
    print("FIRSTROUND RUN COMPLETE")
    print("=" * 72)
    print(f"Candidate : {state.get('candidate_name', '')}")
    print(f"Role      : {state.get('role_title', '')}")
    print(f"Questions : {len(state.get('question_plan', {}).get('questions', []))}")
    print(f"Turns     : {len(state.get('transcript', []))}")
    if state.get("scorecard"):
        sc = state["scorecard"]
        print(f"Score     : {sc.get('overall_score', 'N/A')}/5")
        print(f"Decision  : {str(sc.get('recommendation', 'N/A')).upper()}")
    print("\nOutputs:")
    print(f"  {PREP_OUTPUT / 'jd.json'}")
    print(f"  {PREP_OUTPUT / 'resume.json'}")
    print(f"  {PREP_OUTPUT / 'github.json'}")
    print(f"  {PREP_OUTPUT / 'gap_analysis.json'}")
    print(f"  {PREP_OUTPUT / 'question_plan.json'}")
    print(f"  {OUTPUT / 'transcript.json'}")
    print(f"  {OUTPUT / 'scorecard.json'}")
    print(f"  {OUTPUT / 'report.pdf'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="FirstRound AI Interviewer")
    parser.add_argument("--jd", default="inputs/jd.txt", help="Path to plain-text job description")
    parser.add_argument("--resume", required=True, help="Path to candidate resume PDF")
    parser.add_argument("--candidate-name", default="", help="Optional display name; parser output wins when available")
    parser.add_argument("--role", default="", help="Optional role title; parser output wins when available")
    parser.add_argument("--mode", choices=["console", "livekit", "daily"], default=os.getenv("REALTIME_MODE", "console"),
                        help="console=dev double; livekit=real LiveKit call; daily=legacy Daily call")
    parser.add_argument("--llm-provider", choices=["groq", "anthropic", "mock"], default=None)
    parser.add_argument("--sqlite", default=None, help="SQLite checkpoint path")
    parser.add_argument("--thread-id", default=None, help="Stable thread id for resume-after-drop")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())