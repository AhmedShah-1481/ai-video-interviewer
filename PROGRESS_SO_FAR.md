# WORK IN PROGRESS — Stage 1 & 2 of 5, + stack swap

This zip is a snapshot mid-build. Here's what's real and what's still missing.

## Stack swap: Daily -> LiveKit + Simli

The realtime stack was swapped from Daily.co + local 2D avatar only, to
LiveKit Cloud + LiveKit Agents + Simli (matching the spec's "recommended"
column instead of the fallback column), primarily to get off the Windows
`daily-python` build problem and to try the real avatar vendor.

What changed:
- `src/realtime/livekit_transport.py` (new) — `LiveKitTransport`, same
  `CallTransport` interface `DailyTransport` already implemented.
- `src/realtime/simli_avatar.py` (new) — `AvatarSession` interface with
  `SimliAvatarSession` and `Local2DAvatarSession`; Simli auto-degrades to
  the local avatar on any error so a dead trial doesn't crash a turn.
- `src/realtime/turn_manager.py` — added `_speak_and_listen_livekit()`,
  an async path parallel to the existing sync `_speak_and_listen_daily()`.
  `speak_and_listen()` now dispatches on `REALTIME_MODE` across three
  values: console / livekit / daily.
- `src/config.py`, `.env.example`, `requirements.txt`, `src/main.py`,
  `README.md`, `ARCHITECTURE.md`, `SUBMISSION.md` updated accordingly.
  `daily-python` is commented out of requirements.txt by default.

**Not exercised end-to-end** — same honest flag the original Daily code
carried: written against LiveKit's and Simli's documented APIs, but this
build environment has no network access to actually open a LiveKit room or
a Simli session. Treat your first real run against real LiveKit Cloud +
Simli credentials as a debugging session (PHASE_PLAN.md Phase 1), and
budget time for it — this is a genuinely new integration, not a config
change, even though the `CallTransport`/`AvatarSession` seams kept the
blast radius contained to `src/realtime/`.

## Done
- Repo skeleton
- `inputs/jd.txt` — the Junior AI Engineer JD (system must still accept any JD)
- Prep-phase agents: `src/agents/{jd_parser,resume_parser,github_agent,gap_analysis,question_planner}.py`
- `src/llm_client.py` — Groq/Anthropic-agnostic LLM wrapper
- Guardrails: `src/guardrails/{banned_questions,evidence_check}.py`
- `src/state.py` — typed graph state
- `src/graph.py` + `src/nodes/*.py` — the full LangGraph graph: 17 nodes,
  2 conditional-edge functions, SQLite checkpointer, real HITL `interrupt()`
- `prompts/` — v1 and v2 prompts with iteration notes (has TODOs for you to
  fill in with your actual observed test output — see the note at the top
  of ITERATION_NOTES.md, this matters for the viva)

## Not built yet (coming next)
- `src/realtime/` — **empty right now**, graph.py imports `speak_and_listen`
  from `src.realtime.turn_manager` which doesn't exist yet, so **this will
  not run until Stage 3 lands**. This is next.
- `mcp_server/` — the 5+ tool MCP server
- `evals/` — 5 personas + scorer
- `output/report.pdf` generation
- `ARCHITECTURE.md`, `SUBMISSION.md`, `README.md`, `.env.example`,
  `requirements.txt`

## Known TODOs already flagged in code
- `prompts/ITERATION_NOTES.md` has two `TODO(you)` markers — paste your
  actual v1-vs-v2 output once you run it on your real candidate.
- `inputs/resume.pdf` isn't in this zip — you need to add your actual
  interview partner's real resume there before running the prep phase.

Don't try to run this yet — it'll fail on the realtime import. Next message
picks up with `src/realtime/` (transport, avatar, barge-in), then MCP,
evals, and docs.
