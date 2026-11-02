"""Build fictional qualification input PDFs and clearly labelled mock responses.

This generates test assets only. It does not call an AI, test the application,
or derive an answer key from the implementation under test.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "evals/fixtures/development/D1-qualification"
KEY_PATH = ROOT / "evals/answer-keys/D1-qualification.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_pdf(source: dict) -> dict:
    target = PACK / source["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="FixtureTitle", fontName="Helvetica-Bold", fontSize=18,
                              leading=23, spaceAfter=16, textColor=colors.HexColor("#142334")))
    styles.add(ParagraphStyle(name="FixtureBody", fontName="Helvetica", fontSize=11,
                              leading=14, spaceAfter=7, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="FixtureHeading", fontName="Helvetica-Bold", fontSize=12,
                              leading=16, spaceBefore=8, spaceAfter=9))
    doc = SimpleDocTemplate(str(target), pagesize=A4, leftMargin=22 * mm,
                            rightMargin=22 * mm, topMargin=21 * mm, bottomMargin=23 * mm,
                            title=source["pages"][0]["title"], author="Fictional evaluation fixture")
    story = []
    for page_index, page in enumerate(source["pages"]):
        if page_index:
            story.append(PageBreak())
        story.append(Paragraph(escape(page["title"]), styles["FixtureTitle"]))
        for text in page["paragraphs"]:
            is_heading = (len(text) < 65 and not text.endswith(".") and
                          not text.startswith("FICTIONAL"))
            style = styles["FixtureHeading"] if is_heading else styles["FixtureBody"]
            story.append(Paragraph(escape(text), style))
        story.append(Spacer(1, 2 * mm))

    def footer(pdf_canvas, _doc):
        pdf_canvas.saveState()
        pdf_canvas.setFillColor(colors.HexColor("#56616d"))
        pdf_canvas.setFont("Helvetica", 8)
        pdf_canvas.drawString(22 * mm, 12 * mm, "Fictional test data only | D1 qualification")
        pdf_canvas.drawRightString(A4[0] - 22 * mm, 12 * mm,
                                   f"{source['version_id']} | Page {pdf_canvas.getPageNumber()}")
        pdf_canvas.restoreState()

    def deterministic_canvas(*args, **kwargs):
        kwargs["invariant"] = 1
        return canvas.Canvas(*args, **kwargs)

    doc.build(story, onFirstPage=footer, onLaterPages=footer, canvasmaker=deterministic_canvas)
    reader = PdfReader(target)
    if len(reader.pages) != len(source["pages"]):
        raise AssertionError(f"Unexpected pagination for {target.name}: {len(reader.pages)}")
    return {
        "version_id": source["version_id"], "role": source["role"], "path": source["path"],
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "pages": len(reader.pages), "synthetic": True,
        "amends_version_id": source.get("amends_version_id"),
        "anchors": [{"anchor_id": f"{source['version_id']}-p{i + 1}",
                     "page": i + 1} for i in range(len(reader.pages))],
    }


def citation(anchor_id: str, quote: str) -> dict:
    return {"anchor_id": anchor_id, "quote": quote}


def build_mock_candidates(key: dict, event: dict) -> None:
    """Illustrative API/UI mocks from an authored key; never measured AI output."""
    support = key["company_support"]
    company_anchor = support["anchor_id"]
    value_citations = {
        "title": "Skycourt Campus Maintenance Tender",
        "buyer": "Buyer: Skycourt Property Services.",
        "closing_at": "Closing time is 20 November 2026 at 16:00 Singapore time (UTC+08:00).",
        "service_start_on": "The contract starts on 1 January 2027 and runs for 36 months.",
        "term_months": "The contract starts on 1 January 2027 and runs for 36 months.",
    }
    facts = {name: {"value": key["initial_facts"][name],
                    "citations": [citation("tender-v1-p1", quote)]}
             for name, quote in value_citations.items()}
    company_quotes = {
        "R1": [support["certificate_quote"]], "R2": support["experience_quotes"],
        "R3": [support["attendance_quote"]], "R4": [support["unknown_capacity_quote"]],
        "R5": [], "R6": [],
    }
    requirements = []
    for requirement in key["mandatory_requirements"]:
        rid = requirement["key"]
        status = requirement["initial_status"]
        explanation = ("Current accepted company evidence supports this qualification."
                       if status == "met" else
                       "Total qualified headcount does not confirm Saturday availability."
                       if status == "unconfirmed" else
                       "Submission preparation is outside this qualification assessment.")
        requirements.append({
            "local_ref": rid, "text": requirement["quote"], "kind": requirement["kind"],
            "mandatory": True,
            "tender_citations": [citation(requirement["source_anchor"], requirement["quote"])],
            "status": status,
            "company_citations": [citation(company_anchor, q) for q in company_quotes[rid]],
            "explanation": explanation,
            "missing_information": "Confirm two available FM-T2 technicians for the full Saturday duty."
                                   if rid == "R4" else None,
        })
    draft = {
        "draft_ref": "staffing-question", "requirement_refs": ["R4"],
        "suggested_role": "engineering_lead",
        "question": "Can you confirm two FM-T2 qualified technicians for every Saturday from 09:00 to 13:00 for the 36-month contract?",
        "rationale": "The tender requires availability; the company profile confirms only total headcount.",
    }
    initial = {
        "summary": "The supplied evidence supports certification, experience and briefing attendance. Saturday delivery capacity needs confirmation.",
        "key_facts": facts, "requirements": requirements,
        "recommendation": {"decision": "hold", "reasons": ["Mandatory Saturday staffing availability remains unconfirmed."], "condition_refs": ["R4"]},
        "review_requests": [draft], "warnings": [],
    }
    answered = copy.deepcopy(initial)
    answered["summary"] = "The attributed engineering answer confirms the required two-person Saturday availability. Qualification supports continued preparation."
    staffing = next(r for r in answered["requirements"] if r["local_ref"] == "R4")
    staffing.update(status="met", missing_information=None,
                    company_citations=[citation(event["anchor_id"], event["text"])],
                    explanation="The assigned engineering lead confirmed two available technicians for the stated contract duty.")
    answered["recommendation"] = {"decision": "pursue", "reasons": ["Current qualification requirements are supported; submission artifacts remain to be prepared."], "condition_refs": []}
    answered["review_requests"] = []
    amended = copy.deepcopy(answered)
    amended["summary"] = "The addendum requires three Saturday technicians. The existing answer confirms only two, so capacity needs a fresh confirmation."
    amended["key_facts"]["closing_at"] = {"value": "2026-11-27T16:00:00+08:00", "citations": [citation("addendum-v1-p1", "Closing time is 27 November 2026 at 16:00 Singapore time (UTC+08:00).") ]}
    staffing = next(r for r in amended["requirements"] if r["local_ref"] == "R4")
    new_text = "The contractor must provide three FM-T2 qualified technicians on site every Saturday from 09:00 to 13:00 throughout the contract."
    staffing.update(text=new_text, tender_citations=[citation("addendum-v1-p1", new_text)],
                    status="unconfirmed", missing_information="Confirm three available technicians under the amended scope.",
                    explanation="The prior answer covers two technicians only and does not establish availability of three.")
    amended["recommendation"] = {"decision": "hold", "reasons": ["Amended mandatory staffing is not yet confirmed."], "condition_refs": ["R4"]}
    amended["review_requests"] = [{**draft, "draft_ref": "amended-staffing-question",
                                   "question": draft["question"].replace("two FM-T2", "three FM-T2"),
                                   "rationale": "The addendum changed the requirement; the prior answer covers two only."}]
    for name, candidate in [("initial", initial), ("answered", answered), ("amended", amended)]:
        write_json(PACK / f"mock-responses/analysis-{name}.json", candidate)


def main() -> None:
    source_spec = read_json(PACK / "source-spec.json")
    key = read_json(KEY_PATH)
    event_path = PACK / "events/engineering-answer.json"
    event = read_json(event_path)
    documents = [render_pdf(source) for source in source_spec["documents"]]
    manifest = {
        "schema_version": "m1.fixture-manifest.v1", "fixture_id": source_spec["fixture_id"],
        "synthetic": True, "control_only": True, "documents": documents,
        "answer_events": [{"path": "events/engineering-answer.json", "evidence_version_id": event["evidence_version_id"],
                           "anchor_id": event["anchor_id"], "sha256": hashlib.sha256(event_path.read_bytes()).hexdigest()}],
        "stages": [{name: stage[name] for name in ["name", "clock", "document_versions", "answer_versions"]}
                   for stage in key["stages"]],
        "workspace": {"id": "ws-demo", "name": "Fictional qualification workspace"},
        "users": [
            {"id": "user-owner", "name": "Morgan Lane", "roles": ["bid_owner"]},
            {"id": "user-engineer", "name": "Alex Tan", "roles": ["service_reviewer"], "routing_roles": ["engineering_lead"]},
            {"id": "user-approver", "name": "Priya Rao", "roles": ["approver"]},
            {"id": "user-admin", "name": "Casey Lim", "roles": ["admin"]},
            {"id": "user-viewer", "name": "Taylor Lee", "roles": ["viewer"]},
        ],
    }
    write_json(PACK / "manifest.json", manifest)
    build_mock_candidates(key, event)
    print(f"Built {len(documents)} fictional PDFs, {sum(d['pages'] for d in documents)} pages, manifest and 3 labelled mock candidates.")


if __name__ == "__main__":
    main()
