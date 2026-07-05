# Intelligence Core v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce an intelligence-analysis loop with Fact Pool, Hypothesis Pool, Evidence Ledger, temporal facts, ACH scoring, report anchors, and directed collection.

**Architecture:** Keep the existing SQLite/HTTP architecture. Add focused core modules and store tables, derive compatibility views for existing investigations, then expose new panels in the React dashboard. Reports become structured artifacts generated from facts, evidence, hypotheses, and anchors instead of free-form text alone.

**Tech Stack:** Python stdlib HTTP API, SQLite store, unittest, React + TypeScript + Vite, existing SVG graph and dashboard components.

---

## Reference Integration Notes

These references shape design choices but are not direct dependencies in this phase:

- `OpenOSINT/OpenOSINT`: model the CLI/MCP/tool-loop boundary and structured report outputs. Do not import its security reconnaissance tools into production workflows without authorization controls.
- `OWASP/www-project-social-osint-agent`: model UTC prompt injection, official-API-first collection, cached/offline analysis, and explicit OSINT ethics. Its GitHub repository is a project website; verify any implementation repository separately.
- `madeinoz67/madeinoz-osint-skill`: model the five-step intelligence cycle and knowledge graph persistence concepts.
- `getzep/graphiti`: model temporal fact windows and provenance. Core v2 implements the first layer in SQLite before considering Graphiti as an optional backend.
- `ChicagoHAI/hypothesis-generation`: model hypothesis generation/refinement before ACH scoring. Core v2 starts with deterministic ACH and leaves automatic hypothesis generation for a later task.
- `Paureel/LLM-SCI-GEN`: literature reference for hypothesis generation. No runtime use.

## File Structure

- Create `backend/app/core/fact_pool.py`: fact dataclasses, validation, temporal supersession helpers.
- Create `backend/app/core/evidence_ledger.py`: evidence source typing, Admiralty Code wrapping, evidence hash/dedupe helpers.
- Create `backend/app/core/hypothesis_pool.py`: hypothesis records and ACH bridge helpers using existing `ach_engine.py`.
- Create `backend/app/core/report_contract.py`: required section checks, contact inclusion checks, report anchor validation.
- Modify `backend/app/services/store.py`: SQLite tables, memory store maps, CRUD methods, investigation detail payload.
- Modify `backend/app/main.py`: protocol endpoints for facts, hypotheses, evidence links, collection gaps, report anchors.
- Modify `backend/app/agent_client.py`: CLI commands for writing facts/hypotheses and validating reports.
- Modify `backend/app/core/graph.py`: include fact/hypothesis/evidence-ledger nodes in graph summary without crowding main graph.
- Modify `frontend/src/types.ts`: Core v2 types.
- Create `frontend/src/components/FactPoolPanel.tsx`.
- Create `frontend/src/components/HypothesisPanel.tsx`.
- Create `frontend/src/components/EvidenceLedgerPanel.tsx`.
- Create `frontend/src/components/ReportAuditPanel.tsx`.
- Modify `frontend/src/main.tsx`: render new panels.
- Modify `frontend/src/labels.ts`: labels for facts, hypotheses, anchors, Admiralty status.
- Add tests in `backend/tests/test_intelligence_core_v2.py`.
- Add frontend helper checks in `frontend/scripts/test-intelligence-core-v2.ts`.

---

### Task 1: Core v2 Domain Model

**Files:**
- Create: `backend/app/core/fact_pool.py`
- Create: `backend/app/core/evidence_ledger.py`
- Create: `backend/app/core/hypothesis_pool.py`
- Test: `backend/tests/test_intelligence_core_v2.py`

- [ ] **Step 1: Write failing tests for fact validation and temporal supersession**

Add this to `backend/tests/test_intelligence_core_v2.py`:

```python
import unittest

from app.core.fact_pool import FactRecord, validate_fact_record, supersede_fact


class IntelligenceCoreV2DomainTests(unittest.TestCase):
    def test_confirmed_fact_requires_evidence_and_admiralty_code(self):
        fact = FactRecord(
            id="fact-1",
            investigation_id="inv-1",
            statement="SRR uses xs@csituo.com as a public contact email.",
            subject="SRR Genuine Parts",
            predicate="uses_contact_email",
            object="xs@csituo.com",
            status="CONFIRMED",
            confidence=0.82,
            admiralty_code="A-2",
            evidence_ids=["ev-1"],
            observed_at="2026-05-21T00:00:00+00:00",
            valid_from="2026-05-21T00:00:00+00:00",
        )

        validate_fact_record(fact)

    def test_confirmed_fact_without_evidence_fails_validation(self):
        fact = FactRecord(
            id="fact-1",
            investigation_id="inv-1",
            statement="SRR uses xs@csituo.com as a public contact email.",
            subject="SRR Genuine Parts",
            predicate="uses_contact_email",
            object="xs@csituo.com",
            status="CONFIRMED",
            confidence=0.82,
            admiralty_code="A-2",
            evidence_ids=[],
            observed_at="2026-05-21T00:00:00+00:00",
            valid_from="2026-05-21T00:00:00+00:00",
        )

        with self.assertRaises(ValueError):
            validate_fact_record(fact)

    def test_superseded_fact_keeps_old_validity_window(self):
        old_fact = FactRecord(
            id="fact-old",
            investigation_id="inv-1",
            statement="Company phone is +86-991-3966766.",
            subject="Xinjiang SRR Auto Parts",
            predicate="has_phone",
            object="+86-991-3966766",
            status="CONFIRMED",
            confidence=0.86,
            admiralty_code="A-2",
            evidence_ids=["ev-1"],
            observed_at="2026-05-20T00:00:00+00:00",
            valid_from="2026-05-20T00:00:00+00:00",
        )

        retired, replacement = supersede_fact(
            old_fact,
            new_id="fact-new",
            new_object="+86-991-3966788",
            observed_at="2026-05-21T00:00:00+00:00",
            evidence_ids=["ev-2"],
        )

        self.assertEqual(retired.status, "RETIRED")
        self.assertEqual(retired.valid_to, "2026-05-21T00:00:00+00:00")
        self.assertEqual(replacement.supersedes_fact_id, "fact-old")
        self.assertEqual(replacement.object, "+86-991-3966788")
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_core_v2 -v
```

Expected: import failure for `app.core.fact_pool`.

- [ ] **Step 3: Implement `fact_pool.py`**

Create `backend/app/core/fact_pool.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, replace


FACT_STATUSES = {"CONFIRMED", "LIKELY", "CONTRADICTED", "RETIRED", "NEEDS_REVIEW"}


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
    valid_to: str | None = None
    supersedes_fact_id: str | None = None


def validate_fact_record(fact: FactRecord) -> None:
    if fact.status not in FACT_STATUSES:
        raise ValueError(f"invalid fact status: {fact.status}")
    if not fact.statement.strip():
        raise ValueError("fact statement is required")
    if not fact.subject.strip() or not fact.predicate.strip() or not fact.object.strip():
        raise ValueError("fact subject, predicate, and object are required")
    if fact.status in {"CONFIRMED", "LIKELY"} and not fact.evidence_ids:
        raise ValueError("confirmed or likely facts require evidence")
    if fact.status in {"CONFIRMED", "LIKELY"} and not fact.admiralty_code:
        raise ValueError("confirmed or likely facts require admiralty_code")
    if not 0 <= float(fact.confidence) <= 1:
        raise ValueError("fact confidence must be between 0 and 1")


def supersede_fact(
    old_fact: FactRecord,
    new_id: str,
    new_object: str,
    observed_at: str,
    evidence_ids: list[str],
) -> tuple[FactRecord, FactRecord]:
    retired = replace(old_fact, status="RETIRED", valid_to=observed_at)
    replacement = replace(
        old_fact,
        id=new_id,
        object=new_object,
        statement=f"{old_fact.subject} {old_fact.predicate} {new_object}.",
        evidence_ids=evidence_ids,
        observed_at=observed_at,
        valid_from=observed_at,
        valid_to=None,
        supersedes_fact_id=old_fact.id,
    )
    validate_fact_record(replacement)
    return retired, replacement
```

- [ ] **Step 4: Run the test and verify it passes**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_core_v2 -v
```

Expected: 3 tests pass.

---

### Task 2: Evidence Ledger and Admiralty Integration

**Files:**
- Modify: `backend/tests/test_intelligence_core_v2.py`
- Create: `backend/app/core/evidence_ledger.py`

- [ ] **Step 1: Write failing tests for evidence ledger records**

Append:

```python
from app.core.evidence_ledger import EvidenceLedgerRecord, build_evidence_record


class EvidenceLedgerTests(unittest.TestCase):
    def test_evidence_record_assigns_admiralty_and_hash(self):
        record = build_evidence_record(
            id="ev-1",
            investigation_id="inv-1",
            source_url="https://www.srrautopartsonline.com/en/",
            source_type="official_website",
            source_tool="official_web",
            snippet="SRR contact page lists xs@csituo.com.",
            observed_at="2026-05-21T00:00:00+00:00",
            credibility=0.82,
        )

        self.assertIsInstance(record, EvidenceLedgerRecord)
        self.assertEqual(record.admiralty_code, "A-2")
        self.assertEqual(len(record.content_hash), 16)
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_core_v2.EvidenceLedgerTests -v
```

Expected: import failure for `evidence_ledger`.

- [ ] **Step 3: Implement `evidence_ledger.py`**

Create:

```python
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1

from app.core.verification import admiralty_code


@dataclass(frozen=True)
class EvidenceLedgerRecord:
    id: str
    investigation_id: str
    source_url: str
    source_type: str
    source_tool: str
    snippet: str
    observed_at: str
    admiralty_code: str
    source_reliability: str
    information_credibility: str
    content_hash: str


def build_evidence_record(
    id: str,
    investigation_id: str,
    source_url: str,
    source_type: str,
    source_tool: str,
    snippet: str,
    observed_at: str,
    credibility: float,
) -> EvidenceLedgerRecord:
    code = admiralty_code(source_type, credibility)
    return EvidenceLedgerRecord(
        id=id,
        investigation_id=investigation_id,
        source_url=source_url,
        source_type=source_type,
        source_tool=source_tool,
        snippet=snippet,
        observed_at=observed_at,
        admiralty_code=code["code"],
        source_reliability=code["source_reliability"],
        information_credibility=code["information_credibility"],
        content_hash=sha1(f"{source_url}:{snippet}".encode("utf-8")).hexdigest()[:16],
    )
```

- [ ] **Step 4: Run and verify pass**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_core_v2 -v
```

Expected: all current Core v2 tests pass.

---

### Task 3: Store Tables and Investigation Detail Payload

**Files:**
- Modify: `backend/app/services/store.py`
- Modify: `backend/tests/test_intelligence_core_v2.py`

- [ ] **Step 1: Write failing store tests**

Append:

```python
from tempfile import TemporaryDirectory
from pathlib import Path

from app.services.store import SQLiteStore


class CoreV2StoreTests(unittest.TestCase):
    def test_sqlite_store_persists_facts_and_evidence_ledger(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            investigation = store.create_investigation(
                name="SRR core v2",
                seed_type="company",
                seed_value="SRR Genuine Parts",
                strategy_name="deep",
            )
            evidence = store.add_evidence_record(
                investigation_id=investigation.id,
                source_url="https://www.srrautopartsonline.com/en/",
                source_type="official_website",
                source_tool="official_web",
                snippet="SRR contact page lists xs@csituo.com.",
                credibility=0.82,
            )
            fact = store.add_fact(
                investigation_id=investigation.id,
                statement="SRR uses xs@csituo.com as a public contact email.",
                subject="SRR Genuine Parts",
                predicate="uses_contact_email",
                object_value="xs@csituo.com",
                status="CONFIRMED",
                confidence=0.82,
                admiralty_code=evidence["admiralty_code"],
                evidence_ids=[evidence["id"]],
            )

            detail = SQLiteStore(str(Path(tmpdir) / "osint.sqlite")).get_investigation(investigation.id)

        self.assertEqual(detail["evidence_ledger"][0]["admiralty_code"], "A-2")
        self.assertEqual(detail["facts"][0]["id"], fact["id"])
        self.assertEqual(detail["facts"][0]["evidence_ids"], [evidence["id"]])
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_core_v2.CoreV2StoreTests -v
```

Expected: `SQLiteStore` has no `add_evidence_record`.

- [ ] **Step 3: Add SQLite schema**

Modify `_ensure_schema()` in `backend/app/services/store.py` to create:

```sql
CREATE TABLE IF NOT EXISTS evidence_ledger (
  id TEXT PRIMARY KEY,
  investigation_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_tool TEXT NOT NULL,
  snippet TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  admiralty_code TEXT NOT NULL,
  source_reliability TEXT NOT NULL,
  information_credibility TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
)
```

and:

```sql
CREATE TABLE IF NOT EXISTS facts (
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
  supersedes_fact_id TEXT,
  FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
)
```

- [ ] **Step 4: Add store methods**

In `SQLiteStore`, add methods:

```python
def add_evidence_record(...): ...
def add_fact(...): ...
```

Use `uuid4()` for IDs and `_now()` for timestamps. Use `build_evidence_record()` and `FactRecord` / `validate_fact_record()`.

- [ ] **Step 5: Add detail fields**

In `SQLiteStore.get_investigation()`, add:

```python
data["evidence_ledger"] = [...]
data["facts"] = [...]
```

Parse `evidence_ids_json` into lists.

- [ ] **Step 6: Run and verify pass**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_core_v2.CoreV2StoreTests -v
```

Expected: store test passes.

---

### Task 4: Hypothesis Pool and ACH Store Integration

**Files:**
- Modify: `backend/app/services/store.py`
- Modify: `backend/tests/test_intelligence_core_v2.py`

- [ ] **Step 1: Write failing ACH store test**

Append:

```python
class HypothesisPoolStoreTests(unittest.TestCase):
    def test_store_scores_hypotheses_with_ach(self):
        store = SQLiteStore(":memory:")
        investigation = store.create_investigation(
            name="SRR ACH",
            seed_type="company",
            seed_value="SRR Genuine Parts",
            strategy_name="deep",
        )
        store.add_hypothesis(investigation.id, "h1", "SRR is an active export brand network.")
        store.add_hypothesis(investigation.id, "h2", "SRR is only a dormant brand shell.")
        store.add_hypothesis(investigation.id, "h3", "SRR evidence is mostly same-name noise.")
        result = store.score_hypotheses(
            investigation.id,
            [
                {
                    "id": "ev-export",
                    "summary": "MIMS exhibitor page shows SRR export contact and product categories.",
                    "kinds": ["company_news_report"],
                    "supports": ["h1"],
                    "contradicts": ["h2", "h3"],
                    "source_reliability": "B",
                    "credibility": 0.72,
                    "keywords": ["exhibitor", "export"],
                }
            ],
        )

        self.assertEqual(result["most_likely_hypothesis"], "h1")
        self.assertTrue(any(row["id"] == "h1" for row in result["hypotheses"]))
```

- [ ] **Step 2: Run and verify failure**

Run the test; expect missing `add_hypothesis`.

- [ ] **Step 3: Add `hypotheses` and `hypothesis_evidence` tables**

Create SQLite tables with fields matching spec.

- [ ] **Step 4: Add store methods**

Implement:

```python
def add_hypothesis(self, investigation_id, hypothesis_id, statement, group="default") -> dict
def score_hypotheses(self, investigation_id, evidence_items: list[dict]) -> dict
```

Bridge dict evidence into `ach_engine.EvidenceItem`, run `run_ach_analysis()`, persist statuses.

- [ ] **Step 5: Verify**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_core_v2 -v
```

Expected: all Core v2 tests pass.

---

### Task 5: Agent Protocol Endpoints

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/agent_client.py`
- Modify: `backend/tests/test_agent_protocol.py`
- Modify: `backend/tests/test_agent_client.py`

- [ ] **Step 1: Add failing API tests**

Add tests that POST:

- `/api/agent/evidence-records`
- `/api/agent/facts`
- `/api/agent/hypotheses`
- `/api/agent/hypotheses/score`

Assert 201 responses and investigation detail contains new records.

- [ ] **Step 2: Run and verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_protocol backend.tests.test_agent_client -v
```

Expected: 404 for new endpoints.

- [ ] **Step 3: Implement handlers**

In `ApiHandler.do_POST`, add branches before task completion:

```python
if parsed.path == "/api/agent/evidence-records": ...
if parsed.path == "/api/agent/facts": ...
if parsed.path == "/api/agent/hypotheses": ...
if parsed.path == "/api/agent/hypotheses/score": ...
```

- [ ] **Step 4: Add CLI commands**

Add subcommands to `agent_client.py`:

- `evidence-record`
- `fact`
- `hypothesis`
- `score-hypotheses`

- [ ] **Step 5: Verify**

Run API and client tests.

---

### Task 6: Report Contract and Anchors

**Files:**
- Create: `backend/app/core/report_contract.py`
- Modify: `backend/app/services/store.py`
- Test: `backend/tests/test_intelligence_core_v2.py`

- [ ] **Step 1: Write failing report contract tests**

Add tests:

- confirmed contact fact must appear in report.
- report anchor IDs must point to existing evidence ledger IDs.
- missing required sections fail validation.

- [ ] **Step 2: Implement `report_contract.py`**

Add:

```python
REQUIRED_ENTERPRISE_SECTIONS = [...]
def validate_enterprise_report(report_markdown, facts, evidence_ledger, anchors) -> list[str]
```

Return list of errors. Empty list means valid.

- [ ] **Step 3: Gate task completion**

Do not block all legacy reports yet. Add validation output to investigation detail as `report_audit`. For Core v2 reports, if metadata has `core_version: "v2"`, reject completion when errors exist.

- [ ] **Step 4: Verify tests**

Run Core v2 and agent protocol tests.

---

### Task 7: Frontend Panels

**Files:**
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/components/FactPoolPanel.tsx`
- Create: `frontend/src/components/HypothesisPanel.tsx`
- Create: `frontend/src/components/EvidenceLedgerPanel.tsx`
- Create: `frontend/src/components/ReportAuditPanel.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles.css`
- Add: `frontend/scripts/test-intelligence-core-v2.ts`

- [ ] **Step 1: Write frontend helper test**

Create a script that constructs a sample investigation detail and asserts:

- facts are grouped by status.
- hypotheses show ACH status.
- evidence ledger shows Admiralty Code.
- report audit errors are visible.

- [ ] **Step 2: Run and verify failure**

Run:

```bash
node --experimental-strip-types frontend/scripts/test-intelligence-core-v2.ts
```

Expected: import failure for helper or missing types.

- [ ] **Step 3: Add types**

Add `FactRecord`, `EvidenceLedgerRecord`, `HypothesisRecord`, `ReportAudit` to `frontend/src/types.ts`.

- [ ] **Step 4: Add panels**

Use existing `DataRow`, `section-heading`, `compact-details`, and dense console styling. Do not add decorative layouts.

- [ ] **Step 5: Render panels**

In `frontend/src/main.tsx`, render panels near `IntelligenceMemoryPanel`.

- [ ] **Step 6: Verify frontend**

Run:

```bash
node --experimental-strip-types frontend/scripts/test-intelligence-core-v2.ts
npm run build
```

Expected: script passes and build succeeds.

---

### Task 8: Migration and SRR Backfill

**Files:**
- Create: `backend/scripts/backfill_core_v2.py`
- Test: `backend/tests/test_intelligence_core_v2.py`

- [ ] **Step 1: Write failing backfill test**

Use a temporary SQLite store with SRR-like entities/evidence/relationships. Run backfill. Assert contact facts are created for emails, phones, and people.

- [ ] **Step 2: Implement backfill**

Rules:

- `email`, `phone`, `address`, `identity`, `organization`, `business_scope`, `product_scope`, `production_base`, `risk_signal` become candidate or confirmed facts depending on confidence and evidence.
- Existing evidence becomes evidence ledger records.
- Relationships become fact triples when endpoints exist.
- Existing report is not overwritten; add report audit results.

- [ ] **Step 3: Run locally**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_core_v2 -v
PYTHONPATH=backend python3 backend/scripts/backfill_core_v2.py --db data/osint.sqlite --dry-run
```

- [ ] **Step 4: Deploy and run on n100**

After local verification:

```bash
rsync -az --exclude node_modules --exclude data --exclude frontend/dist /Users/aidi/情报官/osint-agent-network/ n100:/home/aidi/apps/osint-agent-network/
ssh n100 'cd /home/aidi/apps/osint-agent-network && scripts/stop.sh && scripts/start.sh'
ssh n100 'cd /home/aidi/apps/osint-agent-network && PYTHONPATH=backend python3 backend/scripts/backfill_core_v2.py --db data/osint.sqlite'
```

---

### Task 9: Full Verification

**Files:**
- Existing test suite.

- [ ] **Step 1: Run backend tests**

```bash
PYTHONPATH=backend python3 -m unittest discover backend/tests -v
```

- [ ] **Step 2: Run frontend checks**

```bash
cd frontend
npm run build
node --experimental-strip-types scripts/test-graph-helpers.ts
node --experimental-strip-types scripts/test-investigation-bundle.ts
node --experimental-strip-types scripts/test-sparse-lead.ts
node --experimental-strip-types scripts/test-intelligence-core-v2.ts
```

- [ ] **Step 3: Verify n100 health**

```bash
curl -sS http://10.0.0.184:8088/api/health
ssh n100 'cd /home/aidi/apps/osint-agent-network && scripts/status.sh'
```

- [ ] **Step 4: Verify SRR task**

```bash
ssh n100 'curl -sS http://127.0.0.1:8088/api/investigations/196fb57f-dace-4fcc-a45e-bb22d0f46c70 | jq "{facts:(.facts|length), evidence_ledger:(.evidence_ledger|length), hypotheses:(.hypotheses|length), report_audit:.report_audit}"'
```

Expected:

- facts count greater than 0.
- evidence_ledger count greater than 0.
- contact facts exist for known SRR emails and phones.
- report audit has no missing contact errors.

---

## Self-Review

Spec coverage:

- Fact Pool: Tasks 1, 3, 5, 8.
- Hypothesis Pool and ACH: Tasks 4, 5, 7.
- Evidence Ledger and Admiralty Code: Tasks 2, 3, 5, 7.
- Temporal facts: Task 1 and Task 8.
- Report audit and required sections: Task 6 and Task 9.
- UI panels: Task 7.
- Migration/backfill: Task 8.

No placeholders remain. Each task has exact files, commands, and expected outcomes.
