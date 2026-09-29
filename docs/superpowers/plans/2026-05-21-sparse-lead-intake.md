# Sparse Lead Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a privacy-safe sparse lead intake workflow for Alibaba/CRM weak buyer records, including metadata anchors, role-based jobs, constrained query planning, UI intake fields, and analyst stage display.

**Architecture:** The backend keeps the current lightweight API, SQLite/MemoryStore stores, and Intel Tool Gateway. Sparse leads become a new target type with optional investigation metadata, role-based route templates, and a deterministic anchor extraction adapter that writes visible screenshot facts before any candidate discovery. The frontend adds conditional intake fields and stage display while preserving existing company/domain/email/username/phone flows.

**Tech Stack:** Python 3 `unittest`, Python `http.server`, SQLite, React 19, TypeScript, Vite, Node script checks.

---

## File Structure

- Modify `backend/app/core/normalization.py`: accept `sparse_lead` as a human-readable target type.
- Modify `backend/app/core/intel_gateway.py`: add sparse-lead route templates and strategy subsets.
- Modify `backend/app/core/planner.py`: no new APIs, but tests should verify sparse-lead jobs.
- Modify `backend/app/services/store.py`: add investigation metadata storage and fix SQLite `add_jobs()` planned-job parity.
- Modify `backend/app/main.py`: accept optional `metadata` in investigation creation and expose it in details.
- Modify `backend/app/agent_client.py`: include `sparse_lead` in default capabilities.
- Create `backend/app/core/sparse_lead.py`: pure helpers to convert metadata into entities, evidence, and relationships, plus stage summaries.
- Create `backend/app/tools/lead_anchor.py`: local adapter for `lead_anchor_extraction`.
- Modify `backend/app/tools/__init__.py`: register the new adapter.
- Modify `backend/app/tools/base.py` only if the current normalized dataclasses are missing fields needed by the adapter. Prefer not changing them in v1.
- Modify `backend/tests/test_core.py`: normalization and route planning tests.
- Modify `backend/tests/test_agent_protocol.py`: metadata persistence and sparse-lead job tests.
- Modify `backend/tests/test_worker.py`: SQLite planned-job parity and anchor adapter execution tests.
- Modify `frontend/src/types.ts`: add metadata and sparse-lead display types.
- Modify `frontend/src/labels.ts`: add labels for sparse lead target, agent roles, entity types, evidence kinds, and relationships.
- Modify `frontend/src/main.tsx`: add sparse lead form state, payload metadata, and stage panel rendering.
- Create `frontend/src/sparse-lead.ts`: helpers for parsing textarea values, formatting stage state, and building metadata payloads.
- Create `frontend/scripts/test-sparse-lead.ts`: frontend helper tests.
- Modify `frontend/package.json`: add or keep direct node script invocation through verification docs. No package script is required unless desired.
- Modify `scripts/verify.sh`: include backend sparse-lead tests through existing test modules and run `frontend/scripts/test-sparse-lead.ts`.

## Task 1: Fix Planned Job Parity And Sparse Lead Normalization

**Files:**
- Modify: `backend/app/core/normalization.py`
- Modify: `backend/app/services/store.py`
- Modify: `backend/tests/test_core.py`
- Modify: `backend/tests/test_worker.py`

- [ ] **Step 1: Add failing normalization test**

Append this test to `NormalizationTests` in `backend/tests/test_core.py`:

```python
    def test_normalizes_sparse_lead_human_readable_seed(self):
        self.assertEqual(
            normalize_target("sparse_lead", "  Long Way / in19034126503jgqn  "),
            "Long Way / in19034126503jgqn",
        )

        with self.assertRaises(NormalizationError):
            normalize_target("sparse_lead", "x" * 501)
```

- [ ] **Step 2: Add failing SQLite add_jobs parity test**

Add this import near the top of `backend/tests/test_worker.py`:

```python
from app.core.planner import PlannedJob
```

Append this test to `WorkerTests`:

```python
    def test_sqlite_add_jobs_preserves_planned_job_contract_fields(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "osint.sqlite"
            store = SQLiteStore(str(db_path))
            investigation = store.create_investigation(
                name="弱线索买家：Long Way",
                seed_type="company",
                seed_value="Long Way",
                strategy_name="deep",
            )

            created = store.add_jobs(
                investigation.id,
                [
                    PlannedJob(
                        tool_name="identity_match_review",
                        target_type="sparse_lead",
                        target_value="Long Way / in19034126503jgqn",
                        depth=1,
                        agent_role="cross_verification_agent",
                        output_contract="claims,evidence: identity_match_confidence",
                        depends_on="candidate_business_discovery",
                    )
                ],
            )

            detail = store.get_investigation(investigation.id)
            job = next(item for item in detail["jobs"] if item["id"] == created[0]["id"])

        self.assertEqual(job["agent_role"], "cross_verification_agent")
        self.assertEqual(job["output_contract"], "claims,evidence: identity_match_confidence")
        self.assertEqual(job["depends_on"], "candidate_business_discovery")
```

- [ ] **Step 3: Run tests and verify failures**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_core backend.tests.test_worker
```

Expected: FAIL. `sparse_lead` is unsupported, and SQLite `add_jobs()` returns/persists default contract fields.

- [ ] **Step 4: Implement sparse_lead normalization**

Modify `normalize_target()` in `backend/app/core/normalization.py` so the company branch includes sparse leads:

```python
    if target_type in {"company", "sparse_lead"}:
        normalized = re.sub(r"\s+", " ", raw)
        if len(normalized) > 500:
            raise NormalizationError(f"{target_type} target is too long: {value}")
        return normalized
```

Replace the existing `if target_type == "company":` block with this block.

- [ ] **Step 5: Fix SQLite add_jobs parity**

In `SQLiteStore.add_jobs()` in `backend/app/services/store.py`, replace the `Job(...)` construction with:

```python
                job = Job(
                    id=str(uuid4()),
                    investigation_id=investigation_id,
                    tool_name=planned.tool_name,
                    target_type=planned.target_type,
                    target_value=planned.target_value,
                    depth=planned.depth,
                    agent_role=getattr(planned, "agent_role", "tool_agent"),
                    output_contract=getattr(planned, "output_contract", "entities,evidence,relationships"),
                    depends_on=getattr(planned, "depends_on", ""),
                )
```

Keep the existing `INSERT INTO jobs` statement, but make sure the values tuple uses:

```python
                        job.agent_role,
                        job.output_contract,
                        job.depends_on,
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_core backend.tests.test_worker
```

Expected: PASS.

- [ ] **Step 7: Commit**

If the project is inside a git repository, run:

```bash
git add backend/app/core/normalization.py backend/app/services/store.py backend/tests/test_core.py backend/tests/test_worker.py
git commit -m "fix: preserve sparse lead planning fields"
```

If `git status` reports this directory is not a repository, record that in the final handoff and continue without committing.

## Task 2: Add Sparse Lead Metadata Persistence

**Files:**
- Modify: `backend/app/services/store.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_agent_protocol.py`

- [ ] **Step 1: Add failing MemoryStore metadata test**

Append this test to `AgentProtocolTests` in `backend/tests/test_agent_protocol.py`:

```python
    def test_memory_store_creates_sparse_lead_with_metadata(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Alibaba 买家弱线索：Long Way",
            seed_type="sparse_lead",
            seed_value="Long Way / in19034126503jgqn",
            strategy_name="deep",
            metadata={
                "platform": "Alibaba",
                "lead_display_name": "Long Way",
                "member_id": "in19034126503jgqn",
                "country_region": "IN",
            },
        )

        detail = store.get_investigation(investigation.id)

        self.assertEqual(detail["seed_type"], "sparse_lead")
        self.assertEqual(detail["metadata"]["platform"], "Alibaba")
        self.assertEqual(detail["metadata"]["member_id"], "in19034126503jgqn")
```

- [ ] **Step 2: Add failing SQLite metadata persistence test**

Append this test to `AgentProtocolTests`:

```python
    def test_sqlite_store_persists_sparse_lead_metadata(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "osint.sqlite"
            first_store = SQLiteStore(str(db_path))
            investigation = first_store.create_investigation(
                name="Alibaba 买家弱线索：Long Way",
                seed_type="sparse_lead",
                seed_value="Long Way / in19034126503jgqn",
                strategy_name="deep",
                metadata={
                    "platform": "Alibaba",
                    "lead_display_name": "Long Way",
                    "member_id": "in19034126503jgqn",
                    "country_region": "IN",
                    "categories": ["Induction Cookers", "Gas Cooktops"],
                },
            )

            second_store = SQLiteStore(str(db_path))
            detail = second_store.get_investigation(investigation.id)

        self.assertEqual(detail["metadata"]["platform"], "Alibaba")
        self.assertEqual(detail["metadata"]["categories"], ["Induction Cookers", "Gas Cooktops"])
```

- [ ] **Step 3: Run test and verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_protocol
```

Expected: FAIL because `create_investigation()` does not accept `metadata`.

- [ ] **Step 4: Add metadata field to Investigation dataclass**

In `backend/app/services/store.py`, add this field to `Investigation`:

```python
    metadata: dict | None = None
```

Place it after `risk_report`.

- [ ] **Step 5: Update MemoryStore.create_investigation signature and object**

Change `MemoryStore.create_investigation()` signature to:

```python
    def create_investigation(
        self,
        name: str,
        seed_type: str,
        seed_value: str,
        strategy_name: str,
        metadata: dict | None = None,
    ) -> Investigation:
```

Add this field to the `Investigation(...)` constructor:

```python
            metadata=metadata or {},
```

- [ ] **Step 6: Include metadata in MemoryStore detail**

In `MemoryStore._investigation_detail()`, after `data = asdict(investigation)`, add:

```python
        data["metadata"] = investigation.metadata or {}
```

- [ ] **Step 7: Update SQLiteStore.create_investigation signature and constructor**

Change `SQLiteStore.create_investigation()` signature to:

```python
    def create_investigation(
        self,
        name: str,
        seed_type: str,
        seed_value: str,
        strategy_name: str,
        metadata: dict | None = None,
    ) -> Investigation:
```

Add this field to its `Investigation(...)` constructor:

```python
            metadata=metadata or {},
```

- [ ] **Step 8: Add metadata_json column**

In the SQLite `CREATE TABLE IF NOT EXISTS investigations` statement, add:

```sql
                    metadata_json TEXT NOT NULL DEFAULT '{}'
```

Put it after `risk_report_json TEXT NOT NULL DEFAULT '{}'`, with a comma before it.

In `_init_schema()`, after the `risk_report_json` migration, add:

```python
            if "metadata_json" not in columns:
                conn.execute(
                    "ALTER TABLE investigations ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
                )
```

- [ ] **Step 9: Update investigation row serialization**

In `_investigation_row()`, append:

```python
        json.dumps(investigation.metadata or {}, ensure_ascii=False),
```

Update the `INSERT INTO investigations` column list in `SQLiteStore.create_investigation()` to include `metadata_json`, and add one more `?` placeholder.

- [ ] **Step 10: Update row deserialization**

In `_investigation_from_row()`, add:

```python
        "metadata": json.loads(row["metadata_json"] or "{}"),
```

- [ ] **Step 11: Update import_detail**

In `SQLiteStore.import_detail()`, include `metadata_json` in the `INSERT OR REPLACE INTO investigations` column list and values tuple. Use:

```python
                    json.dumps(detail.get("metadata", {}), ensure_ascii=False),
```

- [ ] **Step 12: Update API create endpoint**

In `backend/app/main.py`, update the `store.create_investigation(...)` call:

```python
                investigation = store.create_investigation(
                    name=payload["name"],
                    seed_type=payload["seed_type"],
                    seed_value=payload["seed_value"],
                    strategy_name=payload.get("strategy", "standard"),
                    metadata=payload.get("metadata", {}),
                )
```

- [ ] **Step 13: Run focused tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_protocol
```

Expected: PASS.

- [ ] **Step 14: Commit**

```bash
git add backend/app/services/store.py backend/app/main.py backend/tests/test_agent_protocol.py
git commit -m "feat: persist sparse lead metadata"
```

Skip commit if this directory is not a git repository.

## Task 3: Add Sparse Lead Route Matrix

**Files:**
- Modify: `backend/app/core/intel_gateway.py`
- Modify: `backend/app/agent_client.py`
- Modify: `backend/tests/test_core.py`
- Modify: `backend/tests/test_agent_protocol.py`

- [ ] **Step 1: Add failing planner tests**

Append this test to `PlannerTests` in `backend/tests/test_core.py`:

```python
    def test_sparse_lead_deep_strategy_queues_role_based_intake_jobs(self):
        registry = default_tool_registry()
        jobs = plan_initial_jobs(
            seed_type="sparse_lead",
            seed_value="Long Way / in19034126503jgqn",
            strategy=StrategyProfile.deep(),
            registry=registry,
        )

        tools = [job.tool_name for job in jobs]
        roles = {job.agent_role for job in jobs}

        self.assertEqual(
            tools,
            [
                "lead_anchor_extraction",
                "constrained_query_planning",
                "candidate_business_discovery",
                "rfq_category_analysis",
                "identity_match_review",
                "analysis_judgement",
            ],
        )
        self.assertIn("lead_intake_agent", roles)
        self.assertIn("search_planning_agent", roles)
        self.assertIn("enterprise_intel_agent", roles)
        self.assertIn("purchase_intent_agent", roles)
        self.assertIn("cross_verification_agent", roles)
        analysis_job = next(job for job in jobs if job.tool_name == "analysis_judgement")
        self.assertIn("ACH", analysis_job.output_contract)
        self.assertIn("identity_match_review", analysis_job.depends_on)
```

Append this test to `PlannerTests`:

```python
    def test_sparse_lead_quick_strategy_limits_to_intake_planning_and_analysis(self):
        registry = default_tool_registry()
        jobs = plan_initial_jobs(
            seed_type="sparse_lead",
            seed_value="Long Way / in19034126503jgqn",
            strategy=StrategyProfile.quick(),
            registry=registry,
        )

        self.assertEqual(
            [job.tool_name for job in jobs],
            ["lead_anchor_extraction", "constrained_query_planning", "analysis_judgement"],
        )
```

- [ ] **Step 2: Add failing store detail test**

Append this test to `AgentProtocolTests`:

```python
    def test_sparse_lead_investigation_jobs_include_agent_roles_and_contracts(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Alibaba 买家弱线索：Long Way",
            seed_type="sparse_lead",
            seed_value="Long Way / in19034126503jgqn",
            strategy_name="deep",
            metadata={"platform": "Alibaba", "member_id": "in19034126503jgqn"},
        )

        jobs = store.get_investigation(investigation.id)["jobs"]
        anchor_job = next(job for job in jobs if job["tool_name"] == "lead_anchor_extraction")
        match_job = next(job for job in jobs if job["tool_name"] == "identity_match_review")

        self.assertEqual(anchor_job["agent_role"], "lead_intake_agent")
        self.assertIn("platform anchors", anchor_job["output_contract"])
        self.assertEqual(match_job["agent_role"], "cross_verification_agent")
        self.assertIn("identity_match_confidence", match_job["output_contract"])
```

- [ ] **Step 3: Run tests and verify failures**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_core backend.tests.test_agent_protocol
```

Expected: FAIL because no sparse-lead routes exist.

- [ ] **Step 4: Add sparse lead route templates**

In `backend/app/core/intel_gateway.py`, add this tuple after `COMPANY_ROUTE_MATRIX`:

```python
SPARSE_LEAD_ROUTE_MATRIX: tuple[_RouteTemplate, ...] = (
    _RouteTemplate(
        "lead_anchor_extraction",
        "lead_intake",
        agent_role="lead_intake_agent",
        output_contract="entities,evidence,relationships: platform anchors, visible buyer fields, privacy state",
    ),
    _RouteTemplate(
        "constrained_query_planning",
        "search_planning",
        agent_role="search_planning_agent",
        output_contract="claims,evidence: constrained query matrix, exclusion notes, search priority",
        depends_on="lead_anchor_extraction",
    ),
    _RouteTemplate(
        "candidate_business_discovery",
        "role_agent",
        agent_role="enterprise_intel_agent",
        output_contract="entities,evidence,relationships: candidate companies, public records, websites, business scope",
        depends_on="constrained_query_planning",
    ),
    _RouteTemplate(
        "rfq_category_analysis",
        "role_agent",
        agent_role="purchase_intent_agent",
        output_contract="entities,evidence,claims: purchase categories, RFQ intent signals, RFQ noise signals",
        depends_on="lead_anchor_extraction",
    ),
    _RouteTemplate(
        "identity_match_review",
        "analysis_agent",
        agent_role="cross_verification_agent",
        output_contract=(
            "claims,evidence,relationships: record_confidence, identity_match_confidence, "
            "field_interpretation_confidence, candidate_status, mismatch_signals"
        ),
        depends_on="candidate_business_discovery,rfq_category_analysis",
    ),
    _RouteTemplate(
        "analysis_judgement",
        "analysis_agent",
        agent_role="analysis_judgement_agent",
        output_contract="claims,graph_slots,report: PIR, ACH, BLUF, risk_summary, directed_collection",
        depends_on="identity_match_review",
    ),
)
```

- [ ] **Step 5: Wire sparse_lead into template selection**

Modify `_templates_for()` in `backend/app/core/intel_gateway.py`:

```python
    if target_type == "sparse_lead":
        if strategy_name == "quick":
            return (
                SPARSE_LEAD_ROUTE_MATRIX[0],
                SPARSE_LEAD_ROUTE_MATRIX[1],
                SPARSE_LEAD_ROUTE_MATRIX[-1],
            )
        if strategy_name == "standard":
            return (
                SPARSE_LEAD_ROUTE_MATRIX[0],
                SPARSE_LEAD_ROUTE_MATRIX[1],
                SPARSE_LEAD_ROUTE_MATRIX[2],
                SPARSE_LEAD_ROUTE_MATRIX[4],
                SPARSE_LEAD_ROUTE_MATRIX[-1],
            )
        return SPARSE_LEAD_ROUTE_MATRIX
```

Place it after the `company` branch and before `templates = ROUTE_MATRIX.get(...)`.

- [ ] **Step 6: Add default agent capabilities**

In `backend/app/agent_client.py`, add these strings to `DEFAULT_CAPABILITIES`:

```python
    "sparse_lead",
    "lead_anchor_extraction",
    "constrained_query_planning",
    "candidate_business_discovery",
    "rfq_category_analysis",
    "identity_match_review",
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_core backend.tests.test_agent_protocol
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/intel_gateway.py backend/app/agent_client.py backend/tests/test_core.py backend/tests/test_agent_protocol.py
git commit -m "feat: add sparse lead route matrix"
```

Skip commit if this directory is not a git repository.

## Task 4: Add Deterministic Anchor Extraction Adapter

**Files:**
- Create: `backend/app/core/sparse_lead.py`
- Create: `backend/app/tools/lead_anchor.py`
- Modify: `backend/app/tools/__init__.py`
- Modify: `backend/app/services/worker.py`
- Modify: `backend/tests/test_worker.py`

- [ ] **Step 1: Add failing sparse lead helper and worker test**

Append this test to `backend/tests/test_worker.py`:

```python
    def test_worker_extracts_sparse_lead_anchors_from_metadata(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Alibaba 买家弱线索：Long Way",
            seed_type="sparse_lead",
            seed_value="Long Way / in19034126503jgqn",
            strategy_name="quick",
            metadata={
                "platform": "Alibaba",
                "lead_display_name": "Long Way",
                "member_id": "in19034126503jgqn",
                "country_region": "IN",
                "registration_year": "2023",
                "company_name_raw": "Long Way",
                "privacy_state": "email_phone_hidden",
                "categories": ["Induction Cookers", "Gas Cooktops"],
                "recent_rfqs": ["2200W Best Quality And Low Price Durable Electric Cook Top"],
            },
        )

        with TemporaryDirectory() as tmpdir:
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
            )

        detail = store.get_investigation(investigation.id)
        entity_pairs = {(item["type"], item["value"]) for item in detail["entities"]}
        evidence_kinds = {item["evidence_kind"] for item in detail["evidence"]}
        relationship_types = {item["relationship_type"] for item in detail["relationships"]}

        self.assertEqual(result["completed"], 1)
        self.assertIn(("platform_account", "Long Way"), entity_pairs)
        self.assertIn(("platform_member_id", "in19034126503jgqn"), entity_pairs)
        self.assertIn(("country_region", "IN"), entity_pairs)
        self.assertIn(("purchase_category", "Induction Cookers"), entity_pairs)
        self.assertIn(("rfq_text", "2200W Best Quality And Low Price Durable Electric Cook Top"), entity_pairs)
        self.assertIn("visible_buyer_anchor", evidence_kinds)
        self.assertIn("lead_has_platform_anchor", relationship_types)
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_worker
```

Expected: FAIL because `lead_anchor_extraction` adapter does not exist or cannot read metadata.

- [ ] **Step 3: Create sparse lead helper module**

Create `backend/app/core/sparse_lead.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.tools.base import NormalizedEntity, NormalizedEvidence, NormalizedRelationship


@dataclass(frozen=True)
class SparseLeadAnchorBundle:
    entities: list[NormalizedEntity]
    evidence: list[NormalizedEvidence]
    relationships: list[NormalizedRelationship]


def anchors_from_metadata(seed_value: str, metadata: dict) -> SparseLeadAnchorBundle:
    source_tool = "lead_anchor_extraction"
    entities: list[NormalizedEntity] = []
    evidence: list[NormalizedEvidence] = []
    relationships: list[NormalizedRelationship] = []

    def add_anchor(entity_type: str, value: str, confidence: float = 1.0) -> None:
        cleaned = str(value or "").strip()
        if not cleaned:
            return
        entities.append(NormalizedEntity(entity_type, cleaned, source_tool, confidence))
        evidence.append(
            NormalizedEvidence(
                cleaned,
                "visible_buyer_anchor",
                source_tool,
                f"Visible sparse lead anchor from operator-entered platform/CRM record: {entity_type}={cleaned}",
            )
        )
        relationships.append(
            NormalizedRelationship(
                seed_value,
                cleaned,
                "lead_has_platform_anchor",
                confidence,
            )
        )

    add_anchor("platform", metadata.get("platform", ""), 1.0)
    add_anchor("platform_account", metadata.get("lead_display_name", ""), 1.0)
    add_anchor("platform_member_id", metadata.get("member_id", ""), 1.0)
    add_anchor("country_region", metadata.get("country_region", ""), 1.0)
    add_anchor("registration_year", metadata.get("registration_year", ""), 0.95)
    add_anchor("company_name_raw", metadata.get("company_name_raw", ""), 0.9)
    add_anchor("privacy_state", metadata.get("privacy_state", ""), 0.9)

    for category in metadata.get("categories", []) or []:
        add_anchor("purchase_category", category, 0.72)

    for rfq in metadata.get("recent_rfqs", []) or []:
        add_anchor("rfq_text", rfq, 0.62)

    return SparseLeadAnchorBundle(entities=entities, evidence=evidence, relationships=relationships)
```

- [ ] **Step 4: Create lead anchor adapter**

Create `backend/app/tools/lead_anchor.py`:

```python
from __future__ import annotations

from pathlib import Path

from app.core.sparse_lead import anchors_from_metadata
from app.tools.base import ParsedToolOutput, ToolCommand, ToolRunResult, read_json_artifact, write_json_artifact


class LeadAnchorAdapter:
    name = "lead_anchor_extraction"

    def run(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int, metadata: dict | None = None):
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / "lead_anchors.json"
        write_json_artifact(
            artifact,
            {
                "target_type": target_type,
                "target_value": target_value,
                "metadata": metadata or {},
            },
        )
        return ToolRunResult(
            command=ToolCommand(
                args=["lead_anchor_extraction", target_value],
                cwd=workdir,
                expected_artifact=artifact,
                timeout_seconds=timeout_seconds,
            ),
            returncode=0,
            stdout_excerpt="lead anchors extracted",
            stderr_excerpt="",
        )

    def parse_artifact(self, artifact_path: Path, target_value: str):
        payload = read_json_artifact(artifact_path)
        bundle = anchors_from_metadata(target_value, payload.get("metadata", {}))
        return ParsedToolOutput(
            tool=self.name,
            target_type=payload.get("target_type", "sparse_lead"),
            target_value=target_value,
            entities=bundle.entities,
            evidence=bundle.evidence,
            relationships=bundle.relationships,
        )
```

- [ ] **Step 5: Register adapter**

In `backend/app/tools/__init__.py`, import and register the adapter. Add:

```python
from app.tools.lead_anchor import LeadAnchorAdapter
```

Add to the adapter map:

```python
    "lead_anchor_extraction": LeadAnchorAdapter,
```

- [ ] **Step 6: Pass investigation metadata into adapter.run**

In `_execute_job()` in `backend/app/services/worker.py`, update the adapter `run()` call. Replace:

```python
            run_result = adapter.run(
                target_type=job["target_type"],
                target_value=job["target_value"],
                workdir=workdir,
                timeout_seconds=timeout,
            )
```

with:

```python
            run_kwargs = {
                "target_type": job["target_type"],
                "target_value": job["target_value"],
                "workdir": workdir,
                "timeout_seconds": timeout,
            }
            if job["tool_name"] == "lead_anchor_extraction":
                run_kwargs["metadata"] = detail.get("metadata", {})
            run_result = adapter.run(**run_kwargs)
```

- [ ] **Step 7: Run focused worker tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_worker
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/sparse_lead.py backend/app/tools/lead_anchor.py backend/app/tools/__init__.py backend/app/services/worker.py backend/tests/test_worker.py
git commit -m "feat: extract sparse lead anchors"
```

Skip commit if this directory is not a git repository.

## Task 5: Add Frontend Sparse Lead Intake Form

**Files:**
- Create: `frontend/src/sparse-lead.ts`
- Create: `frontend/scripts/test-sparse-lead.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/labels.ts`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Add frontend helper test**

Create `frontend/scripts/test-sparse-lead.ts`:

```typescript
import assert from "node:assert/strict";

import { buildSparseLeadMetadata, parseLines } from "../src/sparse-lead.ts";

assert.deepEqual(
  parseLines("Induction Cookers\n\n Gas Cooktops "),
  ["Induction Cookers", "Gas Cooktops"],
  "parseLines should trim blank textarea rows",
);

const metadata = buildSparseLeadMetadata({
  platform: "Alibaba",
  lead_display_name: "Long Way",
  member_id: "in19034126503jgqn",
  country_region: "IN",
  registration_year: "2023",
  company_name_raw: "Long Way",
  privacy_state: "email_phone_hidden",
  categoriesText: "Induction Cookers\nGas Cooktops",
  recentRfqsText: "2200W Electric Cook Top",
  operator_notes: "visible profile only",
});

assert.equal(metadata.platform, "Alibaba");
assert.deepEqual(metadata.categories, ["Induction Cookers", "Gas Cooktops"]);
assert.deepEqual(metadata.recent_rfqs, ["2200W Electric Cook Top"]);

console.log("sparse lead helper checks passed");
```

- [ ] **Step 2: Run helper test and verify failure**

Run:

```bash
cd frontend
node --experimental-strip-types ./scripts/test-sparse-lead.ts
```

Expected: FAIL because `src/sparse-lead.ts` does not exist.

- [ ] **Step 3: Create sparse lead frontend helpers**

Create `frontend/src/sparse-lead.ts`:

```typescript
export type SparseLeadForm = {
  platform: string;
  lead_display_name: string;
  member_id: string;
  country_region: string;
  registration_year: string;
  company_name_raw: string;
  privacy_state: string;
  categoriesText: string;
  recentRfqsText: string;
  operator_notes: string;
};

export type SparseLeadMetadata = {
  platform: string;
  lead_display_name: string;
  member_id: string;
  country_region: string;
  registration_year: string;
  company_name_raw: string;
  privacy_state: string;
  categories: string[];
  recent_rfqs: string[];
  operator_notes: string;
};

export const defaultSparseLeadForm: SparseLeadForm = {
  platform: "Alibaba",
  lead_display_name: "",
  member_id: "",
  country_region: "",
  registration_year: "",
  company_name_raw: "",
  privacy_state: "email_phone_hidden",
  categoriesText: "",
  recentRfqsText: "",
  operator_notes: "",
};

export function parseLines(value: string) {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function buildSparseLeadMetadata(form: SparseLeadForm): SparseLeadMetadata {
  return {
    platform: form.platform.trim(),
    lead_display_name: form.lead_display_name.trim(),
    member_id: form.member_id.trim(),
    country_region: form.country_region.trim(),
    registration_year: form.registration_year.trim(),
    company_name_raw: form.company_name_raw.trim(),
    privacy_state: form.privacy_state.trim(),
    categories: parseLines(form.categoriesText),
    recent_rfqs: parseLines(form.recentRfqsText),
    operator_notes: form.operator_notes.trim(),
  };
}

export function sparseLeadSeedValue(metadata: SparseLeadMetadata) {
  const displayName = metadata.lead_display_name || metadata.company_name_raw || "未命名弱线索";
  return metadata.member_id ? `${displayName} / ${metadata.member_id}` : displayName;
}
```

- [ ] **Step 4: Add sparse lead types**

In `frontend/src/types.ts`, add:

```typescript
  metadata?: Record<string, unknown>;
```

to the `Investigation` type.

- [ ] **Step 5: Add labels**

In `frontend/src/labels.ts`, add to `targetTypeLabels`:

```typescript
  sparse_lead: "弱线索买家",
```

Add to `agentRoleLabels`:

```typescript
  lead_intake_agent: "线索录入 Agent",
  search_planning_agent: "检索规划 Agent",
```

Add to `entityTypeLabels`:

```typescript
  company_name_raw: "原始公司字段",
  country_region: "国家/地区",
  platform: "平台",
  platform_member_id: "平台会员 ID",
  privacy_state: "隐私状态",
  purchase_category: "采购类目",
  registration_year: "注册年份",
  rfq_text: "RFQ 文本",
```

Add to `evidenceKindLabels`:

```typescript
  platform_profile_screenshot: "平台资料截图",
  visible_buyer_anchor: "可见买家锚点",
  candidate_public_record: "候选公开记录",
  identity_match_signal: "身份匹配信号",
  identity_mismatch_signal: "身份不匹配信号",
  rfq_intent_signal: "RFQ 意图信号",
  rfq_noise_signal: "RFQ 噪声信号",
```

Add to `relationshipTypeLabels`:

```typescript
  lead_has_platform_anchor: "线索包含平台锚点",
```

- [ ] **Step 6: Wire form state in main.tsx**

In `frontend/src/main.tsx`, update the import from sparse lead helper:

```typescript
import { buildSparseLeadMetadata, defaultSparseLeadForm, sparseLeadSeedValue } from "./sparse-lead";
```

Add state inside `App()`:

```typescript
  const [sparseLeadForm, setSparseLeadForm] = useState(defaultSparseLeadForm);
```

Update the default form if desired:

```typescript
  const [form, setForm] = useState({ name: "example.com 深度调查", seed_type: "domain", seed_value: "example.com", strategy: "deep" });
```

No default change is required.

- [ ] **Step 7: Build sparse lead payload on create**

In `createInvestigation()`, before `fetch`, add:

```typescript
    const sparseMetadata = form.seed_type === "sparse_lead" ? buildSparseLeadMetadata(sparseLeadForm) : null;
    const payload = sparseMetadata
      ? {
          ...form,
          name: form.name || `弱线索买家：${sparseMetadata.lead_display_name || sparseMetadata.member_id}`,
          seed_value: sparseLeadSeedValue(sparseMetadata),
          metadata: sparseMetadata,
        }
      : form;
```

Replace `body: JSON.stringify(form)` with:

```typescript
body: JSON.stringify(payload)
```

- [ ] **Step 8: Add target option**

In the target type `<select>`, add:

```tsx
<option value="sparse_lead">弱线索买家</option>
```

- [ ] **Step 9: Add conditional sparse lead fields**

After the target value input in the form, add:

```tsx
            {form.seed_type === "sparse_lead" ? (
              <div className="sparse-lead-grid">
                <label>平台<input value={sparseLeadForm.platform} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, platform: e.target.value })} /></label>
                <label>显示名<input value={sparseLeadForm.lead_display_name} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, lead_display_name: e.target.value })} /></label>
                <label>会员 ID<input className="mono" value={sparseLeadForm.member_id} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, member_id: e.target.value })} /></label>
                <label>国家/地区<input value={sparseLeadForm.country_region} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, country_region: e.target.value })} /></label>
                <label>注册年份<input value={sparseLeadForm.registration_year} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, registration_year: e.target.value })} /></label>
                <label>原始公司字段<input value={sparseLeadForm.company_name_raw} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, company_name_raw: e.target.value })} /></label>
                <label className="wide-field">类目<textarea value={sparseLeadForm.categoriesText} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, categoriesText: e.target.value })} /></label>
                <label className="wide-field">近期 RFQ<textarea value={sparseLeadForm.recentRfqsText} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, recentRfqsText: e.target.value })} /></label>
                <label className="wide-field">备注<textarea value={sparseLeadForm.operator_notes} onChange={(e) => setSparseLeadForm({ ...sparseLeadForm, operator_notes: e.target.value })} /></label>
              </div>
            ) : null}
```

- [ ] **Step 10: Add minimal CSS**

In `frontend/src/styles.css`, add:

```css
.sparse-lead-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.sparse-lead-grid .wide-field {
  grid-column: 1 / -1;
}

.sparse-lead-grid textarea {
  min-height: 78px;
  resize: vertical;
}

@media (max-width: 760px) {
  .sparse-lead-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 11: Run frontend helper test and build**

Run:

```bash
cd frontend
node --experimental-strip-types ./scripts/test-sparse-lead.ts
npm run build
```

Expected: both PASS.

- [ ] **Step 12: Commit**

```bash
git add frontend/src/sparse-lead.ts frontend/scripts/test-sparse-lead.ts frontend/src/types.ts frontend/src/labels.ts frontend/src/main.tsx frontend/src/styles.css
git commit -m "feat: add sparse lead intake form"
```

Skip commit if this directory is not a git repository.

## Task 6: Add Analyst Stage Strip

**Files:**
- Modify: `frontend/src/sparse-lead.ts`
- Modify: `frontend/scripts/test-sparse-lead.ts`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add failing stage helper tests**

Append to `frontend/scripts/test-sparse-lead.ts`:

```typescript
import { sparseLeadStages } from "../src/sparse-lead.ts";

const stages = sparseLeadStages([
  { tool_name: "lead_anchor_extraction", status: "COMPLETED" },
  { tool_name: "constrained_query_planning", status: "QUEUED" },
  { tool_name: "analysis_judgement", status: "QUEUED" },
]);

assert.equal(stages[0].label, "锚点提取");
assert.equal(stages[0].status, "COMPLETED");
assert.equal(stages[1].label, "约束检索");
assert.equal(stages.at(-1)?.label, "定向采集");
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
cd frontend
node --experimental-strip-types ./scripts/test-sparse-lead.ts
```

Expected: FAIL because `sparseLeadStages` does not exist.

- [ ] **Step 3: Implement stage helper**

In `frontend/src/sparse-lead.ts`, add:

```typescript
type StageJob = {
  tool_name: string;
  status: string;
};

export function sparseLeadStages(jobs: StageJob[]) {
  const byTool = new Map(jobs.map((job) => [job.tool_name, job.status]));
  return [
    { key: "anchors", label: "锚点提取", status: byTool.get("lead_anchor_extraction") ?? "QUEUED" },
    { key: "queries", label: "约束检索", status: byTool.get("constrained_query_planning") ?? "QUEUED" },
    { key: "candidates", label: "候选发现", status: byTool.get("candidate_business_discovery") ?? "QUEUED" },
    { key: "identity", label: "身份匹配", status: byTool.get("identity_match_review") ?? "QUEUED" },
    { key: "ach", label: "ACH 判断", status: byTool.get("analysis_judgement") ?? "QUEUED" },
    { key: "bluf", label: "BLUF 报告", status: byTool.get("analysis_judgement") ?? "QUEUED" },
    { key: "collection", label: "定向采集", status: byTool.get("analysis_judgement") ?? "QUEUED" },
  ];
}

export function isSparseLeadInvestigation(seedType: string) {
  return seedType === "sparse_lead";
}
```

- [ ] **Step 4: Render stage strip**

In `frontend/src/main.tsx`, update sparse lead imports:

```typescript
import { buildSparseLeadMetadata, defaultSparseLeadForm, isSparseLeadInvestigation, sparseLeadSeedValue, sparseLeadStages } from "./sparse-lead";
```

Inside the selected detail column, place this after the summary line and before `QueuePanel`:

```tsx
                {isSparseLeadInvestigation(selected.seed_type) ? (
                  <div className="stage-strip">
                    {sparseLeadStages(selected.jobs ?? []).map((stage) => (
                      <span key={stage.key} className={`stage-chip stage-${stage.status.toLowerCase()}`}>
                        {stage.label}
                      </span>
                    ))}
                  </div>
                ) : null}
```

- [ ] **Step 5: Add stage CSS**

In `frontend/src/styles.css`, add:

```css
.stage-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0;
}

.stage-chip {
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--muted);
  font-size: 12px;
  padding: 4px 8px;
}

.stage-completed {
  border-color: rgba(22, 163, 74, 0.35);
  color: #15803d;
}

.stage-running {
  border-color: rgba(2, 132, 199, 0.4);
  color: #0369a1;
}

.stage-failed,
.stage-blocked,
.stage-partial_failed {
  border-color: rgba(220, 38, 38, 0.35);
  color: #b91c1c;
}
```

If `--border` or `--muted` do not exist in `styles.css`, use the closest existing border and muted color variables or literal colors already used in that file.

- [ ] **Step 6: Run frontend checks**

Run:

```bash
cd frontend
node --experimental-strip-types ./scripts/test-sparse-lead.ts
npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/sparse-lead.ts frontend/scripts/test-sparse-lead.ts frontend/src/main.tsx frontend/src/styles.css
git commit -m "feat: show sparse lead analyst stages"
```

Skip commit if this directory is not a git repository.

## Task 7: Verification Script And Full Regression

**Files:**
- Modify: `scripts/verify.sh`
- Modify: `README.md`
- Modify: `docs/AGENT_PROTOCOL.md`

- [ ] **Step 1: Update verification script**

In `scripts/verify.sh`, add this line before `npm run build`:

```bash
node --experimental-strip-types ./scripts/test-sparse-lead.ts
```

The frontend section should become:

```bash
cd "$ROOT_DIR/frontend"
npm run check:ui-copy
node --experimental-strip-types ./scripts/test-ui-state.ts
node --experimental-strip-types ./scripts/test-graph-helpers.ts
node --experimental-strip-types ./scripts/test-investigation-bundle.ts
node --experimental-strip-types ./scripts/test-sparse-lead.ts
npm run build
```

- [ ] **Step 2: Update README target type list**

In `README.md`, update the current capability bullet:

```markdown
- 多目标类型：`company`、`sparse_lead`、`domain`、`subdomain`、`email`、`username`、`phone`、`ip`、`url`、`profile_url`。
```

Add a short sparse lead note near the Alibaba/CRM paragraph:

```markdown
弱线索买家任务使用 `sparse_lead` 类型，先把截图或 CRM 可见字段写成平台锚点，再做候选主体发现、身份匹配评分、ACH 场景判断和 BLUF 报告。系统不会绕过平台隐私设置，也不会把公开公司负责人自动等同为账号操作者。
```

- [ ] **Step 3: Update Agent Protocol target types**

In `docs/AGENT_PROTOCOL.md`, add to Target Types:

```markdown
- `sparse_lead`: weak Alibaba/CRM/platform buyer lead with multiple visible anchors but no confirmed company, email, phone, or domain.
```

Add this note under the sparse Alibaba SOP:

```markdown
When the operator can enter screenshot anchors directly, create the task as `seed_type=sparse_lead` and put platform, display name, member ID, country, raw company field, categories, and RFQs in investigation metadata. Agents must write those anchors before public candidate discovery.
```

- [ ] **Step 4: Run full verification**

Run:

```bash
bash scripts/verify.sh
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/verify.sh README.md docs/AGENT_PROTOCOL.md
git commit -m "docs: document sparse lead intake workflow"
```

Skip commit if this directory is not a git repository.

## Self-Review

Spec coverage:

- New `sparse_lead` target type is covered in Tasks 1, 2, and 3.
- Metadata anchor storage is covered in Task 2.
- Role-based sparse lead route matrix is covered in Task 3.
- Anchor extraction into entities/evidence/relationships is covered in Task 4.
- UI intake form is covered in Task 5.
- Analyst stage model is covered in Task 6.
- Verification and docs are covered in Task 7.
- Privacy-safe boundaries remain in the design doc and protocol updates; no task adds hidden-contact extraction.

Placeholder scan:

- The plan contains no TBD/TODO placeholders.
- Each code-changing step includes concrete code or exact replacement guidance.

Type consistency:

- Backend target type is consistently `sparse_lead`.
- Metadata keys use `lead_display_name`, `member_id`, `country_region`, `registration_year`, `company_name_raw`, `privacy_state`, `categories`, and `recent_rfqs`.
- Stage job names match the route matrix: `lead_anchor_extraction`, `constrained_query_planning`, `candidate_business_discovery`, `identity_match_review`, `analysis_judgement`.
