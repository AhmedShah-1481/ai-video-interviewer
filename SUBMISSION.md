# FirstRound Submission Checklist

## What is implemented

- [x] LangGraph prep → HITL → interview → scoring pipeline
- [x] Real `interrupt()` based HITL approval/edit/reject flow
- [x] SQLite checkpointing with stable thread IDs
- [x] JD parsing
- [x] Resume PDF parsing
- [x] GitHub grounding
- [x] Gap analysis
- [x] Source-tagged question planning
- [x] Adaptive follow-up / verification / recovery routing
- [x] Banned-question guardrail before the candidate sees a question
- [x] Evidence-required scoring guardrail
- [x] Transcript and scorecard JSON outputs
- [x] PDF report
- [x] Realtime transport abstraction
- [x] Console development transport
- [x] LiveKit live transport implementation (recommended stack)
- [x] Daily live transport implementation (legacy, kept for reference)
- [x] Barge-in polling in the live audio loop
- [x] Simli lip-synced avatar, with automatic fallback to the local 2D avatar on any error
- [x] MCP server
- [x] Evaluation personas
- [x] Prompt v1/v2 files and iteration notes

## Run before submission

```bash
pip install -r requirements.txt
pytest -q
python evals/run_evals.py
```

Then perform a real run with the candidate's consented resume:

```bash
python -m src.main --resume inputs/resume.pdf --jd inputs/jd.txt --mode livekit
```

## Evidence to collect

Replace every `TODO` below with the real evidence produced by your run. Do not invent timings, scores, or URLs.

- Public repository URL: `TODO`
- Code walkthrough video: `TODO`
- Live interview recording: `TODO`
- Candidate consent captured: `TODO`
- Interview duration observed: `TODO`
- Observed barge-in stop latency: `TODO`
- GitHub-grounded questions observed: `TODO`
- Final recommendation from `output/scorecard.json`: `TODO`
- PDF report reviewed: `TODO`
- MCP client screenshot/demo: `TODO`
- v1 vs v2 evaluation results: `TODO`

## Suggested 8+ minute demo evidence

1. Show the JD and real candidate resume.
2. Run prep and show parsed artifacts.
3. Stop at the HITL interrupt.
4. Approve or edit a question and resume the same thread.
5. Start the live Daily call.
6. Demonstrate at least one interruption/barge-in.
7. Demonstrate a shallow answer causing a follow-up.
8. Demonstrate a GitHub-specific question grounded in an actual repository.
9. Finish the interview and show transcript, scorecard, and PDF report.
10. Show MCP tools in a compatible MCP client.

## Submission honesty rule

The console transport is a test double. It must not be presented as the live video interview. If a provider feature or environment-specific media path was not successfully tested, state that explicitly rather than claiming it was verified.
