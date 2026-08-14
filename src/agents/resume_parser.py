"""
parse_resume -> roles, claims, skills, links

Uses pdfplumber for extraction (handles messier layouts better than pypdf
for two-column resumes, which is why it's picked over pypdf here despite
the SKILL.md's stack table listing both as options — worth a line in
ARCHITECTURE.md if the viva asks about this choice).
"""
import json
from pathlib import Path
from src.llm_client import llm_json_retry

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "resume_parser_v2.md"


def extract_pdf_text(pdf_path: str) -> str:
    import pdfplumber

    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    text = "\n".join(text_parts).strip()
    if not text:
        raise ValueError(
            f"No extractable text in {pdf_path}. If this is a scanned/image "
            "resume, OCR it first (see /mnt/skills/public/pdf-reading in the "
            "build environment, or pytesseract locally) — this pipeline does "
            "not silently fall back to OCR because a mis-OCR'd resume would "
            "poison every downstream question with wrong facts."
        )
    return text


def parse_resume(resume_text: str) -> dict:
    system_prompt = PROMPT_PATH.read_text()
    result = llm_json_retry(system_prompt, f"RESUME TEXT:\n\n{resume_text}")
    return result


def parse_resume_from_file(pdf_path: str, output_path: str = "output/prep/resume.json") -> dict:
    text = extract_pdf_text(pdf_path)
    result = parse_resume(text)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    out = parse_resume_from_file("inputs/resume.pdf")
    print(json.dumps(out, indent=2))
