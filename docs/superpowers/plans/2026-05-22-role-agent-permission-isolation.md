# Role Agent Permission Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce reader / verifier / reporter responsibility boundaries for local role agents.

**Architecture:** Add a permissioned store wrapper in `backend/app/core/agent_permissions.py`, then route local role-agent writes through it. Worker scheduling and external HTTP agent permissions remain unchanged.

**Tech Stack:** Python standard library, existing `unittest`, existing local Worker and role-agent services.

---

## File Structure

- Create `backend/app/core/agent_permissions.py`: role tier mapping and permissioned store wrapper.
- Modify `backend/app/services/role_agents.py`: pass permissioned store into private role routines.
- Modify `backend/tests/test_role_agents.py`: add permission-boundary tests.
- Modify `README.md`: document local role-agent responsibility isolation.

---

### Task 1: Write Permission Boundary Tests

**Files:**
- Modify: `backend/tests/test_role_agents.py`

- [ ] **Step 1: Add imports**

Add:

```python
from app.core.agent_permissions import PermissionedRoleStore, tier_for_role
from app.services.role_agents import run_role_agent
```

- [ ] **Step 2: Add tests inside `LocalRoleAgentTests`**

Add near the top of the class:

```python
    def test_role_tier_mapping_separates_reader_verifier_and_reporter(self):
        self.assertEqual(tier_for_role("enterprise_intel_agent"), "reader")
        self.assertEqual(tier_for_role("cross_verification_agent"), "verifier")
        self.assertEqual(tier_for_role("analysis_judgement_agent"), "reporter")

    def test_reader_store_cannot_write_facts(self):
        store = MemoryStore()
        permissioned = PermissionedRoleStore(store, "reader")

        with self.assertRaises(PermissionError):
            permissioned.add_fact(
                investigation_id="task-1",
                statement="Example fact.",
                subject="Example",
                predicate="has_domain",
                object_value="example.com",
                status="CONFIRMED",
                confidence=0.9,
                admiralty_code="A-2",
                evidence_ids=["ev-1"],
            )

    def test_verifier_store_cannot_complete_task(self):
        store = MemoryStore()
        permissioned = PermissionedRoleStore(store, "verifier")

        with self.assertRaises(PermissionError):
            permissioned.complete_task(
                investigation_id="task-1",
                agent_id="agent",
                status="COMPLETED",
                summary="summary",
                report_markdown="# Report",
                confidence=0.8,
            )

    def test_reporter_store_cannot_collect_entities(self):
        store = MemoryStore()
        permissioned = PermissionedRoleStore(store, "reporter")

        with self.assertRaises(PermissionError):
            permissioned.add_entity("task-1", "domain", "example.com", "reporter", 0.8)

    def test_run_role_agent_uses_permissioned_store_for_collection(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Permissioned collection",
            seed_type="company",
            seed_value="Example LLC",
            strategy_name="quick",
        )
        result = run_role_agent(
            store,
            investigation.id,
            {
                "id": "job-enterprise",
                "tool_name": "company_osint",
                "agent_role": "enterprise_intel_agent",
            },
        )

        detail = store.get_investigation(investigation.id)
        self.assertTrue(result.completed)
        self.assertIn(("company", "Example LLC"), {(item["type"], item["value"]) for item in detail["entities"]})
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_role_agents
```

Expected: import failure for `app.core.agent_permissions`.

---

### Task 2: Implement Permissioned Store

**Files:**
- Create `backend/app/core/agent_permissions.py`

- [ ] **Step 1: Create permission module**

Create:

```python
from __future__ import annotations

from typing import Any


ROLE_TIERS = {
    "enterprise_intel_agent": "reader",
    "social_intel_agent": "reader",
    "contact_discovery_agent": "reader",
    "supply_chain_agent": "reader",
    "purchase_intent_agent": "reader",
    "news_intel_agent": "reader",
    "search_planning_agent": "reader",
    "cross_verification_agent": "verifier",
    "analysis_judgement_agent": "reporter",
}

ALLOWED_METHODS = {
    "reader": {
        "get_investigation",
        "add_entity",
        "add_evidence",
        "add_evidence_record",
        "add_relationship",
    },
    "verifier": {
        "get_investigation",
        "add_fact",
        "add_hypothesis",
        "score_hypotheses",
    },
    "reporter": {
        "get_investigation",
        "complete_task",
    },
}


def tier_for_role(agent_role: str) -> str:
    return ROLE_TIERS.get(agent_role, "reader")


class PermissionedRoleStore:
    def __init__(self, store, tier: str):
        if tier not in ALLOWED_METHODS:
            raise ValueError(f"unknown role tier: {tier}")
        self._store = store
        self._tier = tier

    @property
    def tier(self) -> str:
        return self._tier

    def __getattr__(self, name: str):
        if name not in ALLOWED_METHODS[self._tier]:
            raise PermissionError(f"{self._tier} role cannot call {name}")
        return getattr(self._store, name)
```

- [ ] **Step 2: Run role-agent tests to verify partial progress**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_role_agents
```

Expected: permission-wrapper tests pass, but role-agent execution is not yet using the wrapper.

---

### Task 3: Route Role Agents Through Permissioned Store

**Files:**
- Modify `backend/app/services/role_agents.py`

- [ ] **Step 1: Import permission helpers**

Add:

```python
from app.core.agent_permissions import PermissionedRoleStore, tier_for_role
```

- [ ] **Step 2: Wrap store in `run_role_agent`**

Change:

```python
tool_name = str(job.get("tool_name") or "")
if tool_name in {"cross_verification", "identity_match_review"}:
    _run_cross_verification(store, detail)
```

to:

```python
tool_name = str(job.get("tool_name") or "")
role = str(job.get("agent_role") or "")
permissioned_store = PermissionedRoleStore(store, tier_for_role(role))
if tool_name in {"cross_verification", "identity_match_review"}:
    _run_cross_verification(permissioned_store, detail)
```

Then pass `permissioned_store` to `_run_analysis_judgement`, `_run_query_planning`, and `_run_collection_role`.

- [ ] **Step 3: Adjust `_run_analysis_judgement` for verifier pre-work**

Current analysis ensures hypotheses and may score them before reporting. Under strict reporter permissions, reporter should not score hypotheses. Move hypothesis defaults and scoring responsibility to verifier phase only.

In `_run_analysis_judgement`, remove:

```python
    _ensure_default_hypotheses(store, detail)
    if detail.get("evidence_ledger"):
        try:
            store.score_hypotheses(investigation_id, _ach_evidence_items(detail))
        except ValueError:
            pass
```

Keep report rendering and `complete_task`.

- [ ] **Step 4: Ensure verifier creates hypotheses even without evidence items**

In `_run_cross_verification`, keep `_ensure_default_hypotheses(store, detail)`. This is allowed for verifier.

- [ ] **Step 5: Run role-agent tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_role_agents
```

Expected: all role-agent tests pass.

---

### Task 4: Documentation Update

**Files:**
- Modify `README.md`

- [ ] **Step 1: Add local isolation note**

In the `Agent / Skill 治理层` section, add:

```markdown
本地职责 Agent 还按责任分为 reader / verifier / reporter 三层：采集类角色只能写实体、证据和关系；交叉验证角色负责事实、假说和评分；分析评价角色只负责报告和任务完成。这是应用层责任隔离，不是 OS 级沙箱。
```

- [ ] **Step 2: Verify README note**

Run:

```bash
rg -n "reader / verifier / reporter|应用层责任隔离" README.md
```

Expected: note is present.

---

### Task 5: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run role-agent tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_role_agents
```

Expected: all tests pass.

- [ ] **Step 2: Run full verification**

Run:

```bash
bash scripts/verify.sh
```

Expected: full verification passes.

---

## Self-Review

- Scope matches the design: local responsibility isolation only.
- External HTTP agents are not affected.
- Worker scheduling is unchanged.
- Permission tests directly prove forbidden calls fail.
