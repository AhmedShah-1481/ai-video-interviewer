"""
gap_analysis -> resume claim vs JD need vs GH evidence

Pure logic + one LLM call — no need for a fancy prompt file since this is
mostly deterministic matching. The LLM's job here is just judgment calls
("does this GitHub repo actually demonstrate 'RAG experience' or just use
an embeddings library incidentally") that a keyword match would get wrong.

Output feeds question_planner, specifically the "verify" question rule:
a claim with support="none" should get a verify-style question generated.
"""
import json
from pathlib import Path
from src.llm_client import llm_json_retry

SYSTEM_PROMPT = """You compare a candidate's resume claims and skills against
a JD's must-have skills, and check which claims have supporting evidence in
their GitHub data (a repo, README, or source file that actually demonstrates
the claim — not just a keyword match).

For each JD must-have skill, classify as: "strong_match" (resume claim +
GitHub evidence both support it), "resume_only" (claimed but no GitHub
evidence found), "github_only" (GitHub shows it but resume doesn't mention
it explicitly), or "gap" (neither resume nor GitHub supports it).

For each resume claim, note whether GitHub evidence supports it: "supported",
"unsupported", or "not_applicable" (claims that aren't the kind of thing
GitHub could show, e.g. "worked well in a team").

Return JSON:
{
  "skill_coverage": [
    {"skill": "", "status": "strong_match|resume_only|github_only|gap", "evidence": ""}
  ],
  "claim_verification": [
    {"claim": "", "github_support": "supported|unsupported|not_applicable", "evidence": ""}
  ],
  "unsupported_claims_to_verify": []
}
"""


def analyze_gaps(jd: dict, resume: dict, github: dict) -> dict:
    user_prompt = (
        f"JD MUST-HAVES:\n{json.dumps(jd.get('must_have_skills', []))}\n\n"
        f"RESUME CLAIMS:\n{json.dumps(resume.get('claims', []))}\n\n"
        f"RESUME SKILLS:\n{json.dumps(resume.get('skills', []))}\n\n"
        f"GITHUB REPOS (name, description, readme excerpt, source samples):\n"
        f"{json.dumps(github.get('repos', []), indent=2)[:6000]}"
    )
    return llm_json_retry(SYSTEM_PROMPT, user_prompt, max_tokens=2500)


def analyze_gaps_from_files(
    jd_path="output/prep/jd.json",
    resume_path="output/prep/resume.json",
    github_path="output/prep/github.json",
    output_path="output/prep/gap_analysis.json",
) -> dict:
    jd = json.loads(Path(jd_path).read_text())
    resume = json.loads(Path(resume_path).read_text())
    github = json.loads(Path(github_path).read_text())
    result = analyze_gaps(jd, resume, github)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    out = analyze_gaps_from_files()
    print(json.dumps(out, indent=2))
