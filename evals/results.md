# Eval results

Provider: `mock` — run at 2026-08-13T18:17:09+00:00Z

> **This is the offline dry run** (`LLM_PROVIDER=mock`, see `src/mock_llm.py`) — it proves the
> scoring pipeline, ranking logic, and evidence guardrail all run correctly end to end without an
> API key. It is NOT the graded evals run. Re-run with `LLM_PROVIDER=groq` (or `anthropic`) before
> submission and replace this file — see the honest-failure note below for what to watch for when
> you do.

| Rank | Persona | Overall | Recommendation | Expected |
|---|---|---|---|---|
| 1 | strong | 4.4 | hire | Highest, hire, high confidence |
| 2 | nervous | 4.4 | hire | Fairness case — must land near Strong despite hesitation |
| 3 | average | 2.6 | borderline | Middle, borderline, OK |
| 4 | weak | 2.2 | no_hire | Lowest, no_hire |
| 5 | bluffer | 2.2 | no_hire | Hard case — confident-and-empty, must land below Average |

## Ranking checks

- [x] Strong ranks above Average
- [x] Average ranks above Weak
- [x] Bluffer ranks below Average (the hard case)
- [x] Nervous ranks near Strong, not penalized for hesitation

## Per-persona detail

### strong — overall 4.4, hire
- Reasoning: [mock scorer] overall=4.4, bluff_collapse_detected=False, specific_markers=44, vague_markers=0, silent_turns=0.
  - technical depth: 5 — evidence: "That came from a real incident — about 1 in 20 calls"
  - decomposition: 5 — evidence: "For chunking I start from the failure mode, not a default number"
  - shipping ability: 5 — evidence: "I built a RAG FAQ bot for my university's CS club —"
  - debugging: 4 — evidence: "First I'd check if it's a retrieval problem or a generation problem"
  - communication: 3 — evidence: "Yeah — when a senior reviews a junior's PR here, is the"

### nervous — overall 4.4, hire
- Reasoning: [mock scorer] overall=4.4, bluff_collapse_detected=False, specific_markers=27, vague_markers=0, silent_turns=0.
  - technical depth: 5 — evidence: "Um, sorry — 500 tokens because it's about one to two paragraphs"
  - decomposition: 5 — evidence: "Sorry, um... okay. I look at, um, where answers usually live in"
  - shipping ability: 5 — evidence: "Um, sorry, give me a second — okay. So, I built a"
  - debugging: 4 — evidence: "Um, sorry, let me think this through out loud... first I'd pull"
  - communication: 3 — evidence: "Sorry, sure — what does a typical PR review look like on"

### average — overall 2.6, borderline
- Reasoning: [mock scorer] overall=2.6, bluff_collapse_detected=False, specific_markers=7, vague_markers=7, silent_turns=0.
  - technical depth: 4 — evidence: "I think I picked 500 because it seemed like a reasonable number,"
  - decomposition: 2 — evidence: "I usually just split the text into chunks that aren't too big"
  - shipping ability: 2 — evidence: "I made a RAG chatbot for FAQs. I used Python and a"
  - debugging: 2 — evidence: "I'd probably check the logs first and see if there's an obvious"
  - communication: 3 — evidence: "What's the team size like?"

### weak — overall 2.2, no_hire
- Reasoning: [mock scorer] overall=2.2, bluff_collapse_detected=True, specific_markers=2, vague_markers=10, silent_turns=1.
  - technical depth: 1 — evidence: "I don't remember writing that file specifically, it might have been copied"
  - decomposition: 2 — evidence: "Chunking... is that like splitting the data? I'm not really sure how"
  - shipping ability: 3 — evidence: "I made a chatbot thing, it uses AI to answer questions. I"
  - debugging: 2 — evidence: "I guess I'd just restart it and see if that fixes it,"
  - communication: 3 — evidence: "No, not really."

### bluffer — overall 2.2, no_hire
- Reasoning: [mock scorer] overall=2.2, bluff_collapse_detected=True, specific_markers=2, vague_markers=11, silent_turns=0.
  - technical depth: 2 — evidence: "It's handled, yeah, it's definitely in there somewhere, the system's designed to"
  - decomposition: 2 — evidence: "Great question. Chunking strategy is all about finding the optimal balance, I"
  - shipping ability: 2 — evidence: "Absolutely, so I built a full end-to-end RAG system leveraging cutting-edge AI,"
  - debugging: 2 — evidence: "I'd just generally look into it and apply my usual debugging process,"
  - communication: 3 — evidence: "When would I be starting?"

## Honest failure analysis (mock provider)

Bluffer and Weak tied at 2.2 overall in this run. That's a real limitation of the mock
scorer, not a hidden success: `mock_llm.py` scores off raw specific-vs-vague keyword
density, and the Bluffer persona was written to sound fluent but score low on those same
keywords once pressed, so it lands in the same numeric bucket as someone who is simply
vague throughout — the mock scorer separates "confident-and-empty" from "plain weak" only
by direction of rank (bluffer still sits at #5, weak at #4, never above Average), not by a
clean score gap. A real LLM scorer should do better here because it can read *why* an answer
is empty (confident tone dodging a specific artifact vs. genuinely not knowing) rather than
just counting vague-sounding words — that's exactly the semantic judgment this eval exists
to test, and it's the first thing to check when re-running with `LLM_PROVIDER=groq`: does the
real run separate Bluffer's score from Weak's, and does its `recommendation_reasoning` name
the fluent-but-empty pattern the way `prompts/scorer_v2.md` instructs it to?
