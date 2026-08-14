# Prompt iteration notes

> **Before you submit:** the two entries below describe the *design* failure
> each v1 prompt has and the fix in v2. That's real and you can verify it by
> re-running v1 against your own test JD/resume and reading the output. But
> the grader wants YOUR observed failure text from YOUR actual run, not a
> generic description — after you run `evals/run_evals.py` and test the prep
> phase on your real candidate, paste the actual bad output you got from v1
> here (or note if v1 happened to work fine on your data — that's honest too).
> Don't leave this file as pure theory; it's graded on being a *real diagnosed
> failure*, and the viva will ask "which prompt version failed and why."

## resume_parser: v1 → v2

**What v1 got wrong:** v1 says "summarize each section concisely." On a test
run this produces paraphrased claims instead of verbatim ones — e.g. resume
says "Built a RAG pipeline using LangChain and Pinecone for a university
project," and v1's output collapses this to `"experience with RAG"`. That
loses the specific tool names (LangChain, Pinecone) the GitHub agent needs to
cross-reference, and loses the wording the interviewer would need to quote
back accurately. It also has no explicit instruction to search the whole
document for a GitHub link, so v1 sometimes returns `github_url: ""` even
when a link exists in a header/contact block rather than a dedicated "Links"
section.

**Fix in v2:** explicit instruction to copy claims verbatim rather than
summarize, and an explicit multi-location search + username-to-URL
construction rule for github_url.

`TODO(you): paste your actual v1 output on your real candidate's resume here,
showing the collapsed claim, then paste v2's output on the same input.`

## question_planner: v1 → v2

**What v1 got wrong:** v1 says "mix easy and hard questions" and asks for
GitHub-sourced questions implicitly (via "source" field existing in schema)
but never makes the ≥3 GitHub-grounded requirement explicit or defines what
counts. In testing, v1 frequently generates generic questions tagged
`"source": "github"` like "Tell me about a project on your GitHub" with no
`source_reference` — which satisfies the schema but not the actual grading
requirement (a real repo/file/commit reference). It also never asks a
"verify" question when the gap analysis flags an unsupported resume claim,
so bluffing candidates aren't specifically targeted.

**Fix in v2:** made the ≥3 GitHub-grounded rule explicit with a definition of
what does NOT count (generic mentions), and added a hard rule to generate a
verify-style question whenever gap_analysis flags a claim with no GitHub
evidence.

`TODO(you): paste your actual v1 vs v2 question_plan.json diff on your real
candidate here.`
