from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.core.cross_verification import build_cross_verification_matrix
from app.core.intelligence_requirements import build_intelligence_requirements
from app.core.quality import build_quality_assessment, render_structured_report


FIXTURE_PATH = ROOT_DIR / "backend" / "tests" / "fixtures" / "regression_cases.json"


def run_regression_cases(fixture_path: str | Path = FIXTURE_PATH) -> dict:
    cases = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    results = [_run_case(case) for case in cases]
    failed = [case for case in results if case["failures"]]
    return {
        "case_count": len(results),
        "failed": len(failed),
        "cases": results,
    }


def _run_case(case: dict) -> dict:
    detail = _sample_detail(case)
    requirements = build_intelligence_requirements(
        detail["seed_type"],
        detail["seed_value"],
        detail["strategy"],
        detail["metadata"],
    )
    detail["intelligence_requirements"] = requirements
    detail["cross_verification_matrix"] = build_cross_verification_matrix(detail)
    assessment = build_quality_assessment(detail)
    report = render_structured_report(detail, assessment)
    sections = _report_sections(report)
    failures = []
    if not requirements.get("pirs"):
        failures.append("missing PIRs")
    if not requirements.get("eeis"):
        failures.append("missing EEIs")
    if len(detail["cross_verification_matrix"]) != 10:
        failures.append("matrix row count mismatch")
    for required in ("BLUF", "PIR", "I&W"):
        if required not in sections:
            failures.append(f"missing report section: {required}")
    return {
        "id": case["id"],
        "seed_type": detail["seed_type"],
        "pir_count": len(requirements.get("pirs") or []),
        "eei_count": len(requirements.get("eeis") or []),
        "matrix_rows": len(detail["cross_verification_matrix"]),
        "report_sections": sections,
        "score": assessment["score"],
        "failures": failures,
    }


def _sample_detail(case: dict) -> dict:
    seed_type = case["seed_type"]
    seed_value = case["seed_value"]
    entities = []
    evidence = []
    facts = []
    relationships = []
    ledger = []
    if seed_type == "company":
        entities.extend(
            [
                _entity("company", seed_value, "operator_seed", 0.9),
                _entity("domain", "example-manufacturing.com", "official_website", 0.82),
                _entity("email", "sales@example-manufacturing.com", "official_website", 0.72),
                _entity("purchase_category", "construction machinery spare parts", "operator_seed", 0.75),
            ]
        )
    elif seed_type == "domain":
        entities.extend(
            [
                _entity("domain", seed_value, "operator_seed", 0.9),
                _entity("email", f"contact@{seed_value}", "theharvester", 0.5),
            ]
        )
    elif seed_type == "email":
        entities.extend(
            [
                _entity("email", seed_value, "operator_seed", 0.9),
                _entity("domain", seed_value.split("@", 1)[1], "operator_seed", 0.75),
            ]
        )
    elif seed_type == "sparse_lead":
        metadata = case.get("metadata") or {}
        entities.extend(
            [
                _entity("platform_account", metadata.get("member_id", seed_value), "alibaba_screenshot", 0.85),
                _entity("company", metadata.get("company_name_raw", "Sample Lead"), "alibaba_screenshot", 0.7),
                _entity("country_region", metadata.get("country_region", "India"), "alibaba_screenshot", 0.65),
                _entity("purchase_category", metadata.get("purchase_category", "construction machinery spare parts"), "alibaba_screenshot", 0.75),
            ]
        )
    if entities:
        evidence.append(
            {
                "id": f"ev-{case['id']}",
                "entity_value": entities[0]["value"],
                "evidence_kind": "operator_seed",
                "source_tool": entities[0]["source_tool"],
                "snippet": f"Fixed regression seed for {seed_value}",
            }
        )
        ledger.append(
            {
                "id": f"ledger-{case['id']}",
                "source_url": "fixed-regression://sample",
                "source_type": "operator_seed",
                "source_tool": entities[0]["source_tool"],
                "snippet": f"Fixed regression seed for {entities[0]['value']}",
                "admiralty_code": "B-2",
            }
        )
        facts.append(
            {
                "id": f"fact-{case['id']}",
                "statement": f"{seed_value} has a fixed regression seed observation.",
                "subject": seed_value,
                "predicate": "has_seed_observation",
                "object": entities[0]["value"],
                "object_value": entities[0]["value"],
                "status": "CONFIRMED",
                "promotion_stage": "ACCEPTED_FACT",
                "confidence": 0.8,
                "admiralty_code": "B-2",
                "evidence_ids": [f"ev-{case['id']}"],
            }
        )
    return {
        "id": case["id"],
        "name": case["id"],
        "seed_type": seed_type,
        "seed_value": seed_value,
        "strategy": case.get("strategy", "standard"),
        "metadata": case.get("metadata") or {},
        "entities": entities,
        "evidence": evidence,
        "evidence_ledger": ledger,
        "facts": facts,
        "relationships": relationships,
        "summary": "",
        "report_markdown": "",
        "hypotheses": [],
        "hypothesis_analysis": {},
        "intelligence_memory": {"collection_gaps": [], "directed_collection": []},
    }


def _entity(entity_type: str, value: str, source_tool: str, confidence: float) -> dict:
    return {
        "type": entity_type,
        "value": value,
        "source_tool": source_tool,
        "confidence": confidence,
    }


def _report_sections(report: str) -> list[str]:
    sections = []
    for line in report.splitlines():
        if line.startswith("## "):
            title = line.removeprefix("## ").strip()
            if title.startswith("PIR"):
                sections.append("PIR")
            elif title.startswith("I&W"):
                sections.append("I&W")
            else:
                sections.append(title)
    return sections


def main() -> int:
    result = run_regression_cases()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
