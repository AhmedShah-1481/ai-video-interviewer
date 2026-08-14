"""
Thin wrapper so every agent calls one function — llm_json() — regardless of
whether we're pointed at Groq (fallback, free) or Anthropic (if you have a key).

Why this exists as its own file: the viva asks you to justify architecture
choices. The answer here is "one seam between all my agents and whichever
LLM I'm using, so swapping providers or adding retry/logging logic doesn't
touch agent code."
"""
import json
import re
from src.config import SETTINGS


def _strip_code_fences(text: str) -> str:
    return re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()


def llm_json(system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> dict:
    """
    Calls the configured LLM, forces JSON-only output, parses and returns a dict.
    Raises ValueError if the model didn't return valid JSON — callers should
    catch this and retry once with a stricter reminder rather than silently
    passing garbage downstream (this is why gap_analysis/question_planner
    wrap calls in a retry loop, not because the model is unreliable per se).
    """
    if SETTINGS.llm_provider == "groq":
        text = _call_groq(system_prompt, user_prompt, max_tokens)
    elif SETTINGS.llm_provider == "anthropic":
        text = _call_anthropic(system_prompt, user_prompt, max_tokens)
    elif SETTINGS.llm_provider == "mock":
        text = _call_mock(system_prompt, user_prompt)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {SETTINGS.llm_provider}")

    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Model did not return valid JSON. Raw output:\n{text}") from e


def _call_groq(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    from groq import Groq  # pip install groq

    client = Groq(api_key=SETTINGS.groq_api_key)
    resp = client.chat.completions.create(
        model=SETTINGS.groq_model,
        max_tokens=max_tokens,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt + "\n\nRespond with ONLY valid JSON. No markdown fences, no preamble."},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content


def _call_anthropic(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    import anthropic  # pip install anthropic

    client = anthropic.Anthropic(api_key=SETTINGS.anthropic_api_key)
    resp = client.messages.create(
        model=SETTINGS.anthropic_model,
        max_tokens=max_tokens,
        system=system_prompt + "\n\nRespond with ONLY valid JSON. No markdown fences, no preamble.",
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


def _call_mock(system_prompt: str, user_prompt: str) -> str:
    """
    LLM_PROVIDER=mock — a deterministic, keyword-based stand-in for a real
    model call. NOT for grading. Exists so the graph, agents, and
    evals/run_evals.py can be exercised offline (no API key, no network) —
    e.g. in CI, or in a sandbox with no egress. Real prep/interview/scoring
    runs must use LLM_PROVIDER=groq or =anthropic; the scoring judgment
    quality this project is graded on comes from the real model, not this
    stub. See src/mock_llm.py for the heuristics.
    """
    from src.mock_llm import mock_response
    return json.dumps(mock_response(system_prompt, user_prompt))


def llm_json_retry(system_prompt: str, user_prompt: str, max_tokens: int = 2000, retries: int = 1) -> dict:
    """Retry once with a stricter nudge if the first call didn't parse as JSON."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            return llm_json(system_prompt, user_prompt, max_tokens)
        except ValueError as e:
            last_err = e
            user_prompt = user_prompt + "\n\nREMINDER: output ONLY raw JSON, nothing else."
    raise last_err
