"""Offline consistency checks for test assets; not an application or AI test."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from pypdf import PdfReader
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "evals/fixtures/development/D1-qualification"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalise(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    manifest = load(PACK / "manifest.json")
    key = load(ROOT / "evals/answer-keys/D1-qualification.json")
    source_spec = load(PACK / "source-spec.json")
    schema = load(ROOT / "contracts/qualification/analysis.schema.json")
    Draft202012Validator.check_schema(schema)
    schema_validator = Draft202012Validator(schema)
    require(manifest["synthetic"] and key["control_only"], "Missing synthetic/control labels")
    anchors = {}
    for document in manifest["documents"]:
        path = PACK / document["path"]
        require(hashlib.sha256(path.read_bytes()).hexdigest() == document["sha256"], f"Hash mismatch: {path.name}")
        reader = PdfReader(path)
        require(len(reader.pages) == document["pages"], "Page-count mismatch")
        for anchor in document["anchors"]:
            text = reader.pages[anchor["page"] - 1].extract_text() or ""
            require("FICTIONAL TEST DATA" in text, f"Missing fictional label: {anchor['anchor_id']}")
            anchors[anchor["anchor_id"]] = normalise(text)
    for source in source_spec["documents"]:
        for index, page in enumerate(source["pages"], 1):
            actual = anchors[f"{source['version_id']}-p{index}"]
            for paragraph in [page["title"], *page["paragraphs"]]:
                require(normalise(paragraph) in actual, f"Missing or clipped source text: {source['version_id']} page {index}")
    event = load(PACK / "events/engineering-answer.json")
    anchors[event["anchor_id"]] = normalise(event["text"])
    require(hashlib.sha256((PACK / "events/engineering-answer.json").read_bytes()).hexdigest() == manifest["answer_events"][0]["sha256"], "Answer event changed")
    for requirement in key["mandatory_requirements"]:
        require(normalise(requirement["quote"]) in anchors[requirement["source_anchor"]], f"Bad answer-key quote: {requirement['key']}")
    support = key["company_support"]
    for quote in [support["certificate_quote"], *support["experience_quotes"], support["attendance_quote"], support["unknown_capacity_quote"]]:
        require(normalise(quote) in anchors[support["anchor_id"]], "Unsupported company answer-key fact")
    now = datetime.fromisoformat(key["initial_clock"])
    closing = datetime.fromisoformat(key["initial_facts"]["closing_at"])
    due = max(now, min(now + timedelta(hours=48), closing - timedelta(hours=24)))
    require(due == datetime.fromisoformat(key["expected_question"]["default_due_at"]), "Wrong expected due time")
    stages = {stage["name"]: stage for stage in key["stages"]}
    require(datetime.fromisoformat(stages["initial"]["clock"]) < datetime.fromisoformat(event["recorded_at"]) <= datetime.fromisoformat(stages["answered"]["clock"]) < datetime.fromisoformat(stages["amended"]["clock"]), "Invalid event chronology")
    allowed_docs = {document["version_id"] for document in manifest["documents"]}
    for stage in manifest["stages"]:
        require(set(stage["document_versions"]) <= allowed_docs, "Unknown stage document")
        require(not stage["answer_versions"] or stage["answer_versions"] == [event["evidence_version_id"]], "Unknown answer version")
    count = 0
    for name in ["initial", "answered", "amended"]:
        candidate = load(PACK / f"mock-responses/analysis-{name}.json")
        schema_validator.validate(candidate)
        require(set(candidate) == set(schema["required"]), "Mock top-level keys differ from contract")
        require(candidate["recommendation"]["decision"] == stages[name]["recommendation"], "Wrong mock recommendation")
        require(candidate["key_facts"]["closing_at"]["value"] == stages[name]["closing_at"], "Wrong mock closing time")
        ids = [r["local_ref"] for r in candidate["requirements"]]
        require(len(ids) == len(set(ids)) == 6, "Invalid mock requirement IDs")
        for field in candidate["key_facts"].values():
            for cite in field["citations"]:
                require(normalise(cite["quote"]) in anchors[cite["anchor_id"]], "Mock fact citation missing")
                count += 1
        for requirement in candidate["requirements"]:
            for cite in requirement["tender_citations"] + requirement["company_citations"]:
                require(normalise(cite["quote"]) in anchors[cite["anchor_id"]], "Mock requirement citation missing")
                count += 1
        staff = next(r for r in candidate["requirements"] if r["local_ref"] == "R4")
        require(staff["status"] == stages[name]["r4_status"], "Wrong mock staffing state")
        if name == "answered":
            require(staff["company_citations"][0]["anchor_id"] == event["anchor_id"], "Answer was not cited")
        if name == "amended":
            require("three FM-T2" in staff["text"] and staff["tender_citations"][0]["anchor_id"] == "addendum-v1-p1", "Amendment missing")
        for draft in candidate["review_requests"]:
            require(set(draft["requirement_refs"]) <= set(ids), "Mock review refers to missing requirement")
    print(f"PASS: {len(manifest['documents'])} PDF hashes, {len(anchors) - 1} pages, source text, answer event, stage clocks, JSON Schema and {count} mock citations are consistent.")
    print("This is offline fixture verification. No AI, parser-adoption, queue, API or UI behaviour was tested.")


if __name__ == "__main__":
    main()
