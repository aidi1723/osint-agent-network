# Gap-to-Tool Follow-up Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every `NEEDS_REVIEW` or partially blocked investigation explain concrete gaps, required evidence, available tools, unavailable tools, and next automatic/manual collection actions.

**Architecture:** Extend the existing `backend/app/core/gap_followups.py` module into a deterministic gap analysis and tool-planning layer. The worker will call this planner after analysis, queue only ready non-duplicate follow-up jobs, and expose the planner output through investigation detail and reports. No new external service or LLM dependency is introduced.

**Tech Stack:** Python 3.11, standard `unittest`, existing `MemoryStore` / `SQLiteStore`, existing tool registry and tool health modules, existing background worker.

---

## File Map

- Modify: `backend/app/core/gap_followups.py`
  - Owns gap explanation, gap-to-tool mapping, health-aware tool planning, and conversion to `PlannedJob`.
- Create: `backend/tests/test_gap_to_tool_planner.py`
  - Unit tests for gap analysis, tool status mapping, duplicate prevention, exhausted gaps, and planned jobs.
- Modify: `backend/app/services/worker.py`
  - Uses the enhanced planner, records richer worker events, and tracks queued/blocked/exhausted gap summary counters.
- Modify: `backend/app/services/store.py`
  - Adds computed `gap_analysis`, `gap_tool_plan`, and `gap_followup_summary` to investigation detail.
- Modify: `backend/app/core/quality.py`
  - Adds report section rendering for "卡点与补采计划".
- Modify: `backend/tests/test_worker.py`
  - Verifies worker queues ready gap follow-ups and records unavailable tools without marking generic failure.
- Modify: `backend/tests/test_quality_gate.py`
  - Verifies structured report includes blockers, missing evidence, and suggested next actions.
- Modify: `docs/NEXT_PHASE_ROADMAP_2026-07-06.md`
  - Marks progress and links this implementation plan after completion.
- Modify: `docs/UPDATE_LOG.md`
  - Records implementation and verification evidence.

---

### Task 1: Add Gap Analysis Contract

**Files:**
- Modify: `backend/app/core/gap_followups.py`
- Create: `backend/tests/test_gap_to_tool_planner.py`

- [ ] **Step 1: Write failing gap analysis tests**

Add `backend/tests/test_gap_to_tool_planner.py`:

```python
import unittest

from app.core.gap_followups import build_gap_analysis


class GapToToolPlannerTests(unittest.TestCase):
    def test_build_gap_analysis_explains_blocking_quality_keys(self):
        detail = {
            "id": "task-1",
            "name": "Example Manufacturing LLC",
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "quality_assessment": {
                "missing_keys": ["official_website", "decision_maker"],
                "blocking_keys": ["official_website", "decision_maker"],
            },
            "intelligence_memory": {
                "collection_gaps": [
                    {"key": "decision_maker", "label": "决策人", "reason": "缺少负责人证据"}
                ]
            },
            "entities": [],
            "evidence_ledger": [],
            "jobs": [],
        }

        gaps = build_gap_analysis(detail)

        by_key = {item["gap_key"]: item for item in gaps}
        self.assertEqual(by_key["official_website"]["severity"], "blocking")
        self.assertIn("official", " ".join(by_key["official_website"]["missing_evidence"]).lower())
        self.assertEqual(by_key["decision_maker"]["severity"], "blocking")
        self.assertIn("responsible", by_key["decision_maker"]["why_it_matters"].lower())
        self.assertTrue(by_key["decision_maker"]["manual_review_hint"])

    def test_unknown_gap_gets_manual_review_explanation(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "quality_assessment": {
                "missing_keys": ["custom_unknown_gap"],
                "blocking_keys": ["custom_unknown_gap"],
            },
            "intelligence_memory": {"collection_gaps": []},
            "jobs": [],
        }

        gaps = build_gap_analysis(detail)

        self.assertEqual(gaps[0]["gap_key"], "custom_unknown_gap")
        self.assertEqual(gaps[0]["severity"], "blocking")
        self.assertIn("manual", gaps[0]["manual_review_hint"].lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_gap_to_tool_planner.py' -v
```

Expected:

- FAIL because `build_gap_analysis` does not exist.

- [ ] **Step 3: Implement minimal gap analysis**

In `backend/app/core/gap_followups.py`, add:

```python
GAP_EXPLANATIONS = {
    "official_website": {
        "label": "Official website",
        "current_state": "No accepted official website or domain is linked to the target.",
        "missing_evidence": [
            "Official domain or URL tied to the target",
            "Page title or snippet showing target identity",
            "Source URL for review",
        ],
        "why_it_matters": "The task cannot be completed confidently without an official source boundary.",
        "manual_review_hint": "Inspect the company website, public registry, or trusted directory if automated search remains inconclusive.",
    },
    "decision_maker": {
        "label": "Decision maker candidate",
        "current_state": "No accepted person, title, or profile evidence is linked to the company.",
        "missing_evidence": [
            "Official team/about/contact page naming a responsible person",
            "Public profile or news item linking the person to the company",
            "Independent evidence for title or purchasing authority",
        ],
        "why_it_matters": "The task cannot be completed without a reviewable person or role responsible for commercial follow-up.",
        "manual_review_hint": "If automated tools do not find a public profile, inspect the company website, public directories, or CRM context.",
    },
    "contact_channel": {
        "label": "Contact channel",
        "current_state": "No accepted email or phone channel is linked to the target.",
        "missing_evidence": [
            "Email or phone visible on an official or high-quality source",
            "Source URL connecting the contact to the target",
        ],
        "why_it_matters": "Commercial follow-up requires a contact channel with provenance.",
        "manual_review_hint": "Review contact, footer, privacy, and support pages manually if extraction fails.",
    },
    "business_scope": {
        "label": "Business scope",
        "current_state": "No accepted business or product scope is linked to the target.",
        "missing_evidence": [
            "Official product or service description",
            "Source-backed category or business scope",
        ],
        "why_it_matters": "The system needs scope evidence to judge relevance and buying fit.",
        "manual_review_hint": "Review product pages, company profiles, RFQs, and public catalogs.",
    },
}


def build_gap_analysis(detail: dict) -> list[dict]:
    assessment = detail.get("quality_assessment") or {}
    missing_keys = list(assessment.get("missing_keys") or [])
    blocking_keys = set(assessment.get("blocking_keys") or [])
    memory_gaps = (detail.get("intelligence_memory") or {}).get("collection_gaps") or []
    for gap in memory_gaps:
        key = str(gap.get("key") or "").strip()
        if key and key not in missing_keys:
            missing_keys.append(key)

    results = []
    for key in missing_keys:
        template = GAP_EXPLANATIONS.get(key)
        severity = "blocking" if key in blocking_keys else "important"
        if template is None:
            results.append(
                {
                    "gap_key": key,
                    "label": key.replace("_", " ").title(),
                    "severity": severity,
                    "current_state": "No deterministic gap explanation is registered for this key.",
                    "missing_evidence": ["Operator-defined evidence is required."],
                    "why_it_matters": "The quality gate cannot treat this gap as resolved without reviewable evidence.",
                    "manual_review_hint": "Manual review is required because no automatic tool mapping exists yet.",
                }
            )
            continue
        results.append({"gap_key": key, "severity": severity, **template})
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_gap_to_tool_planner.py' -v
```

Expected:

- `Ran 2 tests`
- `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/gap_followups.py backend/tests/test_gap_to_tool_planner.py
git commit -m "feat: explain investigation evidence gaps"
```

---

### Task 2: Add Health-Aware Gap Tool Plan

**Files:**
- Modify: `backend/app/core/gap_followups.py`
- Modify: `backend/tests/test_gap_to_tool_planner.py`

- [ ] **Step 1: Add failing tool plan tests**

Append tests:

```python
from app.core.gap_followups import build_gap_tool_plan


class GapToolPlanTests(unittest.TestCase):
    def test_tool_plan_marks_ready_and_unavailable_tools(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "quality_assessment": {
                "missing_keys": ["official_website"],
                "blocking_keys": ["official_website"],
            },
            "intelligence_memory": {"collection_gaps": []},
            "jobs": [],
        }
        health = {
            "official_site_search": {"status": "ready", "reason": "configured"},
            "httpx": {"status": "missing_executable", "reason": "executable not found: httpx"},
        }

        plan = build_gap_tool_plan(detail, tool_health_by_name=health)

        by_tool = {item["tool_name"]: item for item in plan}
        self.assertEqual(by_tool["official_site_search"]["status"], "ready")
        self.assertEqual(by_tool["httpx"]["status"], "missing_executable")
        self.assertIn("official website", by_tool["official_site_search"]["reason"].lower())

    def test_tool_plan_marks_duplicate_jobs_as_already_attempted(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "quality_assessment": {
                "missing_keys": ["official_website"],
                "blocking_keys": ["official_website"],
            },
            "intelligence_memory": {"collection_gaps": []},
            "jobs": [
                {
                    "tool_name": "official_site_search",
                    "target_type": "company",
                    "target_value": "Example Manufacturing LLC",
                    "status": "COMPLETED",
                    "depends_on": "completed:analysis_judgement;gap:official_website",
                }
            ],
        }
        health = {"official_site_search": {"status": "ready", "reason": "configured"}}

        plan = build_gap_tool_plan(detail, tool_health_by_name=health)

        official_search = next(item for item in plan if item["tool_name"] == "official_site_search")
        self.assertEqual(official_search["status"], "already_attempted")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_gap_to_tool_planner.py' -v
```

Expected:

- FAIL because `build_gap_tool_plan` does not exist.

- [ ] **Step 3: Implement minimal tool mapping**

Add mapping and planner in `backend/app/core/gap_followups.py`:

```python
GAP_TOOL_MAPPINGS = {
    "official_website": (
        {
            "tool_name": "official_site_search",
            "agent_role": "tool_agent",
            "target_type": "seed",
            "reason": "Find official website candidates before crawling pages.",
            "expected_evidence": ["official_site_candidate", "website_title", "source_snippet"],
        },
        {
            "tool_name": "httpx",
            "agent_role": "tool_agent",
            "target_type": "domain",
            "reason": "Probe candidate domains or URLs for live web evidence.",
            "expected_evidence": ["live_url", "title", "technology"],
        },
        {
            "tool_name": "katana",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Crawl candidate pages for contact, about, and business evidence.",
            "expected_evidence": ["business_page_url", "contact_page_url"],
        },
        {
            "tool_name": "official_site_extractor",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Extract identity, contact, scope, and decision-maker evidence from official pages.",
            "expected_evidence": ["company_identity", "contact", "business_scope"],
        },
    ),
    "decision_maker": (
        {
            "tool_name": "official_site_extractor",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Extract people, titles, and contact roles from official pages.",
            "expected_evidence": ["person_name", "job_title", "official_page_url"],
        },
        {
            "tool_name": "social_profile_search",
            "agent_role": "social_intel_agent",
            "target_type": "seed",
            "reason": "Find public profiles that may identify responsible people.",
            "expected_evidence": ["profile_url", "person_name", "company_link"],
        },
        {
            "tool_name": "company_news",
            "agent_role": "tool_agent",
            "target_type": "company",
            "reason": "Search public news for executives, managers, and buying signals.",
            "expected_evidence": ["news_url", "person_name", "role_or_quote"],
        },
    ),
    "contact_channel": (
        {
            "tool_name": "official_site_extractor",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Extract email and phone evidence from official pages.",
            "expected_evidence": ["email", "phone", "source_url"],
        },
        {
            "tool_name": "contact_discovery",
            "agent_role": "contact_discovery_agent",
            "target_type": "seed",
            "reason": "Use role-agent contact discovery to collect public contact pages and ownership boundaries.",
            "expected_evidence": ["verified_email", "verified_phone", "contact_page"],
        },
        {
            "tool_name": "theharvester",
            "agent_role": "tool_agent",
            "target_type": "domain",
            "reason": "Collect public emails and domain-linked contacts when a domain is known.",
            "expected_evidence": ["email", "domain_source"],
        },
    ),
    "business_scope": (
        {
            "tool_name": "company_osint",
            "agent_role": "enterprise_intel_agent",
            "target_type": "seed",
            "reason": "Collect company identity, public records, website, and business scope.",
            "expected_evidence": ["business_scope", "product_scope", "source_url"],
        },
        {
            "tool_name": "official_site_extractor",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Extract product and service scope from official pages.",
            "expected_evidence": ["product_scope", "business_scope"],
        },
    ),
}


def build_gap_tool_plan(detail: dict, tool_health_by_name: dict[str, dict] | None = None) -> list[dict]:
    tool_health_by_name = tool_health_by_name or {}
    seed_type = str(detail.get("seed_type") or "company")
    seed_value = str(detail.get("seed_value") or "")
    existing = {
        (
            str(job.get("tool_name") or ""),
            str(job.get("target_type") or ""),
            str(job.get("target_value") or ""),
            str(job.get("depends_on") or ""),
        )
        for job in detail.get("jobs", [])
    }
    plan = []
    for gap in build_gap_analysis(detail):
        gap_key = gap["gap_key"]
        for mapping in GAP_TOOL_MAPPINGS.get(gap_key, ()):
            target_type = _gap_mapping_target_type(mapping["target_type"], seed_type)
            target_value = seed_value
            depends_on = f"completed:analysis_judgement;gap:{gap_key}"
            health = tool_health_by_name.get(mapping["tool_name"], {})
            status = str(health.get("status") or "ready")
            if (mapping["tool_name"], target_type, target_value, depends_on) in existing:
                status = "already_attempted"
            plan.append(
                {
                    "gap_key": gap_key,
                    "tool_name": mapping["tool_name"],
                    "agent_role": mapping["agent_role"],
                    "target_type": target_type,
                    "target_value": target_value,
                    "status": status,
                    "reason": mapping["reason"],
                    "expected_evidence": list(mapping["expected_evidence"]),
                    "depends_on": depends_on,
                    "health_reason": str(health.get("reason") or ""),
                }
            )
    return plan


def _gap_mapping_target_type(value: str, seed_type: str) -> str:
    if value == "seed":
        return seed_type
    return value
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_gap_to_tool_planner.py' -v
```

Expected:

- All gap planner tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/gap_followups.py backend/tests/test_gap_to_tool_planner.py
git commit -m "feat: map evidence gaps to tool actions"
```

---

### Task 3: Convert Ready Tool Plan Items To Planned Jobs

**Files:**
- Modify: `backend/app/core/gap_followups.py`
- Modify: `backend/tests/test_gap_to_tool_planner.py`

- [ ] **Step 1: Add failing planned-job tests**

Append:

```python
from app.core.gap_followups import plan_gap_followup_jobs


class GapPlannedJobTests(unittest.TestCase):
    def test_plan_gap_followup_jobs_only_queues_ready_actions(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "quality_assessment": {
                "missing_keys": ["official_website"],
                "blocking_keys": ["official_website"],
            },
            "intelligence_memory": {"collection_gaps": []},
            "jobs": [],
        }
        health = {
            "official_site_search": {"status": "ready", "reason": "configured"},
            "httpx": {"status": "missing_executable", "reason": "executable not found"},
        }

        jobs = plan_gap_followup_jobs(detail, tool_health_by_name=health)

        self.assertTrue(any(job.tool_name == "official_site_search" for job in jobs))
        self.assertFalse(any(job.tool_name == "httpx" for job in jobs))
        self.assertTrue(all("gap:official_website" in job.depends_on for job in jobs))
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_gap_to_tool_planner.py' -v
```

Expected:

- FAIL because `plan_gap_followup_jobs()` does not accept `tool_health_by_name`.

- [ ] **Step 3: Update `plan_gap_followup_jobs()`**

Change the signature:

```python
def plan_gap_followup_jobs(detail: dict, tool_health_by_name: dict[str, dict] | None = None) -> list[PlannedJob]:
```

At the top of the function, build the tool plan:

```python
tool_plan = build_gap_tool_plan(detail, tool_health_by_name=tool_health_by_name)
ready_items = [item for item in tool_plan if item["status"] == "ready"]
if ready_items:
    planned = [
        PlannedJob(
            tool_name=item["tool_name"],
            target_type=item["target_type"],
            target_value=item["target_value"],
            depth=3,
            agent_role=item["agent_role"],
            output_contract="entities,evidence,relationships",
            depends_on=item["depends_on"],
        )
        for item in ready_items
    ]
    planned.append(
        PlannedJob(
            tool_name="identity_match_review" if str(detail.get("seed_type") or "") == "sparse_lead" else "cross_verification",
            target_type=str(detail.get("seed_type") or "company"),
            target_value=str(detail.get("seed_value") or ""),
            depth=4,
            agent_role="cross_verification_agent",
            output_contract="claims,evidence,relationships: gap_followup_verification, confidence_adjustments",
            depends_on="completed:analysis_judgement;gap:verification",
        )
    )
    planned.append(
        PlannedJob(
            tool_name="analysis_judgement",
            target_type=str(detail.get("seed_type") or "company"),
            target_value=str(detail.get("seed_value") or ""),
            depth=5,
            agent_role="analysis_judgement_agent",
            output_contract="claims,graph_slots,report: updated PIR, ACH, BLUF, risk_summary, directed_collection",
            depends_on="cross_verification;identity_match_review;gap:reanalyze",
        )
    )
    return planned
```

Keep the existing template fallback only if `ready_items` is empty and there are no known mappings.

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_gap_to_tool_planner.py' -v
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_worker.py' -v
```

Expected:

- Gap planner tests pass.
- Existing worker tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/gap_followups.py backend/tests/test_gap_to_tool_planner.py
git commit -m "feat: queue ready gap followup tools"
```

---

### Task 4: Expose Gap Planner Output In Investigation Detail

**Files:**
- Modify: `backend/app/services/store.py`
- Modify: `backend/tests/test_agent_protocol.py` or create focused tests in `backend/tests/test_gap_to_tool_planner.py`

- [ ] **Step 1: Add failing detail-output test**

Add to `backend/tests/test_gap_to_tool_planner.py`:

```python
from app.services.store import MemoryStore


class GapDetailOutputTests(unittest.TestCase):
    def test_investigation_detail_includes_gap_plan(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Example Manufacturing LLC",
            seed_type="company",
            seed_value="Example Manufacturing LLC",
            strategy_name="standard",
        )
        store.complete_task(
            investigation.id,
            agent_id="local-analysis-agent",
            status="NEEDS_REVIEW",
            summary="Needs review.",
            report_markdown="",
            confidence=0.4,
        )

        detail = store.get_investigation(investigation.id)

        self.assertIn("gap_analysis", detail)
        self.assertIn("gap_tool_plan", detail)
        self.assertIn("gap_followup_summary", detail)
        self.assertIsInstance(detail["gap_analysis"], list)
        self.assertIsInstance(detail["gap_tool_plan"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_gap_to_tool_planner.py' -v
```

Expected:

- FAIL because detail lacks gap planner fields.

- [ ] **Step 3: Add computed fields in store detail builders**

In `backend/app/services/store.py`, import:

```python
from app.core.gap_followups import build_gap_analysis, build_gap_followup_summary, build_gap_tool_plan
```

Where detail currently adds `quality_assessment`, add:

```python
data["gap_analysis"] = build_gap_analysis(data)
data["gap_tool_plan"] = build_gap_tool_plan(data)
data["gap_followup_summary"] = build_gap_followup_summary(data["gap_tool_plan"], data["gap_analysis"])
```

Apply the same logic to both `MemoryStore` and `SQLiteStore` detail paths where
`quality_assessment` is computed.

- [ ] **Step 4: Implement summary helper**

In `backend/app/core/gap_followups.py`, add:

```python
def build_gap_followup_summary(tool_plan: list[dict], gap_analysis: list[dict]) -> dict:
    summary = {
        "total_gaps": len(gap_analysis),
        "blocking_gaps": len([gap for gap in gap_analysis if gap.get("severity") == "blocking"]),
        "ready": 0,
        "queued": 0,
        "already_attempted": 0,
        "blocked_by_config": 0,
        "exhausted": 0,
        "manual_review_required": 0,
    }
    for item in tool_plan:
        status = str(item.get("status") or "")
        if status in summary:
            summary[status] += 1
        if status in {"missing_config", "missing_executable", "credential_blocked", "disabled"}:
            summary["blocked_by_config"] += 1
    mapped_gap_keys = {item.get("gap_key") for item in tool_plan}
    for gap in gap_analysis:
        if gap.get("gap_key") not in mapped_gap_keys:
            summary["manual_review_required"] += 1
    return summary
```

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_gap_to_tool_planner.py' -v
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_agent_protocol.py' -v
```

Expected:

- Tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/gap_followups.py backend/app/services/store.py backend/tests/test_gap_to_tool_planner.py
git commit -m "feat: expose gap plans in investigation detail"
```

---

### Task 5: Render Gap Plan In Reports

**Files:**
- Modify: `backend/app/core/quality.py`
- Modify: `backend/tests/test_quality_gate.py`

- [ ] **Step 1: Add failing report test**

Add to `backend/tests/test_quality_gate.py`:

```python
def test_structured_report_includes_gap_to_tool_plan(self):
    detail = {
        "name": "Example Manufacturing LLC",
        "seed_type": "company",
        "seed_value": "Example Manufacturing LLC",
        "entities": [],
        "evidence_ledger": [],
        "facts": [],
        "relationships": [],
        "jobs": [],
        "quality_assessment": {
            "missing_keys": ["official_website"],
            "blocking_keys": ["official_website"],
        },
        "gap_analysis": [
            {
                "gap_key": "official_website",
                "label": "Official website",
                "severity": "blocking",
                "current_state": "No accepted official website.",
                "missing_evidence": ["Official domain or URL tied to the target"],
                "why_it_matters": "Official source boundary is required.",
                "manual_review_hint": "Inspect trusted directories manually.",
            }
        ],
        "gap_tool_plan": [
            {
                "gap_key": "official_website",
                "tool_name": "official_site_search",
                "status": "ready",
                "reason": "Find official website candidates before crawling pages.",
            }
        ],
    }

    report = render_structured_report(detail, build_quality_assessment(detail))

    self.assertIn("## 卡点与补采计划", report)
    self.assertIn("Official website", report)
    self.assertIn("official_site_search", report)
    self.assertIn("Official domain or URL", report)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_quality_gate.py' -v
```

Expected:

- FAIL because the report section is missing.

- [ ] **Step 3: Add report rendering**

In `backend/app/core/quality.py`, inside `render_structured_report()`, after
`## 情报缺口`, add:

```python
    lines.extend(["", "## 卡点与补采计划"])
    gap_analysis = detail.get("gap_analysis") or []
    gap_tool_plan = detail.get("gap_tool_plan") or []
    if gap_analysis:
        for gap in gap_analysis[:8]:
            lines.append(f"- [{gap.get('severity', 'important')}] {gap.get('label', gap.get('gap_key'))}：{gap.get('current_state', '')}")
            missing_evidence = gap.get("missing_evidence") or []
            if missing_evidence:
                lines.append(f"  - 需要证据：{'；'.join(str(item) for item in missing_evidence[:3])}")
            related_tools = [item for item in gap_tool_plan if item.get("gap_key") == gap.get("gap_key")]
            if related_tools:
                tool_bits = [
                    f"{item.get('tool_name')}({item.get('status')})"
                    for item in related_tools[:5]
                ]
                lines.append(f"  - 可用/受阻工具：{'; '.join(tool_bits)}")
            if gap.get("manual_review_hint"):
                lines.append(f"  - 人工复核：{gap.get('manual_review_hint')}")
    else:
        lines.append("- 暂无结构化卡点计划。")
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_quality_gate.py' -v
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_pdf_export.py' -v
```

Expected:

- Report tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/quality.py backend/tests/test_quality_gate.py
git commit -m "feat: render gap followup plan in reports"
```

---

### Task 6: Worker Event And Summary Integration

**Files:**
- Modify: `backend/app/services/worker.py`
- Modify: `backend/tests/test_worker.py`

- [ ] **Step 1: Add failing worker test**

Add to `backend/tests/test_worker.py`:

```python
def test_worker_records_gap_tool_plan_when_tools_unavailable(self):
    store = MemoryStore()
    investigation = store.create_investigation(
        name="Example Manufacturing LLC",
        seed_type="company",
        seed_value="Example Manufacturing LLC",
        strategy_name="standard",
    )
    store.complete_task(
        investigation.id,
        agent_id="analysis",
        status="NEEDS_REVIEW",
        summary="Needs more evidence.",
        report_markdown="",
        confidence=0.4,
    )

    with patch(
        "app.services.worker.build_tool_health_report",
        return_value={
            "summary": {},
            "tools": [
                {
                    "name": "official_site_search",
                    "status": "missing_config",
                    "reason": "OFFICIAL_SITE_SEARCH_BASE_URL is not configured",
                }
            ],
        },
    ):
        result = run_investigation_jobs(store, investigation.id, max_jobs=1, artifact_root=Path("/tmp/unused"))

    self.assertIn("gap_followup_summary", result)
    self.assertGreaterEqual(result["gap_followup_summary"]["blocked_by_config"], 1)
    detail = store.get_investigation(investigation.id)
    self.assertTrue(any("补采" in event["message"] for event in detail["events"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_worker.WorkerTests.test_worker_records_gap_tool_plan_when_tools_unavailable -v
```

Expected:

- FAIL because worker does not expose gap follow-up summary.

- [ ] **Step 3: Integrate tool health in worker gap queueing**

In `backend/app/services/worker.py`, import:

```python
from app.core.tool_health import build_tool_health_report
from app.core.gap_followups import build_gap_analysis, build_gap_followup_summary, build_gap_tool_plan, plan_gap_followup_jobs
```

Update `_queue_gap_followups()` to build health:

```python
health_report = build_tool_health_report()
health_by_name = {item["name"]: item for item in health_report.get("tools", [])}
gap_analysis = build_gap_analysis(detail)
gap_tool_plan = build_gap_tool_plan(detail, tool_health_by_name=health_by_name)
gap_summary = build_gap_followup_summary(gap_tool_plan, gap_analysis)
planned = plan_gap_followup_jobs(detail, tool_health_by_name=health_by_name)
```

When adding the event, include:

```python
"gap_followup_summary": gap_summary,
"blocked_tools": [
    {
        "gap_key": item["gap_key"],
        "tool_name": item["tool_name"],
        "status": item["status"],
        "reason": item.get("health_reason", ""),
    }
    for item in gap_tool_plan
    if item["status"] in {"missing_config", "missing_executable", "credential_blocked", "disabled"}
],
```

Add `gap_followup_summary` to the returned worker `summary`.

- [ ] **Step 4: Run worker tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_worker.py' -v
```

Expected:

- Worker tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/worker.py backend/tests/test_worker.py
git commit -m "feat: record gap tool planning in worker runs"
```

---

### Task 7: Documentation And Final Verification

**Files:**
- Modify: `docs/NEXT_PHASE_ROADMAP_2026-07-06.md`
- Modify: `docs/UPDATE_LOG.md`
- Modify: `docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md`

- [ ] **Step 1: Update roadmap progress**

Add a progress note under the Gap-to-Tool section:

```markdown
## Gap-to-Tool Progress

Implemented:

- `gap_analysis` in investigation detail;
- `gap_tool_plan` with ready/unavailable/already-attempted states;
- worker event recording for queued and blocked follow-up actions;
- report section `卡点与补采计划`.

Verification:

- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_gap_to_tool_planner.py' -v`
- `bash scripts/verify.sh`
```

- [ ] **Step 2: Run full verification**

Run:

```bash
bash scripts/verify.sh
```

Expected:

- backend tests pass;
- frontend helper checks pass;
- Vitest passes;
- production build passes.

- [ ] **Step 3: Run privacy scan**

Run:

```bash
git diff --unified=0 -- . | rg '^\+' | rg -n 'SRR|srrautopartsonline|ZAWIJA|Family Hospitality|Long Way|in19034126503jgqn|JAPAN SRR|Genuine Parts|f1224594|d9bf6c4b|6999088c|a8df5c87|83a1a3a5|22f8ead9|b1767a1a|565694ff|1ac0604c|fa08c83b|266d697c|e9b5e99b|/home/aidi|/Users/aidi|\bn100\b|192\.168\.|10\.[0-9]+\.|172\.(1[6-9]|2[0-9]|3[01])\.|Bearer [A-Za-z0-9._~-]{12,}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}'
```

Expected:

- no output.

- [ ] **Step 4: Commit docs and final changes**

```bash
git add docs/NEXT_PHASE_ROADMAP_2026-07-06.md docs/UPDATE_LOG.md docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md
git commit -m "docs: record gap to tool planner completion"
```

---

## Final Acceptance

- `NEEDS_REVIEW` investigation detail includes `gap_analysis`,
  `gap_tool_plan`, and `gap_followup_summary`.
- Reports include `## 卡点与补采计划`.
- Ready mapped tools are queued within budget.
- Unavailable tools are reported with specific reasons.
- Duplicate mapped tools are not queued again.
- Exhausted or unknown gaps include manual review hints.
- `bash scripts/verify.sh` passes.
- Added-line privacy scan has no findings.
