"""
parse_jd -> competencies, must-haves, seniority

Input: raw JD text (any JD, not just the sample one — the grader may swap
inputs/jd.txt for a different role and re-run).
Output: output/prep/jd.json
"""
import json
from pathlib import Path
from src.llm_client import llm_json_retry

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "jd_parser_v2.md"


def parse_jd(jd_text: str) -> dict:
    system_prompt = PROMPT_PATH.read_text()
    result = llm_json_retry(system_prompt, f"JOB DESCRIPTION:\n\n{jd_text}")
    return result


def parse_jd_from_file(input_path: str, output_path: str = "output/prep/jd.json") -> dict:
    jd_text = Path(input_path).read_text()
    result = parse_jd(jd_text)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    out = parse_jd_from_file("inputs/jd.txt")
    print(json.dumps(out, indent=2))
