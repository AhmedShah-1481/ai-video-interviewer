"""
outputs -> scorecard.json, transcript.json, report.pdf

report.pdf is the human-readable version of scorecard.json for a recruiter
who doesn't want to read raw JSON. Uses reportlab (fallback column: "reportlab
/ WeasyPrint / HTML->PDF"), since it needs zero system dependencies beyond
the pip package (WeasyPrint needs system Cairo/Pango, riskier under a 24h
clock).
"""
from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)


def _rec_color(rec: str):
    return {"hire": colors.HexColor("#1a7f37"), "no_hire": colors.HexColor("#cf222e"),
            "borderline": colors.HexColor("#9a6700")}.get(rec, colors.black)


def generate_report(scorecard: dict, output_path: str = "output/report.pdf") -> str:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(output_path, pagesize=LETTER,
                             topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                             leftMargin=0.7 * inch, rightMargin=0.7 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleBig", parent=styles["Title"], fontSize=20, spaceAfter=4)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=14, spaceAfter=6)
    body = styles["BodyText"]
    quote_style = ParagraphStyle("Quote", parent=styles["BodyText"], leftIndent=14,
                                  textColor=colors.HexColor("#444444"), fontName="Helvetica-Oblique")

    story = []
    story.append(Paragraph("Interview Scorecard", title_style))
    story.append(Paragraph(
        f"{scorecard.get('candidate_name', 'Unknown')} — {scorecard.get('role', 'Unknown role')}", body))
    story.append(Paragraph(
        f"Interview date: {scorecard.get('interview_date', '')} · "
        f"Duration: {scorecard.get('duration_seconds', 0) // 60}m "
        f"{scorecard.get('duration_seconds', 0) % 60}s · "
        f"GitHub-grounded questions asked: {scorecard.get('github_grounded_questions_asked', 0)}",
        body))
    story.append(Spacer(1, 10))

    rec = scorecard.get("recommendation", "")
    rec_style = ParagraphStyle("Rec", parent=styles["Heading1"], fontSize=16, textColor=_rec_color(rec))
    story.append(Paragraph(f"Recommendation: {rec.upper() if rec else 'N/A'}"
                            f" (overall {scorecard.get('overall_score', 'N/A')}/5)", rec_style))
    if scorecard.get("recommendation_reasoning"):
        story.append(Paragraph(scorecard["recommendation_reasoning"], body))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#dddddd"), spaceBefore=10, spaceAfter=10))

    story.append(Paragraph("Competency scores", h2))
    table_data = [["Competency", "Score", "Confidence", "Evidence"]]
    for comp in scorecard.get("competencies", []):
        score_display = "REJECTED" if comp.get("rejected") else str(comp.get("score", ""))
        quote = comp.get("evidence_quote", "") or "(no quote)"
        table_data.append([
            Paragraph(comp.get("name", ""), body),
            score_display,
            f"{comp.get('confidence', 0):.2f}",
            Paragraph(f"\u201c{quote}\u201d", quote_style),
        ])
    t = Table(table_data, colWidths=[1.3 * inch, 0.6 * inch, 0.8 * inch, 3.3 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    if scorecard.get("strengths"):
        story.append(Paragraph("Strengths", h2))
        for s in scorecard["strengths"]:
            story.append(Paragraph(f"• {s}", body))

    if scorecard.get("concerns"):
        story.append(Paragraph("Concerns", h2))
        for c in scorecard["concerns"]:
            story.append(Paragraph(f"• {c}", body))

    if scorecard.get("guardrail_flags"):
        story.append(Paragraph("Guardrail flags", h2))
        for f in scorecard["guardrail_flags"]:
            story.append(Paragraph(f"• {f}", body))

    doc.build(story)
    return output_path


if __name__ == "__main__":
    import json
    import sys

    scorecard_path = sys.argv[1] if len(sys.argv) > 1 else "output/scorecard.json"
    scorecard = json.loads(Path(scorecard_path).read_text())
    out = generate_report(scorecard)
    print(f"Wrote {out}")
