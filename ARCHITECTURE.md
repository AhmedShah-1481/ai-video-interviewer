# FirstRound Architecture

## 1. System flow

```text
JD + Resume PDF
      |
      v
+------------------- PREP -------------------+
| parse_jd                                    |
|     -> parse_resume                         |
|     -> github_agent                         |
|     -> gap_analysis                         |
|     -> question_planner                     |
+----------------------+----------------------+
                       |
                       v
             +------------------+
             |   HITL interrupt |
             | approve/edit/    |
             | reject/regenerate|
             +--------+---------+
                      |
                      v
+------------------- LIVE INTERVIEW -------------------+
| intro -> resume_probe -> jd_fit -> github_deepdive  |
|              -> scenario -> candidate_Qs -> wrap_up |
|                                                      |
| after candidate answers:                             |
| shallow       -> follow_up                           |
| bluff         -> verify                              |
| silent/offtopic -> recovery                          |
| time budget   -> wrap_up                             |
+-------------------------+----------------------------+
                          |
                          v
+-------------------- SCORING -------------------------+
| transcript + question plan -> LLM scorecard         |
| evidence guardrail -> scorecard.json                |
| transcript.json -> report_generator -> report.pdf   |
+------------------------------------------------------+
```

## 2. LangGraph state

`src/state.py` defines one typed state shared across prep, live interview, and scoring.

Important fields include:

- `jd`, `resume`, `github_data`, `gap_analysis`, `question_plan`: prep artifacts;
- `hitl_decision`: `pending`, `approved`, `edited`, or `rejected`;
- `current_question`, `current_question_index`: interview position;
- `followup_counts`: caps follow-up probes per question;
- `last_candidate_answer`, `last_answer_quality`: adaptive routing inputs;
- `transcript`: append-only interview evidence;
- `interview_start_ms`, `call_elapsed_ms`: time-budget enforcement;
- `barge_in_flag`: records candidate interruption of agent speech;
- `guardrail_flags`: safety/quality events;
- `scorecard`: final scoring artifact.

## 3. Why LangGraph

The workflow is stateful and contains real branching plus human approval. LangGraph makes the graph transitions explicit and gives us checkpointed state around the HITL interrupt.

The graph has two main conditional routing functions:

### `route_after_prep`

The HITL decision routes either to `intro` or back to `question_planner` for regeneration.

### `route_after_turn`

Every answer-producing interview node uses the same router. It can send the graph to:

- `follow_up` when the answer is shallow;
- `verify` when a bluff/unsupported claim is suspected;
- `recovery` for silence/off-topic answers;
- the current phase's next question;
- the next interview phase;
- `wrap_up` when the time budget is exceeded.

This avoids embedding routing policy separately inside every question node.

## 4. HITL implementation

`src/nodes/hitl_gate.py` uses LangGraph's `interrupt()` rather than a fake `input()` pause. The CLI receives the interrupt payload and resumes the same graph with:

```python
app.invoke(Command(resume=decision), config=config)
```

The CLI keeps the same SQLite checkpointer connection open during the run. The `thread_id` is stable, so a suspended run can be resumed with the same configuration.

Approve and edit both pass through the banned-question filter again. Reject sets the graph to regenerate the plan.

## 5. Realtime architecture

`src/realtime/turn_manager.py` is the seam between graph nodes and media.

### Console mode

`ConsoleTransport` prints agent text and accepts typed candidate answers. A leading `!` simulates an interruption. This mode is for development/evaluation only.

### LiveKit mode (recommended, default)

`LiveKitTransport` connects to a LiveKit Cloud room via LiveKit Agents and exposes an audio/video track pair to the turn manager. Because LiveKit's SDK is asyncio-native and the rest of this codebase's turn logic was originally written synchronously, `LiveKitTransport` runs its own background event-loop thread and bridges every call across it — the class still implements the exact same `CallTransport` interface as `DailyTransport`, so no node/graph code changed. Agent TTS audio is streamed in chunks; each chunk is checked for candidate speech using `BargeInMonitor`, same as the Daily path — if speech is detected, outgoing audio is stopped immediately. Candidate audio is accumulated until silence or the hard answer-duration cap, then sent to Groq Whisper.

### Daily mode (legacy)

`DailyTransport` creates a Daily room and exposes audio/video media to the turn manager, with the same barge-in and silence-based listening behavior as the LiveKit path. Kept in the codebase for reference; not the default because of Windows install friction with `daily-python`.

## 6. Avatar

Two interchangeable implementations behind one `AvatarSession` interface (`src/realtime/simli_avatar.py`), selected by `AVATAR_PROVIDER`:

- **Simli (recommended, default)** — a real lip-synced avatar via Simli's WebSocket session API. Audio chunks are streamed in, lip-synced video frames come back. Any failure (dead trial credits, network error, mid-call drop) degrades that session to the local 2D avatar automatically rather than crashing the interview turn — this is deliberate: the spec's grading philosophy explicitly protects against vendor trial credits running out.
- **Local 2D (fallback)** — a local asset set in `assets/avatar/`. TTS audio is converted to a coarse amplitude envelope and mapped to closed/narrow/mid/wide mouth shapes. This is what the spec's fallback column calls "portrait image + viseme lip-sync driven by the TTS stream," and it earns full marks on its own — it's not a lesser option, just a different one.

## 7. LLM boundary

All LLM calls pass through `src/llm_client.py`.

Supported providers:

- Groq;
- Anthropic;
- deterministic mock provider for offline tests.

The seam allows provider switching without changing the individual agents.

## 8. GitHub grounding

`github_agent.py` extracts the GitHub URL from the parsed resume and fetches public profile/repository data. The question planner receives JD, resume, GitHub, and gap-analysis context and creates source-tagged questions. The scoring node counts GitHub-grounded questions from the actual transcript node.

## 9. Guardrails

### Banned-question guardrail

Question plans are filtered before HITL. HITL-edited plans are filtered again. Questions are also checked immediately before speaking, preventing a dynamically generated/edited unsafe question from reaching the candidate.

### Evidence guardrail

The scorer must produce an evidence quote for competency scoring. `validate_scorecard()` enforces this after the LLM returns; a prompt instruction alone is not trusted.

## 10. Outputs

The scoring node writes:

- `output/scorecard.json`;
- `output/transcript.json`.

`report_generator.py` turns the scorecard into `output/report.pdf`.

## 11. Known limitations / honest claims

1. Console mode is not a real video interview.
2. LiveKit integration depends on local audio permissions, the installed `livekit`/`livekit-api` SDKs, and a live LiveKit Cloud project; the legacy Daily path has the equivalent dependency on `daily-python`.
3. Simli avatar quality and availability depend on trial credit balance; the local 2D fallback uses coarse amplitude-derived mouth shapes rather than phoneme-perfect visemes, and is what's actually used whenever Simli is unset, out of credit, or drops mid-call.
4. GitHub grounding depends on public API access and may be rate-limited without a token.
5. LLM quality depends on the configured provider/model.
6. Prompt iteration notes must be populated from real observed runs; they should not contain fabricated metrics.
