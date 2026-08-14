# FirstRound — AI Video Interviewer

This repository is a LangGraph-based AI interviewer. The existing implementation is organized as three phases:

1. **Prep:** JD parsing → resume parsing → GitHub grounding → gap analysis → question planning.
2. **HITL:** a real LangGraph `interrupt()` pauses the graph so a recruiter can approve, edit, or reject/regenerate the question plan.
3. **Interview + scoring:** the live-call nodes run through the realtime transport, adaptive conditional routing handles follow-ups/verification/recovery, then the scoring node writes the scorecard, transcript, and PDF report.

The graph has a SQLite checkpointer so the same `thread_id` can be used to resume a suspended/failed run.

## 1. Install

Python 3.11+ is recommended.

```bash
python -m venv .venv
```

Windows:

```bash
.venv\\Scripts\\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add the provider keys you actually use. **Never commit `.env` or API keys.**

## 2. Inputs

The default JD is `inputs/jd.txt`.

The resume must be a PDF because the existing resume parser uses `pdfplumber`. Put your candidate resume somewhere such as:

```text
inputs/resume.pdf
```

The parser is deliberately based on the candidate's actual resume rather than hard-coded candidate facts.

## 3. Run the complete pipeline locally

For graph/realtime development without a live call:

```bash
python -m src.main --resume inputs/resume.pdf --jd inputs/jd.txt --mode console
```

The CLI will:

- run the five prep nodes;
- stop at the real LangGraph HITL interrupt;
- show the planned questions;
- let the recruiter **approve**, **edit**, or **reject/regenerate**;
- resume the same graph/thread with `Command(resume=...)`;
- run the interview nodes;
- apply conditional follow-up / verification / recovery routing;
- run scoring;
- write the final artifacts.

### HITL actions

At the prompt:

```text
Approve [a], edit [e], reject/regenerate [r]:
```

For an edit, you can either give a JSON file containing a list of replacement questions or replace one question interactively.

## 4. Real live interview

The console mode is **not** the graded live interview. It exists to exercise the full graph without a microphone/network/media setup.

For the real LiveKit transport (recommended stack):

```bash
python -m src.main --resume inputs/resume.pdf --jd inputs/jd.txt --mode livekit
```

Set:

```text
REALTIME_MODE=livekit
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
AVATAR_PROVIDER=simli
SIMLI_API_KEY=...
SIMLI_FACE_ID=...
GROQ_API_KEY=...
```

On startup, the candidate's join token is printed to the console — paste it into a LiveKit-compatible client (e.g. LiveKit Meet) along with `LIVEKIT_URL` to join the room.

Before running the full graph, isolate signaling and media from every AI
service with the RTC smoke test:

```bash
python -m src.realtime.livekit_smoke
```

It connects and publishes the agent tracks, prints a candidate token, waits
for a candidate, sends a test tone/video frame, and verifies inbound microphone
PCM. For a server-only negotiation check, run
`python -m src.realtime.livekit_smoke --connect-only`. Use `--debug` for event
logs, `--ice relay` to test TURN-only connectivity, or
`--no-single-peer-connection` to compare the legacy publisher/subscriber-PC
topology. A failed smoke test exits nonzero instead of continuing as silence.

The realtime implementation uses:

- LiveKit transport for audio/video (a legacy Daily path also exists — see ARCHITECTURE.md — kept for reference, not the default);
- Simli for the lip-synced avatar, auto-falling back to the local 2D avatar on any Simli error so a depleted trial degrades the face rather than breaking the interview (set `AVATAR_PROVIDER=2d` to skip Simli entirely);
- Groq Whisper for candidate STT;
- Edge TTS by default, or ElevenLabs when configured;
- VAD-based barge-in polling.

The first real LiveKit + Simli run should be treated as an integration test: microphone permissions, SDK behavior, audio devices, LiveKit Cloud project setup, and Simli trial credit balance are all environment-dependent — this is exactly what PHASE_PLAN.md's Phase 1 checkpoint exists to catch early.

## 5. Outputs

After a successful run:

```text
output/
├── prep/
│   ├── jd.json
│   ├── resume.json
│   ├── github.json
│   ├── gap_analysis.json
│   └── question_plan.json
├── transcript.json
├── scorecard.json
├── report.pdf
└── checkpoints.sqlite
```

## 6. Tests / evals

Run unit tests:

```bash
pytest -q
```

Run the existing persona evaluation script:

```bash
python evals/run_evals.py
```

The evaluation files are intentionally kept separate from the production graph.

## 7. MCP

The MCP server is in `mcp_server/server.py` and exposes the project's candidate/question-plan/scorecard/transcript tools. Start it with:

```bash
python mcp_server/server.py
```

Use the MCP server with a compatible MCP client/desktop application and point it at this project directory.

## 8. Important grading/demo note

The console transport is a development double. It must not be represented as a real video interview. For a real submission, use the real realtime transport, a real candidate with consent, and preserve the recording/evidence required by the assignment.

The project also contains prompt iteration notes. Replace any `TODO(you)` items with your **actual observed v1/v2 evaluation results** before final submission rather than inventing metrics.

## 9. Useful commands

```bash
# complete local pipeline
python -m src.main --resume inputs/resume.pdf --mode console

# real LiveKit mode (recommended stack)
python -m src.main --resume inputs/resume.pdf --mode livekit

# legacy Daily mode
python -m src.main --resume inputs/resume.pdf --mode daily

# tests
pytest -q

# evals
python evals/run_evals.py
```
