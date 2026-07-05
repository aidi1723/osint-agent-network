# Intelligence Core v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PIR/EEI requirements, fact promotion stages, a cross-verification matrix, and Core v3 report sections so investigation outputs become stricter intelligence products.

**Architecture:** Store PIR/EEI in existing investigation metadata for low-risk migration, add one additive `facts.promotion_stage` column, and derive the cross-verification matrix from stored entities, evidence, evidence ledger, facts, and relationships. Backend core modules produce deterministic analysis objects; frontend panels render those objects compactly under the existing HCS dashboard style.

**Tech Stack:** Python 3.11 `unittest`, SQLite, existing `http.server` API, React + TypeScript + Vite, source-owned CSS/components.

---

## File Map

- Create `backend/app/core/intelligence_requirements.py`: default PIR/EEI generation, normalization, and coverage updates.
- Create `backend/app/core/cross_verification.py`: source-family classification and deterministic matrix generation.
- Modify `backend/app/core/fact_pool.py`: add promotion-stage constants, dataclass field, validation, and helpers.
- Modify `backend/app/services/store.py`: persist `promotion_stage`, migrate legacy rows, return `intelligence_requirements` and `cross_verification_matrix`.
- Modify `backend/app/core/quality.py`: add Core v3 quality checks and report sections.
- Modify `backend/app/services/role_agents.py`: ensure generated reports use Core v3 detail fields.
- Create/modify backend tests in `backend/tests/test_intelligence_requirements.py`, `backend/tests/test_cross_verification.py`, `backend/tests/test_intelligence_core_v3.py`, and existing store/quality tests.
- Modify `frontend/src/types.ts`: add Core v3 response types.
- Create `frontend/src/core-v3.ts`: UI helper functions for labels, row ordering, and stage counts.
- Create `frontend/src/components/IntelligenceRequirementsPanel.tsx`: PIR/EEI compact panel.
- Create `frontend/src/components/CrossVerificationMatrixPanel.tsx`: compact matrix table.
- Create `frontend/src/components/FactPromotionPanel.tsx`: promotion counts and accepted/candidate facts.
- Modify `frontend/src/main.tsx`: add creation inputs and detail panels.
- Modify `frontend/src/styles.css`: compact table/chip styling under existing HCS design.
- Create `frontend/scripts/test-core-v3.ts`: frontend helper tests.
- Modify `scripts/verify.sh`: include new frontend helper test if not globbed manually.
- Modify docs: `README.md`, `docs/PROJECT_PACKAGE.md`, and `docs/N100_DEPLOYMENT_RUNBOOK.md` to mention Core v3 after implementation.

---

### Task 1: Intelligence Requirements Core

**Files:**
- Create: `backend/app/core/intelligence_requirements.py`
- Test: `backend/tests/test_intelligence_requirements.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_intelligence_requirements.py`:

```python
import unittest

from app.core.intelligence_requirements import (
    DEFAULT_EEI_STATUS,
    DEFAULT_PIR_STATUS,
    build_intelligence_requirements,
    requirement_coverage,
)


class IntelligenceRequirementsTests(unittest.TestCase):
    def test_company_defaults_include_identity_purchase_contact_and_risk(self):
        req = build_intelligence_requirements("company", "Family Hospitality LLC", "standard", {})

        pir_ids = {item["id"] for item in req["pirs"]}
        eei_ids = {item["id"] for item in req["eeis"]}

        self.assertIn("pir_identity", pir_ids)
        self.assertIn("pir_purchase_capacity", pir_ids)
        self.assertIn("pir_contact_confidence", pir_ids)
        self.assertIn("pir_risk", pir_ids)
        self.assertIn("eei_company_identity", eei_ids)
        self.assertIn("eei_official_website", eei_ids)
        self.assertIn("eei_contact_email", eei_ids)
        self.assertEqual(req["pirs"][0]["status"], DEFAULT_PIR_STATUS)
        self.assertEqual(req["eeis"][0]["status"], DEFAULT_EEI_STATUS)

    def test_sparse_lead_defaults_include_identity_match_pir(self):
        req = build_intelligence_requirements(
            "sparse_lead",
            "Long Way / in19034126503jgqn",
            "quick",
            {"country_region": "IN", "platform": "Alibaba"},
        )

        questions = " ".join(item["question"] for item in req["pirs"])
        eei_ids = {item["id"] for item in req["eeis"]}

        self.assertIn("same buyer", questions.lower())
        self.assertIn("eei_platform_anchor", eei_ids)
        self.assertIn("eei_identity_match", eei_ids)

    def test_normalizes_operator_supplied_requirements(self):
        req = build_intelligence_requirements(
            "domain",
            "example.com",
            "deep",
            {
                "intelligence_requirements": {
                    "decision_context": "qualify supplier",
                    "confidence_requirement": "strict",
                    "pirs": [{"question": "Is this domain official?", "priority": "high"}],
                    "eeis": [{"label": "WHOIS or official page", "field_key": "official_website"}],
                }
            },
        )

        self.assertEqual(req["decision_context"], "qualify supplier")
        self.assertEqual(req["confidence_requirement"], "strict")
        self.assertEqual(req["pirs"][0]["id"], "pir_custom_1")
        self.assertEqual(req["eeis"][0]["id"], "eei_custom_1")
        self.assertTrue(req["eeis"][0]["required"])

    def test_requirement_coverage_counts_answered_and_confirmed_items(self):
        req = build_intelligence_requirements("email", "buyer@example.com", "standard", {})
        req["pirs"][0]["status"] = "ANSWERED"
        req["eeis"][0]["status"] = "CONFIRMED"

        coverage = requirement_coverage(req)

        self.assertGreater(coverage["pir_answered"], 0)
        self.assertGreater(coverage["eei_confirmed"], 0)
        self.assertGreater(coverage["required_eei_total"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_requirements
```

Expected: FAIL because `app.core.intelligence_requirements` does not exist.

- [ ] **Step 3: Implement requirements core**

Create `backend/app/core/intelligence_requirements.py`:

```python
from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_PIR_STATUS = "OPEN"
DEFAULT_EEI_STATUS = "MISSING"
PIR_STATUSES = {"OPEN", "PARTIAL", "ANSWERED", "BLOCKED", "NEEDS_REVIEW"}
EEI_STATUSES = {"MISSING", "CANDIDATE", "SUPPORTED", "CONFIRMED", "CONFLICTED"}


BASE_PIRS = [
    ("pir_identity", "Is the target organization or account identity real and operational?", "high"),
    ("pir_purchase_capacity", "Does the target show credible purchase capacity or purchase intent?", "high"),
    ("pir_contact_confidence", "Are the contact channels tied to the target by public evidence?", "high"),
    ("pir_decision_maker", "Is the decision-maker candidate supported by public evidence?", "medium"),
    ("pir_risk", "Are there risk, contradiction, fraud, litigation, reputation, or sanctions signals?", "high"),
]

SPARSE_LEAD_EXTRA_PIRS = [
    ("pir_identity_match", "Do public records belong to the same buyer represented by the platform lead?", "high"),
]

BASE_EEIS = [
    ("eei_company_identity", "Legal or operating company name", "company_identity", True),
    ("eei_official_website", "Official website or domain", "official_website", True),
    ("eei_contact_email", "Public contact email", "contact_email", False),
    ("eei_contact_phone", "Public phone or WhatsApp", "contact_phone", False),
    ("eei_operation_location", "Address or operating region", "operation_location", True),
    ("eei_registration", "Registration identifier or registry profile", "registration", False),
    ("eei_business_scope", "Business scope and product fit", "business_scope", True),
    ("eei_decision_maker", "Decision-maker candidate", "decision_maker", False),
    ("eei_purchase_signal", "Import, project, RFQ, or purchase-intent signal", "purchase_intent", False),
    ("eei_risk_signal", "Risk or contradiction signal", "risk_signal", False),
]

SPARSE_LEAD_EXTRA_EEIS = [
    ("eei_platform_anchor", "Platform anchor fields", "platform_anchor", True),
    ("eei_identity_match", "Public-record to buyer identity match", "identity_match", True),
]

DOMAIN_EEIS = [
    ("eei_official_website", "Official website or domain", "official_website", True),
    ("eei_contact_email", "Public contact email", "contact_email", False),
    ("eei_business_scope", "Business scope and product fit", "business_scope", False),
    ("eei_risk_signal", "Risk or contradiction signal", "risk_signal", False),
]

EMAIL_EEIS = [
    ("eei_contact_email", "Email ownership and context", "contact_email", True),
    ("eei_company_identity", "Linked organization identity", "company_identity", False),
    ("eei_official_website", "Linked official domain", "official_website", False),
    ("eei_risk_signal", "Risk or contradiction signal", "risk_signal", False),
]


def build_intelligence_requirements(
    seed_type: str,
    seed_value: str,
    strategy: str,
    metadata: dict[str, Any] | None,
) -> dict:
    metadata = metadata or {}
    supplied = metadata.get("intelligence_requirements")
    if isinstance(supplied, dict):
        return normalize_intelligence_requirements(supplied)

    pirs = [_pir(*item) for item in BASE_PIRS]
    if seed_type == "sparse_lead":
        pirs.extend(_pir(*item) for item in SPARSE_LEAD_EXTRA_PIRS)

    if seed_type == "domain":
        eei_source = DOMAIN_EEIS
    elif seed_type == "email":
        eei_source = EMAIL_EEIS
    else:
        eei_source = BASE_EEIS
    eeis = [_eei(*item) for item in eei_source]
    if seed_type == "sparse_lead":
        eeis.extend(_eei(*item) for item in SPARSE_LEAD_EXTRA_EEIS)

    return {
        "decision_context": _default_decision_context(seed_type, seed_value),
        "confidence_requirement": _confidence_requirement(strategy),
        "pirs": pirs,
        "eeis": eeis,
    }


def normalize_intelligence_requirements(raw: dict[str, Any]) -> dict:
    pirs = []
    for index, item in enumerate(raw.get("pirs") or [], start=1):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        status = str(item.get("status") or DEFAULT_PIR_STATUS)
        pirs.append(
            {
                "id": str(item.get("id") or f"pir_custom_{index}"),
                "question": question,
                "priority": str(item.get("priority") or "medium"),
                "status": status if status in PIR_STATUSES else DEFAULT_PIR_STATUS,
                "answer": str(item.get("answer") or ""),
                "confidence": _bounded_float(item.get("confidence"), 0.0),
                "linked_fact_ids": _string_list(item.get("linked_fact_ids")),
                "remaining_gaps": _string_list(item.get("remaining_gaps")),
            }
        )
    eeis = []
    for index, item in enumerate(raw.get("eeis") or [], start=1):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        field_key = str(item.get("field_key") or "").strip()
        if not label or not field_key:
            continue
        status = str(item.get("status") or DEFAULT_EEI_STATUS)
        eeis.append(
            {
                "id": str(item.get("id") or f"eei_custom_{index}"),
                "label": label,
                "field_key": field_key,
                "required": bool(item.get("required", True)),
                "status": status if status in EEI_STATUSES else DEFAULT_EEI_STATUS,
                "linked_entity_values": _string_list(item.get("linked_entity_values")),
                "linked_fact_ids": _string_list(item.get("linked_fact_ids")),
            }
        )
    return {
        "decision_context": str(raw.get("decision_context") or ""),
        "confidence_requirement": str(raw.get("confidence_requirement") or "standard"),
        "pirs": pirs,
        "eeis": eeis,
    }


def apply_requirement_updates(requirements: dict, matrix: list[dict], facts: list[dict]) -> dict:
    updated = deepcopy(requirements)
    by_field = {row.get("field_key"): row for row in matrix}
    accepted_fact_ids = {
        str(fact.get("id"))
        for fact in facts
        if fact.get("promotion_stage") == "ACCEPTED_FACT" or fact.get("status") in {"CONFIRMED", "LIKELY"}
    }
    for eei in updated.get("eeis", []):
        row = by_field.get(eei.get("field_key"))
        if not row:
            continue
        status = str(row.get("status") or "")
        if status in {"CONFIRMED", "LIKELY"}:
            eei["status"] = "CONFIRMED"
        elif status == "SUPPORTED":
            eei["status"] = "SUPPORTED"
        elif status == "CONFLICTED":
            eei["status"] = "CONFLICTED"
        elif row.get("candidate_value"):
            eei["status"] = "CANDIDATE"
        eei["linked_entity_values"] = [str(row.get("candidate_value"))] if row.get("candidate_value") else []
        eei["linked_fact_ids"] = list(row.get("linked_fact_ids") or [])

    for pir in updated.get("pirs", []):
        if accepted_fact_ids:
            pir["status"] = "PARTIAL"
            pir["linked_fact_ids"] = sorted(accepted_fact_ids)[:6]
        if pir.get("id") == "pir_identity" and _field_confirmed(updated, "company_identity"):
            pir["status"] = "ANSWERED"
            pir["answer"] = "Identity is supported by cross-verified public-source evidence."
            pir["confidence"] = max(float(pir.get("confidence") or 0), 0.75)
        if pir.get("id") == "pir_contact_confidence" and (
            _field_confirmed(updated, "contact_email") or _field_confirmed(updated, "contact_phone")
        ):
            pir["status"] = "ANSWERED"
            pir["answer"] = "At least one contact channel is supported by public-source evidence."
            pir["confidence"] = max(float(pir.get("confidence") or 0), 0.7)
    return updated


def requirement_coverage(requirements: dict) -> dict:
    pirs = requirements.get("pirs") or []
    eeis = requirements.get("eeis") or []
    required = [item for item in eeis if item.get("required")]
    return {
        "pir_total": len(pirs),
        "pir_answered": sum(1 for item in pirs if item.get("status") == "ANSWERED"),
        "pir_partial": sum(1 for item in pirs if item.get("status") == "PARTIAL"),
        "required_eei_total": len(required),
        "eei_confirmed": sum(1 for item in eeis if item.get("status") == "CONFIRMED"),
        "required_eei_confirmed": sum(1 for item in required if item.get("status") == "CONFIRMED"),
    }


def _pir(id: str, question: str, priority: str) -> dict:
    return {
        "id": id,
        "question": question,
        "priority": priority,
        "status": DEFAULT_PIR_STATUS,
        "answer": "",
        "confidence": 0.0,
        "linked_fact_ids": [],
        "remaining_gaps": [],
    }


def _eei(id: str, label: str, field_key: str, required: bool) -> dict:
    return {
        "id": id,
        "label": label,
        "field_key": field_key,
        "required": required,
        "status": DEFAULT_EEI_STATUS,
        "linked_entity_values": [],
        "linked_fact_ids": [],
    }


def _default_decision_context(seed_type: str, seed_value: str) -> str:
    if seed_type == "sparse_lead":
        return "Qualify sparse platform buyer lead."
    if seed_type == "company":
        return "Assess public-source company identity, contactability, risk, and purchase fit."
    return f"Assess public-source intelligence for {seed_type}: {seed_value}."


def _confidence_requirement(strategy: str) -> str:
    if strategy in {"deep", "maximum"}:
        return "strict"
    if strategy == "quick":
        return "quick"
    return "standard"


def _bounded_float(value: Any, default: float) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _field_confirmed(requirements: dict, field_key: str) -> bool:
    return any(
        item.get("field_key") == field_key and item.get("status") == "CONFIRMED"
        for item in requirements.get("eeis", [])
    )
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_requirements
```

Expected: OK.

---

### Task 2: Fact Promotion Stage And SQLite Migration

**Files:**
- Modify: `backend/app/core/fact_pool.py`
- Modify: `backend/app/services/store.py`
- Test: `backend/tests/test_intelligence_core_v3.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_intelligence_core_v3.py`:

```python
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.fact_pool import FactRecord, validate_fact_record
from app.services.store import SQLiteStore


class IntelligenceCoreV3Tests(unittest.TestCase):
    def test_fact_record_accepts_and_validates_promotion_stage(self):
        fact = FactRecord(
            id="fact-1",
            investigation_id="inv-1",
            statement="Example LLC operates example.com.",
            subject="Example LLC",
            predicate="operates",
            object="example.com",
            status="CONFIRMED",
            promotion_stage="ACCEPTED_FACT",
            confidence=0.9,
            admiralty_code="A-2",
            evidence_ids=["ev-1"],
            observed_at="2026-05-22T00:00:00+00:00",
            valid_from="2026-05-22T00:00:00+00:00",
        )

        validate_fact_record(fact)

    def test_invalid_promotion_stage_is_rejected(self):
        fact = FactRecord(
            id="fact-1",
            investigation_id="inv-1",
            statement="Example LLC operates example.com.",
            subject="Example LLC",
            predicate="operates",
            object="example.com",
            status="CONFIRMED",
            promotion_stage="FINAL_TRUTH",
            confidence=0.9,
            admiralty_code="A-2",
            evidence_ids=["ev-1"],
            observed_at="2026-05-22T00:00:00+00:00",
            valid_from="2026-05-22T00:00:00+00:00",
        )

        with self.assertRaises(ValueError):
            validate_fact_record(fact)

    def test_store_migrates_legacy_facts_to_promotion_stage(self):
        with TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "legacy.sqlite")
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE investigations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    seed_type TEXT NOT NULL,
                    seed_value TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    max_depth INTEGER NOT NULL,
                    max_jobs INTEGER NOT NULL,
                    max_entities INTEGER NOT NULL,
                    claimed_by_agent_id TEXT,
                    claimed_by_agent_name TEXT,
                    updated_at TEXT,
                    summary TEXT NOT NULL DEFAULT '',
                    report_markdown TEXT NOT NULL DEFAULT '',
                    confidence REAL,
                    risk_report_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE facts (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_value TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    admiralty_code TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    supersedes_fact_id TEXT
                );
                INSERT INTO investigations (
                    id, name, seed_type, seed_value, strategy, status, created_at,
                    max_depth, max_jobs, max_entities, updated_at
                ) VALUES (
                    'inv-legacy', 'Legacy', 'company', 'Legacy LLC',
                    'standard', 'OPEN', '2026-05-21T00:00:00+00:00',
                    2, 10, 25, '2026-05-21T00:00:00+00:00'
                );
                INSERT INTO facts (
                    id, investigation_id, statement, subject, predicate, object_value,
                    status, confidence, admiralty_code, evidence_ids_json, observed_at, valid_from
                ) VALUES (
                    'fact-1', 'inv-legacy', 'Legacy LLC operates publicly.', 'Legacy LLC',
                    'operates', 'publicly', 'CONFIRMED', 0.9, 'A-2', '["ev-1"]',
                    '2026-05-21T00:00:00+00:00', '2026-05-21T00:00:00+00:00'
                );
                """
            )
            conn.commit()
            conn.close()

            store = SQLiteStore(db_path)
            detail = store.get_investigation("inv-legacy")

        self.assertEqual(detail["facts"][0]["promotion_stage"], "ACCEPTED_FACT")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_core_v3
```

Expected: FAIL because `FactRecord` has no `promotion_stage`.

- [ ] **Step 3: Update `fact_pool.py`**

Modify `backend/app/core/fact_pool.py`:

```python
FACT_STATUSES = {"CONFIRMED", "LIKELY", "CONTRADICTED", "RETIRED", "NEEDS_REVIEW"}
FACT_PROMOTION_STAGES = {
    "RAW_OBSERVATION",
    "CANDIDATE_FACT",
    "ASSESSED_FACT",
    "ACCEPTED_FACT",
    "REJECTED_FACT",
}


@dataclass(frozen=True)
class FactRecord:
    id: str
    investigation_id: str
    statement: str
    subject: str
    predicate: str
    object: str
    status: str
    confidence: float
    admiralty_code: str
    evidence_ids: list[str]
    observed_at: str
    valid_from: str
    promotion_stage: str = "CANDIDATE_FACT"
    valid_to: str | None = None
    supersedes_fact_id: str | None = None
```

Inside `validate_fact_record()` add:

```python
    if fact.promotion_stage not in FACT_PROMOTION_STAGES:
        raise ValueError(f"invalid fact promotion_stage: {fact.promotion_stage}")
    if fact.promotion_stage == "ACCEPTED_FACT" and fact.status not in {"CONFIRMED", "LIKELY"}:
        raise ValueError("accepted facts must be confirmed or likely")
```

Add helper:

```python
def default_promotion_stage_for_status(status: str) -> str:
    if status == "CONFIRMED":
        return "ACCEPTED_FACT"
    if status == "LIKELY":
        return "ASSESSED_FACT"
    if status in {"CONTRADICTED", "RETIRED"}:
        return "REJECTED_FACT"
    return "CANDIDATE_FACT"
```

- [ ] **Step 4: Update SQLite persistence**

Modify imports in `backend/app/services/store.py`:

```python
from app.core.fact_pool import FactRecord, default_promotion_stage_for_status, validate_fact_record
```

Update all `INSERT INTO facts` statements to include `promotion_stage` after `status`.

For `add_fact()`, persist `fact.promotion_stage`.

For import paths where `fact` is a dict, use:

```python
fact.get("promotion_stage") or default_promotion_stage_for_status(fact.get("status", "NEEDS_REVIEW"))
```

In `_init_schema()`, add the column to the `CREATE TABLE facts` statement:

```sql
promotion_stage TEXT NOT NULL DEFAULT 'CANDIDATE_FACT',
```

After fact table column inspection, add migration:

```python
            fact_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(facts)").fetchall()
            }
            if "promotion_stage" not in fact_columns:
                conn.execute(
                    "ALTER TABLE facts ADD COLUMN promotion_stage TEXT NOT NULL DEFAULT 'CANDIDATE_FACT'"
                )
                conn.execute(
                    """
                    UPDATE facts
                    SET promotion_stage = CASE
                        WHEN status = 'CONFIRMED' THEN 'ACCEPTED_FACT'
                        WHEN status = 'LIKELY' THEN 'ASSESSED_FACT'
                        WHEN status IN ('CONTRADICTED', 'RETIRED') THEN 'REJECTED_FACT'
                        ELSE 'CANDIDATE_FACT'
                    END
                    """
                )
```

Update `_fact_from_row()` to read:

```python
promotion_stage = row["promotion_stage"] if "promotion_stage" in row.keys() else default_promotion_stage_for_status(row["status"])
```

Update `_fact_as_dict()` to include:

```python
"promotion_stage": fact.promotion_stage,
```

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_core_v3 backend.tests.test_intelligence_core_v2 backend.tests.test_agent_protocol
```

Expected: OK.

---

### Task 3: Cross-Verification Matrix Core

**Files:**
- Create: `backend/app/core/cross_verification.py`
- Test: `backend/tests/test_cross_verification.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_cross_verification.py`:

```python
import unittest

from app.core.cross_verification import build_cross_verification_matrix, classify_source_family


class CrossVerificationTests(unittest.TestCase):
    def test_classifies_source_family(self):
        self.assertEqual(classify_source_family("official_website", "official_web"), "official")
        self.assertEqual(classify_source_family("registry", "state_registry"), "registry")
        self.assertEqual(classify_source_family("news", "company_news"), "news")
        self.assertEqual(classify_source_family("tool", "theHarvester"), "tool")

    def test_confirms_identity_with_official_and_registry_sources(self):
        detail = {
            "entities": [
                {"id": "e1", "type": "company", "value": "Example LLC", "source_tool": "official_web", "confidence": 0.8},
                {"id": "e2", "type": "company", "value": "Example LLC", "source_tool": "state_registry", "confidence": 0.9},
            ],
            "evidence_ledger": [
                {"id": "ev1", "source_type": "official_website", "source_tool": "official_web", "source_url": "https://example.com", "admiralty_code": "A-2", "snippet": "Example LLC"},
                {"id": "ev2", "source_type": "registry", "source_tool": "state_registry", "source_url": "https://registry.example", "admiralty_code": "A-2", "snippet": "Example LLC"},
            ],
            "facts": [
                {"id": "f1", "subject": "Example LLC", "predicate": "identity", "object": "Example LLC", "status": "CONFIRMED", "promotion_stage": "ACCEPTED_FACT", "confidence": 0.9, "evidence_ids": ["ev1", "ev2"]},
            ],
            "evidence": [],
            "relationships": [],
        }

        rows = build_cross_verification_matrix(detail)
        identity = next(row for row in rows if row["field_key"] == "company_identity")

        self.assertEqual(identity["status"], "CONFIRMED")
        self.assertEqual(identity["candidate_value"], "Example LLC")
        self.assertEqual(identity["independent_source_count"], 2)
        self.assertIn("official", identity["supporting_sources"])
        self.assertIn("registry", identity["supporting_sources"])

    def test_flags_conflicting_contact_values(self):
        detail = {
            "entities": [
                {"id": "e1", "type": "email", "value": "sales@example.com", "source_tool": "official_web", "confidence": 0.8},
                {"id": "e2", "type": "email", "value": "info@other.example", "source_tool": "directory_site", "confidence": 0.6},
            ],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "relationships": [],
        }

        rows = build_cross_verification_matrix(detail)
        email = next(row for row in rows if row["field_key"] == "contact_email")

        self.assertEqual(email["status"], "CONFLICTED")
        self.assertIn("directory", email["contradicting_sources"])
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_cross_verification
```

Expected: FAIL because `app.core.cross_verification` does not exist.

- [ ] **Step 3: Implement matrix builder**

Create `backend/app/core/cross_verification.py`:

```python
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


FIELD_DEFINITIONS = [
    ("company_identity", "企业名称", {"company", "organization"}),
    ("official_website", "官网/域名", {"domain", "website", "official_website", "url"}),
    ("contact_email", "企业邮箱", {"email"}),
    ("contact_phone", "电话/WhatsApp", {"phone", "whatsapp"}),
    ("operation_location", "地址/经营区域", {"address", "declared_location", "likely_activity_region", "country_region"}),
    ("registration", "注册信息", {"registration", "registration_id", "tax_id", "nit", "rues"}),
    ("business_scope", "主营业务/产品匹配", {"business_scope", "product_scope", "purchase_category"}),
    ("decision_maker", "决策人候选", {"identity", "decision_maker", "person", "profile_url"}),
    ("purchase_intent", "采购意图", {"purchase_intent", "buying_signal", "rfq"}),
    ("risk_signal", "风险信号", {"risk_signal", "negative_signal", "litigation", "sanction"}),
]

SOURCE_HINTS = {
    "official": ("official", "website", "contact_page", "operator_seed"),
    "registry": ("registry", "rues", "nit", "state", "government", "gov"),
    "news": ("news", "gnews", "rss", "newspaper"),
    "directory": ("directory", "dnb", "bbb", "empresite", "einforma", "map"),
    "social": ("social", "linkedin", "facebook", "twitter", "instagram", "profile"),
    "tool": ("sherlock", "maigret", "theharvester", "amass", "spiderfoot", "ghunt", "phoneinfoga", "recon"),
    "operator": ("operator", "manual", "crm", "alibaba", "screenshot"),
}


def classify_source_family(source_type: str | None, source_tool: str | None) -> str:
    text = f"{source_type or ''} {source_tool or ''}".lower()
    for family, hints in SOURCE_HINTS.items():
        if any(hint in text for hint in hints):
            return family
    return "unknown"


def build_cross_verification_matrix(detail: dict[str, Any]) -> list[dict[str, Any]]:
    entities = detail.get("entities") or []
    evidence = detail.get("evidence") or []
    ledger = detail.get("evidence_ledger") or []
    facts = detail.get("facts") or []
    ledger_by_id = {item.get("id"): item for item in ledger}
    source_families_by_value = _source_families_by_value(entities, evidence, ledger)
    linked_evidence_by_value = _linked_evidence_by_value(evidence, ledger)
    fact_ids_by_value = _fact_ids_by_value(facts)

    rows = []
    for field_key, label, entity_types in FIELD_DEFINITIONS:
        candidates = [
            item for item in entities
            if str(item.get("type") or "") in entity_types and str(item.get("value") or "").strip()
        ]
        facts_for_field = [
            item for item in facts
            if _fact_matches_field(item, field_key, entity_types)
        ]
        values = [str(item.get("value")) for item in candidates]
        values.extend(str(item.get("object") or item.get("object_value")) for item in facts_for_field if item.get("object") or item.get("object_value"))
        candidate_value = _best_value(values, candidates, facts_for_field)
        support = sorted(source_families_by_value.get(candidate_value, set()))
        linked_evidence_ids = sorted(linked_evidence_by_value.get(candidate_value, set()))
        linked_fact_ids = sorted(fact_ids_by_value.get(candidate_value, set()))
        best_admiralty = _best_admiralty(linked_evidence_ids, ledger_by_id)
        contradiction_sources = _contradiction_sources(values, candidate_value, candidates)
        status = _row_status(candidate_value, support, contradiction_sources, facts_for_field, best_admiralty)
        confidence = _row_confidence(status, support, best_admiralty)
        rows.append(
            {
                "field_key": field_key,
                "label": label,
                "candidate_value": candidate_value,
                "supporting_sources": support,
                "contradicting_sources": sorted(contradiction_sources),
                "source_count": len(support),
                "independent_source_count": len(set(support)),
                "best_admiralty_code": best_admiralty,
                "status": status,
                "confidence": confidence,
                "linked_evidence_ids": linked_evidence_ids,
                "linked_fact_ids": linked_fact_ids,
                "rationale": _rationale(label, candidate_value, support, contradiction_sources, status),
            }
        )
    return rows


def _source_families_by_value(entities: list[dict], evidence: list[dict], ledger: list[dict]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for entity in entities:
        value = str(entity.get("value") or "")
        if value:
            result[value].add(classify_source_family("", entity.get("source_tool")))
    for item in evidence:
        value = str(item.get("entity_value") or "")
        if value:
            result[value].add(classify_source_family(item.get("evidence_kind"), item.get("source_tool")))
    for item in ledger:
        snippet = str(item.get("snippet") or "")
        family = classify_source_family(item.get("source_type"), item.get("source_tool"))
        for value in list(result.keys()):
            if value and value.lower() in snippet.lower():
                result[value].add(family)
    return result


def _linked_evidence_by_value(evidence: list[dict], ledger: list[dict]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for item in evidence:
        value = str(item.get("entity_value") or "")
        if value and item.get("id"):
            result[value].add(str(item["id"]))
    for item in ledger:
        snippet = str(item.get("snippet") or "")
        for value in list(result.keys()):
            if value and value.lower() in snippet.lower() and item.get("id"):
                result[value].add(str(item["id"]))
    return result


def _fact_ids_by_value(facts: list[dict]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        value = str(fact.get("object") or fact.get("object_value") or "")
        if value and fact.get("id"):
            result[value].add(str(fact["id"]))
    return result


def _fact_matches_field(fact: dict, field_key: str, entity_types: set[str]) -> bool:
    text = f"{fact.get('predicate', '')} {fact.get('statement', '')}".lower()
    if field_key in text:
        return True
    return any(kind in text for kind in entity_types)


def _best_value(values: list[str], candidates: list[dict], facts: list[dict]) -> str:
    clean = [value for value in values if value and value != "None"]
    if not clean:
        return ""
    counts = Counter(clean)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _best_admiralty(evidence_ids: list[str], ledger_by_id: dict[str, dict]) -> str:
    codes = [str(ledger_by_id[item].get("admiralty_code") or "") for item in evidence_ids if item in ledger_by_id]
    codes = [code for code in codes if code]
    if not codes:
        return ""
    return sorted(codes)[0]


def _contradiction_sources(values: list[str], candidate_value: str, candidates: list[dict]) -> set[str]:
    distinct = {value for value in values if value and value != candidate_value}
    if not candidate_value or not distinct:
        return set()
    return {
        classify_source_family("", item.get("source_tool"))
        for item in candidates
        if str(item.get("value") or "") in distinct
    }


def _row_status(candidate_value: str, support: list[str], contradictions: set[str], facts: list[dict], admiralty: str) -> str:
    if contradictions:
        return "CONFLICTED"
    if any(item.get("status") == "CONFIRMED" or item.get("promotion_stage") == "ACCEPTED_FACT" for item in facts):
        return "CONFIRMED"
    if not candidate_value:
        return "MISSING"
    if len(set(support)) >= 2:
        return "LIKELY"
    if support and ("official" in support or "registry" in support or admiralty.startswith("A-")):
        return "SUPPORTED"
    if support:
        return "CANDIDATE"
    return "NEEDS_REVIEW"


def _row_confidence(status: str, support: list[str], admiralty: str) -> float:
    base = {
        "CONFIRMED": 0.9,
        "LIKELY": 0.78,
        "SUPPORTED": 0.65,
        "CANDIDATE": 0.45,
        "NEEDS_REVIEW": 0.3,
        "CONFLICTED": 0.2,
        "MISSING": 0.0,
    }[status]
    if admiralty.startswith("A-"):
        base += 0.05
    if len(set(support)) >= 3:
        base += 0.05
    return min(1.0, round(base, 2))


def _rationale(label: str, value: str, support: list[str], contradictions: set[str], status: str) -> str:
    if status == "MISSING":
        return f"{label} has not been collected."
    if contradictions:
        return f"{label} has conflicting candidate values across {', '.join(sorted(contradictions))} sources."
    if support:
        return f"{label} is supported by {', '.join(support)} source family evidence."
    return f"{label} has a candidate value but no strong independent support yet."
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_cross_verification
```

Expected: OK.

---

### Task 4: Store Integration For Requirements And Matrix

**Files:**
- Modify: `backend/app/services/store.py`
- Test: `backend/tests/test_intelligence_core_v3.py`

- [ ] **Step 1: Add failing store integration test**

Append to `IntelligenceCoreV3Tests` in `backend/tests/test_intelligence_core_v3.py`:

```python
    def test_investigation_detail_includes_requirements_and_matrix(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            inv = store.create_investigation("Example", "company", "Example LLC", "standard")
            store.add_entity(inv.id, "company", "Example LLC", "official_web", 0.9)
            store.add_entity(inv.id, "domain", "example.com", "official_web", 0.9)
            detail = store.get_investigation(inv.id)

        self.assertIn("intelligence_requirements", detail)
        self.assertIn("cross_verification_matrix", detail)
        self.assertTrue(detail["intelligence_requirements"]["pirs"])
        identity = next(row for row in detail["cross_verification_matrix"] if row["field_key"] == "company_identity")
        self.assertEqual(identity["candidate_value"], "Example LLC")
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_core_v3
```

Expected: FAIL because detail lacks `intelligence_requirements` and `cross_verification_matrix`.

- [ ] **Step 3: Add imports**

In `backend/app/services/store.py` add:

```python
from app.core.cross_verification import build_cross_verification_matrix
from app.core.intelligence_requirements import apply_requirement_updates, build_intelligence_requirements
```

- [ ] **Step 4: Store requirements on create**

In `create_investigation()`, before constructing `Investigation`, compute:

```python
        metadata = metadata or {}
        requirements = build_intelligence_requirements(seed_type, seed_value, strategy.name, metadata)
        metadata = {**metadata, "intelligence_requirements": requirements}
```

Then pass that metadata to `Investigation`.

- [ ] **Step 5: Add derived fields in detail builder**

In both in-memory and SQLite `get_investigation()` detail assembly, after facts/evidence/relationships are present and before returning:

```python
        matrix = build_cross_verification_matrix(data)
        requirements = build_intelligence_requirements(
            data["seed_type"],
            data["seed_value"],
            data["strategy"],
            data.get("metadata") or {},
        )
        requirements = apply_requirement_updates(requirements, matrix, data.get("facts") or [])
        data["intelligence_requirements"] = requirements
        data["cross_verification_matrix"] = matrix
```

Ensure this runs before `quality_assessment` and report rendering when possible.

- [ ] **Step 6: Run integration tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_core_v3 backend.tests.test_store_dedup backend.tests.test_worker
```

Expected: OK.

---

### Task 5: Quality Gate And Report Core v3 Sections

**Files:**
- Modify: `backend/app/core/quality.py`
- Test: `backend/tests/test_quality_gate.py`

- [ ] **Step 1: Add failing report and quality tests**

Append to `backend/tests/test_quality_gate.py`:

```python
    def test_quality_assessment_includes_core_v3_checks(self):
        detail = {
            "entities": [{"type": "company", "value": "Example LLC"}],
            "evidence_ledger": [{"id": "ev-1", "source_url": "https://example.com", "admiralty_code": "A-2"}],
            "facts": [{"id": "fact-1", "status": "CONFIRMED", "promotion_stage": "ACCEPTED_FACT"}],
            "relationships": [],
            "hypotheses": [],
            "report_markdown": "# BLUF\nExample.",
            "intelligence_requirements": {
                "pirs": [{"id": "pir_identity", "status": "ANSWERED"}],
                "eeis": [{"id": "eei_company_identity", "field_key": "company_identity", "required": True, "status": "CONFIRMED"}],
            },
            "cross_verification_matrix": [
                {"field_key": "company_identity", "status": "CONFIRMED", "candidate_value": "Example LLC"}
            ],
        }

        assessment = build_quality_assessment(detail)
        keys = {item["key"] for item in assessment["checks"]}

        self.assertIn("pir_requirements", keys)
        self.assertIn("cross_verification", keys)
        self.assertIn("accepted_facts", keys)

    def test_structured_report_includes_core_v3_sections(self):
        detail = {
            "name": "Example report",
            "seed_value": "Example LLC",
            "summary": "",
            "entities": [],
            "facts": [{"statement": "Example LLC operates example.com.", "status": "CONFIRMED", "promotion_stage": "ACCEPTED_FACT", "confidence": 0.9, "admiralty_code": "A-2"}],
            "evidence_ledger": [{"source_url": "https://example.com", "admiralty_code": "A-2", "snippet": "Example LLC"}],
            "hypothesis_analysis": {"most_likely_hypothesis": "alpha_real_buyer", "confidence_language": "很有可能"},
            "intelligence_requirements": {
                "pirs": [{"question": "Is identity real?", "status": "ANSWERED", "answer": "Identity is supported.", "confidence": 0.8}],
                "eeis": [{"label": "Company identity", "required": True, "status": "CONFIRMED"}],
            },
            "cross_verification_matrix": [
                {"label": "企业名称", "candidate_value": "Example LLC", "status": "CONFIRMED", "rationale": "Official and registry support."}
            ],
            "intelligence_memory": {"collection_gaps": [], "directed_collection": []},
        }

        report = render_structured_report(detail)

        self.assertIn("## PIR 逐项回答", report)
        self.assertIn("## 交叉验证矩阵摘要", report)
        self.assertIn("## I&W 征候", report)
        self.assertIn("## 证据附录", report)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_quality_gate
```

Expected: FAIL because Core v3 checks/sections are missing.

- [ ] **Step 3: Extend `FIELD_RULES`**

In `backend/app/core/quality.py`, add:

```python
    ("pir_requirements", "PIR/EEI 情报需求", (), 8),
    ("cross_verification", "交叉验证矩阵", (), 10),
    ("accepted_facts", "已采纳事实", (), 10),
```

Add these keys to `COMPLETION_REQUIRED_KEYS`:

```python
COMPLETION_REQUIRED_KEYS = {
    "company_identity",
    "evidence_ledger",
    "fact_pool",
    "bluf_report",
    "pir_requirements",
    "cross_verification",
}
```

- [ ] **Step 4: Update `_present()`**

Add:

```python
    if key == "pir_requirements":
        req = detail.get("intelligence_requirements") or {}
        return bool(req.get("pirs") and req.get("eeis"))
    if key == "cross_verification":
        matrix = detail.get("cross_verification_matrix") or []
        return any(item.get("status") in {"CONFIRMED", "LIKELY", "SUPPORTED"} for item in matrix)
    if key == "accepted_facts":
        return any(
            item.get("promotion_stage") == "ACCEPTED_FACT" or item.get("status") in {"CONFIRMED", "LIKELY"}
            for item in detail.get("facts") or []
        )
```

- [ ] **Step 5: Extend report rendering**

In `render_structured_report()`, add variables:

```python
    requirements = detail.get("intelligence_requirements") or {}
    matrix = detail.get("cross_verification_matrix") or []
```

After BLUF, add PIR section:

```python
    lines.extend(["", "## PIR 逐项回答"])
    pirs = requirements.get("pirs") or []
    if pirs:
        for pir in pirs[:6]:
            confidence = _format_confidence(pir.get("confidence"))
            answer = pir.get("answer") or "尚未形成完整回答。"
            lines.append(f"- [{pir.get('status', 'OPEN')} / {confidence}] {pir.get('question', '')}：{answer}")
    else:
        lines.append("- 未定义 PIR，当前报告按默认调查目标解释。")
```

After quality gate, add EEI and matrix summary:

```python
    lines.extend(["", "## EEI 覆盖摘要"])
    eeis = requirements.get("eeis") or []
    if eeis:
        for eei in eeis[:10]:
            required = "必需" if eei.get("required") else "可选"
            lines.append(f"- [{eei.get('status', 'MISSING')} / {required}] {eei.get('label', '')}")
    else:
        lines.append("- 未定义 EEI。")

    lines.extend(["", "## 交叉验证矩阵摘要"])
    if matrix:
        for row in matrix[:10]:
            value = row.get("candidate_value") or "待补充"
            lines.append(f"- [{row.get('status', 'MISSING')}] {row.get('label', row.get('field_key'))}：{value}。{row.get('rationale', '')}")
    else:
        lines.append("- 暂无交叉验证矩阵。")
```

Before next-step actions, add I&W:

```python
    lines.extend(["", "## I&W 征候"])
    indicators = _indicator_lines(detail, matrix)
    for item in indicators:
        lines.append(f"- {item}")
```

Before return, add evidence appendix title by changing `## 关键证据` to `## 证据附录`.

Add helper:

```python
def _indicator_lines(detail: dict, matrix: list[dict]) -> list[str]:
    positive = []
    risk = []
    statuses = {row.get("field_key"): row.get("status") for row in matrix}
    if statuses.get("company_identity") in {"CONFIRMED", "LIKELY"}:
        positive.append("企业身份存在较强公开来源支撑。")
    if statuses.get("contact_email") in {"CONFIRMED", "LIKELY", "SUPPORTED"} or statuses.get("contact_phone") in {"CONFIRMED", "LIKELY", "SUPPORTED"}:
        positive.append("至少一个联系渠道具备公开证据支撑。")
    if statuses.get("purchase_intent") in {"CONFIRMED", "LIKELY", "SUPPORTED"}:
        positive.append("存在采购意图或业务匹配征候。")
    if any(row.get("status") == "CONFLICTED" for row in matrix):
        risk.append("存在字段冲突，需要人工复核。")
    if not positive:
        positive.append("暂未形成强采购或身份闭合征候。")
    return [f"正向：{item}" for item in positive[:4]] + [f"风险：{item}" for item in risk[:4]]
```

- [ ] **Step 6: Run quality tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_quality_gate
```

Expected: OK.

---

### Task 6: Frontend Types And Core v3 Helpers

**Files:**
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/core-v3.ts`
- Create: `frontend/scripts/test-core-v3.ts`

- [ ] **Step 1: Write failing frontend helper test**

Create `frontend/scripts/test-core-v3.ts`:

```typescript
import assert from "node:assert/strict";
import {
  coreV3StatusLabel,
  factPromotionCounts,
  sortMatrixRows,
} from "../src/core-v3.ts";

const rows = sortMatrixRows([
  { field_key: "risk_signal", label: "风险", status: "MISSING", candidate_value: "", confidence: 0, supporting_sources: [], contradicting_sources: [], source_count: 0, independent_source_count: 0, linked_evidence_ids: [], linked_fact_ids: [], rationale: "" },
  { field_key: "company_identity", label: "企业", status: "CONFLICTED", candidate_value: "A", confidence: 0.2, supporting_sources: [], contradicting_sources: ["directory"], source_count: 1, independent_source_count: 1, linked_evidence_ids: [], linked_fact_ids: [], rationale: "" },
]);

assert.equal(coreV3StatusLabel("ACCEPTED_FACT"), "已采纳事实");
assert.equal(rows[0].field_key, "company_identity");
assert.deepEqual(
  factPromotionCounts([
    { promotion_stage: "ACCEPTED_FACT" },
    { promotion_stage: "CANDIDATE_FACT" },
    { promotion_stage: "CANDIDATE_FACT" },
  ] as any),
  { RAW_OBSERVATION: 0, CANDIDATE_FACT: 2, ASSESSED_FACT: 0, ACCEPTED_FACT: 1, REJECTED_FACT: 0 },
);

console.log("core v3 helper checks passed");
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
cd frontend
node --experimental-strip-types ./scripts/test-core-v3.ts
```

Expected: FAIL because `src/core-v3.ts` does not exist.

- [ ] **Step 3: Add types**

In `frontend/src/types.ts`, add:

```typescript
export type IntelligencePir = {
  id: string;
  question: string;
  priority: string;
  status: string;
  answer: string;
  confidence: number;
  linked_fact_ids: string[];
  remaining_gaps: string[];
};

export type IntelligenceEei = {
  id: string;
  label: string;
  field_key: string;
  required: boolean;
  status: string;
  linked_entity_values: string[];
  linked_fact_ids: string[];
};

export type IntelligenceRequirements = {
  decision_context: string;
  confidence_requirement: string;
  pirs: IntelligencePir[];
  eeis: IntelligenceEei[];
};

export type CrossVerificationRow = {
  field_key: string;
  label: string;
  candidate_value: string;
  supporting_sources: string[];
  contradicting_sources: string[];
  source_count: number;
  independent_source_count: number;
  best_admiralty_code?: string;
  status: string;
  confidence: number;
  linked_evidence_ids: string[];
  linked_fact_ids: string[];
  rationale: string;
};
```

Add to `Investigation`:

```typescript
  intelligence_requirements?: IntelligenceRequirements;
  cross_verification_matrix?: CrossVerificationRow[];
```

Add to `FactRecord`:

```typescript
  promotion_stage?: string;
```

- [ ] **Step 4: Implement helper**

Create `frontend/src/core-v3.ts`:

```typescript
import type { CrossVerificationRow, FactRecord } from "./types";

export const promotionStageOrder = [
  "RAW_OBSERVATION",
  "CANDIDATE_FACT",
  "ASSESSED_FACT",
  "ACCEPTED_FACT",
  "REJECTED_FACT",
] as const;

const labels: Record<string, string> = {
  RAW_OBSERVATION: "原始观察",
  CANDIDATE_FACT: "候选事实",
  ASSESSED_FACT: "已评估事实",
  ACCEPTED_FACT: "已采纳事实",
  REJECTED_FACT: "已拒绝事实",
  MISSING: "缺失",
  CANDIDATE: "候选",
  SUPPORTED: "有来源支持",
  LIKELY: "较可信",
  CONFIRMED: "已确认",
  CONFLICTED: "存在冲突",
  NEEDS_REVIEW: "需复核",
  OPEN: "待回答",
  PARTIAL: "部分回答",
  ANSWERED: "已回答",
  BLOCKED: "受阻",
};

const fieldPriority: Record<string, number> = {
  company_identity: 1,
  official_website: 2,
  contact_email: 3,
  contact_phone: 4,
  operation_location: 5,
  registration: 6,
  business_scope: 7,
  decision_maker: 8,
  purchase_intent: 9,
  risk_signal: 10,
};

const severity: Record<string, number> = {
  CONFLICTED: 0,
  NEEDS_REVIEW: 1,
  MISSING: 2,
  CANDIDATE: 3,
  SUPPORTED: 4,
  LIKELY: 5,
  CONFIRMED: 6,
};

export function coreV3StatusLabel(status?: string) {
  return labels[status ?? ""] ?? status ?? "未知";
}

export function sortMatrixRows(rows: CrossVerificationRow[] = []) {
  return [...rows].sort((a, b) => {
    const byPriority = (fieldPriority[a.field_key] ?? 99) - (fieldPriority[b.field_key] ?? 99);
    if (byPriority !== 0) return byPriority;
    return (severity[a.status] ?? 99) - (severity[b.status] ?? 99);
  });
}

export function factPromotionCounts(facts: Partial<FactRecord>[] = []) {
  const counts = {
    RAW_OBSERVATION: 0,
    CANDIDATE_FACT: 0,
    ASSESSED_FACT: 0,
    ACCEPTED_FACT: 0,
    REJECTED_FACT: 0,
  };
  for (const fact of facts) {
    const stage = fact.promotion_stage ?? "CANDIDATE_FACT";
    if (stage in counts) counts[stage as keyof typeof counts] += 1;
  }
  return counts;
}
```

- [ ] **Step 5: Run helper test**

Run:

```bash
cd frontend
node --experimental-strip-types ./scripts/test-core-v3.ts
```

Expected: `core v3 helper checks passed`.

---

### Task 7: Frontend Core v3 Panels

**Files:**
- Create: `frontend/src/components/IntelligenceRequirementsPanel.tsx`
- Create: `frontend/src/components/CrossVerificationMatrixPanel.tsx`
- Create: `frontend/src/components/FactPromotionPanel.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Create requirements panel**

Create `frontend/src/components/IntelligenceRequirementsPanel.tsx`:

```tsx
import { coreV3StatusLabel } from "../core-v3";
import type { IntelligenceRequirements } from "../types";

export function IntelligenceRequirementsPanel({ requirements }: { requirements?: IntelligenceRequirements }) {
  const pirs = requirements?.pirs ?? [];
  const eeis = requirements?.eeis ?? [];
  return (
    <article className="core-v2-panel hcs-brief-card core-v3-panel">
      <div className="section-heading">
        <h3>PIR / EEI 情报需求</h3>
        <span>{pirs.length} PIR · {eeis.length} EEI</span>
      </div>
      <div className="core-v3-pir-list">
        {pirs.slice(0, 5).map((pir) => (
          <div key={pir.id} className={`core-v3-status status-${pir.status.toLowerCase()}`}>
            <strong>{coreV3StatusLabel(pir.status)}</strong>
            <span>{pir.question}</span>
          </div>
        ))}
        {!pirs.length ? <div className="empty compact">暂无 PIR，系统会按目标类型生成默认情报需求。</div> : null}
      </div>
      <div className="core-v3-chip-row">
        {eeis.slice(0, 10).map((eei) => (
          <span key={eei.id} className={`core-v3-chip status-${eei.status.toLowerCase()}`} title={eei.label}>
            {eei.required ? "*" : ""}{eei.label}: {coreV3StatusLabel(eei.status)}
          </span>
        ))}
      </div>
    </article>
  );
}
```

- [ ] **Step 2: Create matrix panel**

Create `frontend/src/components/CrossVerificationMatrixPanel.tsx`:

```tsx
import { coreV3StatusLabel, sortMatrixRows } from "../core-v3";
import type { CrossVerificationRow } from "../types";

export function CrossVerificationMatrixPanel({ rows }: { rows?: CrossVerificationRow[] }) {
  const sorted = sortMatrixRows(rows ?? []);
  return (
    <article className="core-v2-panel core-v3-panel core-v3-matrix-panel">
      <div className="section-heading">
        <h3>交叉验证矩阵</h3>
        <span>{sorted.length} 项</span>
      </div>
      <div className="core-v3-table-wrap">
        <table className="core-v3-table">
          <thead>
            <tr>
              <th>字段</th>
              <th>候选值</th>
              <th>来源族</th>
              <th>状态</th>
              <th>置信</th>
              <th>依据</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={row.field_key} className={`matrix-${row.status.toLowerCase()}`}>
                <td>{row.label}</td>
                <td><code>{row.candidate_value || "待补充"}</code></td>
                <td>{row.supporting_sources.length ? row.supporting_sources.join(" / ") : "-"}</td>
                <td><span className={`core-v3-chip status-${row.status.toLowerCase()}`}>{coreV3StatusLabel(row.status)}</span></td>
                <td>{row.confidence.toFixed(2)}</td>
                <td>{row.rationale}</td>
              </tr>
            ))}
            {!sorted.length ? (
              <tr><td colSpan={6} className="empty">暂无交叉验证矩阵。</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </article>
  );
}
```

- [ ] **Step 3: Create fact promotion panel**

Create `frontend/src/components/FactPromotionPanel.tsx`:

```tsx
import { coreV3StatusLabel, factPromotionCounts, promotionStageOrder } from "../core-v3";
import type { FactRecord } from "../types";

export function FactPromotionPanel({ facts }: { facts?: FactRecord[] }) {
  const counts = factPromotionCounts(facts ?? []);
  const accepted = (facts ?? []).filter((fact) => fact.promotion_stage === "ACCEPTED_FACT" || fact.status === "CONFIRMED").slice(0, 4);
  return (
    <article className="core-v2-panel hcs-brief-card core-v3-panel">
      <div className="section-heading">
        <h3>事实晋级</h3>
        <span>{facts?.length ?? 0} 条</span>
      </div>
      <div className="core-v3-chip-row">
        {promotionStageOrder.map((stage) => (
          <span key={stage} className={`core-v3-chip status-${stage.toLowerCase()}`}>
            {coreV3StatusLabel(stage)} {counts[stage]}
          </span>
        ))}
      </div>
      <div className="detail-stack compact-stack">
        {accepted.map((fact) => (
          <div key={fact.id} className="core-v3-fact-line">
            <strong>{coreV3StatusLabel(fact.promotion_stage ?? "CANDIDATE_FACT")}</strong>
            <span>{fact.statement}</span>
          </div>
        ))}
        {!accepted.length ? <div className="empty compact">暂无已采纳事实。</div> : null}
      </div>
    </article>
  );
}
```

- [ ] **Step 4: Wire panels in `main.tsx`**

Add imports:

```tsx
import { IntelligenceRequirementsPanel } from "./components/IntelligenceRequirementsPanel";
import { CrossVerificationMatrixPanel } from "./components/CrossVerificationMatrixPanel";
import { FactPromotionPanel } from "./components/FactPromotionPanel";
```

Inside `.hcs-right-drawer-body`, before `HypothesisPanel`, add:

```tsx
                  <IntelligenceRequirementsPanel requirements={selected.intelligence_requirements} />
```

Inside `.hcs-gap-stack`, before `ReportAuditPanel`, add:

```tsx
                      <CrossVerificationMatrixPanel rows={selected.cross_verification_matrix} />
                      <FactPromotionPanel facts={selected.facts} />
```

- [ ] **Step 5: Add CSS**

Append to `frontend/src/styles.css`:

```css
.core-v3-panel {
  min-width: 0;
}

.core-v3-pir-list {
  display: grid;
  gap: 8px;
}

.core-v3-status,
.core-v3-fact-line {
  display: grid;
  gap: 4px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-soft);
}

.core-v3-status strong,
.core-v3-fact-line strong {
  font-size: 12px;
  color: var(--muted);
}

.core-v3-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.core-v3-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  min-height: 24px;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 12px;
  line-height: 1.35;
  color: var(--text);
  background: var(--surface);
}

.status-confirmed,
.status-answered,
.status-accepted_fact {
  border-color: rgba(22, 163, 74, 0.35);
  background: rgba(22, 163, 74, 0.08);
}

.status-conflicted,
.status-rejected_fact {
  border-color: rgba(220, 38, 38, 0.35);
  background: rgba(220, 38, 38, 0.08);
}

.status-needs_review,
.status-partial,
.status-candidate,
.status-candidate_fact {
  border-color: rgba(217, 119, 6, 0.35);
  background: rgba(217, 119, 6, 0.08);
}

.core-v3-table-wrap {
  overflow-x: auto;
}

.core-v3-table {
  min-width: 760px;
  table-layout: fixed;
}

.core-v3-table th:nth-child(1) { width: 110px; }
.core-v3-table th:nth-child(2) { width: 170px; }
.core-v3-table th:nth-child(3) { width: 110px; }
.core-v3-table th:nth-child(4) { width: 110px; }
.core-v3-table th:nth-child(5) { width: 70px; }

.core-v3-table td {
  vertical-align: top;
  white-space: normal;
  word-break: break-word;
}
```

If variables `--border`, `--surface-soft`, `--surface`, or `--text` are not defined in `styles.css`, use existing equivalent variables found at the top of that file.

- [ ] **Step 6: Run frontend checks**

Run:

```bash
cd frontend
node --experimental-strip-types ./scripts/test-core-v3.ts
npm run build
```

Expected: helper checks pass and build succeeds.

---

### Task 8: Task Creation Payload And Verify Script

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `scripts/verify.sh`
- Test: existing frontend build and verify script

- [ ] **Step 1: Add requirement form state**

In `frontend/src/main.tsx`, add state after `form`:

```tsx
  const [requirementsForm, setRequirementsForm] = useState({
    decision_context: "qualify buyer or company lead",
    confidence_requirement: "standard",
  });
```

- [ ] **Step 2: Include requirements in create payload**

In `createInvestigation()`, build payload with:

```tsx
    const intelligenceRequirements = {
      decision_context: requirementsForm.decision_context,
      confidence_requirement: requirementsForm.confidence_requirement,
      pirs: [],
      eeis: [],
    };
```

Add `intelligence_requirements: intelligenceRequirements` to `metadata` for sparse lead and non-sparse payloads. For non-sparse payload, set:

```tsx
    const payload = sparseMetadata
      ? {
          ...form,
          name: form.name || `弱线索买家：${sparseMetadata.lead_display_name || sparseMetadata.member_id}`,
          seed_value: sparseLeadSeedValue(sparseMetadata),
          metadata: { ...sparseMetadata, intelligence_requirements: intelligenceRequirements },
        }
      : { ...form, metadata: { intelligence_requirements: intelligenceRequirements } };
```

- [ ] **Step 3: Add compact form controls**

In the create task form after target value, add:

```tsx
              <div className="intel-requirement-mini">
                <label>情报用途
                  <input
                    value={requirementsForm.decision_context}
                    onChange={(e) => setRequirementsForm({ ...requirementsForm, decision_context: e.target.value })}
                  />
                </label>
                <label>置信要求
                  <select
                    value={requirementsForm.confidence_requirement}
                    onChange={(e) => setRequirementsForm({ ...requirementsForm, confidence_requirement: e.target.value })}
                  >
                    <option value="quick">快速判断</option>
                    <option value="standard">标准闭环</option>
                    <option value="strict">严格证据</option>
                  </select>
                </label>
              </div>
```

- [ ] **Step 4: Add verify script frontend helper**

In `scripts/verify.sh`, add after existing frontend helper checks:

```bash
node --experimental-strip-types ./scripts/test-core-v3.ts
```

- [ ] **Step 5: Run verification**

Run:

```bash
bash scripts/verify.sh
```

Expected: all backend tests, frontend helper checks, and Vite build pass.

---

### Task 9: Documentation And Deployment

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_PACKAGE.md`
- Modify: `docs/N100_DEPLOYMENT_RUNBOOK.md`

- [ ] **Step 1: Update README capability list**

In `README.md`, add to current capability bullets:

```markdown
- Intelligence Core v3：PIR/EEI 情报需求、事实晋级、交叉验证矩阵、ACH/I&W 白皮书结构。
```

- [ ] **Step 2: Update project package status**

In `docs/PROJECT_PACKAGE.md`, add under completed:

```markdown
- Intelligence Core v3：任务需求层、事实晋级、交叉验证矩阵和专业白皮书结构。
```

- [ ] **Step 3: Update <production-host> runbook acceptance criteria**

In `docs/N100_DEPLOYMENT_RUNBOOK.md`, add to final acceptance:

```markdown
- Investigation detail returns `intelligence_requirements` and `cross_verification_matrix`.
- Whitepaper includes PIR answers, cross-verification summary, ACH/I&W, gaps, and directed collection.
```

- [ ] **Step 4: Run local verification**

Run:

```bash
bash scripts/verify.sh
```

Expected: OK.

- [ ] **Step 5: Deploy to <production-host>**

Run:

```bash
rsync -az --exclude data --exclude reports --exclude frontend/node_modules --exclude frontend/dist --exclude .env --exclude frontend/.env.production --exclude .DS_Store /path/to/osint-agent-network/ <production-host>:/opt/osint-agent-network/
ssh <production-host> 'set -eu; cd /opt/osint-agent-network/frontend; npm run build; systemctl --user restart osint-agent-network-api.service osint-agent-network-web.service; sleep 3; cd /opt/osint-agent-network; bash scripts/verify.sh; curl -sS http://127.0.0.1:8088/api/health'
```

Expected:

```text
Ran 62+ tests ... OK
core v3 helper checks passed
{"status": "ok", "service": "osint-agent-network"}
```

---

## Self-Review Checklist

- Spec coverage: Tasks cover PIR/EEI, fact promotion, cross-verification matrix, quality/report updates, UI panels, creation payload, verification, docs, and <production-host> deployment.
- Placeholder scan: no TBD/TODO/implement-later placeholders are used as implementation instructions.
- Type consistency: `intelligence_requirements`, `cross_verification_matrix`, and `promotion_stage` are named consistently across backend, API, frontend types, and UI helpers.
- Risk control: migration is additive; matrix is derived; old tasks are handled by default requirement generation at read time.

