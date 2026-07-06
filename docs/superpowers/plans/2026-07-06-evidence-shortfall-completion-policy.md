# Evidence Shortfall Completion Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic evidence-shortfall completion rules so investigations can distinguish strict completion, limited completion, continued automatic collection, human decision, environment blockage, and execution failure.

**Architecture:** Keep the existing quality gate as the strict completion authority. Add a pure `completion_policy` computation layer that reads quality assessment, gap analysis, tool readiness, entities, evidence, facts, and verification rows, then expose the computed policy through store details, worker summaries, and reports without a database migration.

**Tech Stack:** Python standard library, `unittest`, current in-memory and SQLite stores, existing worker orchestration, existing gap-followup and quality modules.

---

## File Structure

- Create `backend/app/core/completion_policy.py`
  - Owns `build_completion_policy(detail: dict) -> dict`.
  - Contains evidence-floor helpers, limitation classification, environment-blocked detection, and operator-action text.
- Create `backend/tests/test_completion_policy.py`
  - Covers strict, continue-collection, limited completion, non-waivable blockers, blocked environment, and store detail integration.
- Modify `backend/app/services/store.py`
  - Imports `build_completion_policy`.
  - Adds `completion_policy` after `quality_assessment`, `gap_analysis`, `gap_tool_plan`, and `gap_followup_summary` are computed for both MemoryStore and SQLiteStore details.
  - Updates `complete_task()` status selection to allow policy-backed limited completion.
- Modify `backend/app/services/worker.py`
  - Imports `build_completion_policy`.
  - Computes final policy after risk report and quality assessment.
  - Adds `completion_policy` and `completion_mode` to worker summary.
  - Uses policy recommended status for evidence-shortfall outcomes while preserving execution failures and high-risk review outcomes.
- Modify `backend/app/core/quality.py`
  - Renders a `## 完成策略` report section from `completion_policy`.
- Modify `backend/tests/test_worker.py`
  - Adds a worker regression for limited completion and policy summary exposure.
- Modify `backend/tests/test_quality_gate.py`
  - Adds report rendering assertions for completion mode, limitations, and operator next actions.
- Modify `docs/UPDATE_LOG.md`
  - Records implementation and verification results.

---

### Task 1: Core Completion Policy Contract

**Files:**
- Create: `backend/tests/test_completion_policy.py`
- Create: `backend/app/core/completion_policy.py`

- [ ] **Step 1: Write failing tests for the core policy modes**

Add this initial test file:

```python
import unittest

from app.core.completion_policy import build_completion_policy


def complete_company_detail() -> dict:
    return {
        "seed_type": "company",
        "seed_value": "Sample Auto Parts Co.",
        "entities": [
            {"type": "company", "value": "Sample Auto Parts Co.", "confidence": 0.9},
            {"type": "domain", "value": "example-target.test", "confidence": 0.82},
            {"type": "url", "value": "https://example-target.test", "confidence": 0.82},
            {"type": "email", "value": "sales@example-target.test", "confidence": 0.8},
            {"type": "phone", "value": "+1-555-0100", "confidence": 0.76},
            {"type": "address", "value": "Chicago, IL", "confidence": 0.72},
            {"type": "business_scope", "value": "auto parts distribution", "confidence": 0.8},
            {"type": "decision_maker", "value": "Export Manager", "confidence": 0.66},
        ],
        "evidence": [
            {"entity_value": "sales@example-target.test", "evidence_kind": "official_site_contact", "source_tool": "official_site_extractor"}
        ],
        "evidence_ledger": [
            {
                "id": "ev-1",
                "source_url": "https://example-target.test/contact",
                "source_type": "official_site_contact",
                "source_tool": "official_site_extractor",
                "admiralty_code": "A-2",
                "snippet": "Official contact page lists sales@example-target.test.",
            }
        ],
        "facts": [
            {
                "id": "fact-1",
                "statement": "Sample Auto Parts Co. lists a source-backed contact channel.",
                "predicate": "has_contact_email",
                "object": "sales@example-target.test",
                "status": "CONFIRMED",
                "promotion_stage": "ACCEPTED_FACT",
                "confidence": 0.82,
                "evidence_ids": ["ev-1"],
            }
        ],
        "hypotheses": [{"id": "h1", "status": "MOST_LIKELY", "support_score": 0.8}],
        "relationships": [{"from_value": "Sample Auto Parts Co.", "to_value": "sales@example-target.test"}],
        "report_markdown": "## BLUF\nSample Auto Parts Co. has source-backed contact and scope evidence.",
        "intelligence_requirements": {
            "pirs": [{"id": "pir_identity", "status": "ANSWERED"}],
            "eeis": [{"id": "eei_company_identity", "field_key": "company_identity", "required": True, "status": "CONFIRMED"}],
        },
        "cross_verification_matrix": [
            {"field_key": "company_identity", "status": "CONFIRMED", "candidate_value": "Sample Auto Parts Co."},
            {"field_key": "official_website", "status": "SUPPORTED", "candidate_value": "https://example-target.test"},
        ],
        "gap_followup_summary": {
            "total_gaps": 0,
            "blocking_gaps": 0,
            "ready": 0,
            "queued": 0,
            "already_attempted": 0,
            "blocked_by_config": 0,
            "exhausted": 0,
            "manual_review_required": 0,
        },
    }


class CompletionPolicyTests(unittest.TestCase):
    def test_strict_completion_recommends_completed(self):
        policy = build_completion_policy(complete_company_detail())

        self.assertEqual(policy["completion_mode"], "strict")
        self.assertEqual(policy["recommended_status"], "COMPLETED")
        self.assertTrue(policy["strict_completion_ready"])
        self.assertFalse(policy["manual_decision_required"])

    def test_ready_gap_tools_continue_collection(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "entities": [{"type": "company", "value": "Example Manufacturing LLC", "confidence": 0.72}],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "relationships": [],
            "hypotheses": [],
            "report_markdown": "",
            "quality_assessment": {
                "score": 20.0,
                "completion_ready": False,
                "missing_keys": ["official_website"],
                "blocking_keys": ["official_website"],
                "checks": [],
            },
            "gap_analysis": [{"gap_key": "official_website", "severity": "blocking"}],
            "gap_tool_plan": [
                {"gap_key": "official_website", "tool_name": "official_site_search", "status": "ready"}
            ],
            "gap_followup_summary": {
                "total_gaps": 1,
                "blocking_gaps": 1,
                "ready": 1,
                "queued": 0,
                "already_attempted": 0,
                "blocked_by_config": 0,
                "exhausted": 0,
                "manual_review_required": 0,
            },
        }

        policy = build_completion_policy(detail)

        self.assertEqual(policy["completion_mode"], "continue_collection")
        self.assertEqual(policy["recommended_status"], "NEEDS_REVIEW")
        self.assertFalse(policy["auto_exhausted"])
        self.assertIn("official_website", policy["remaining_blockers"])

    def test_environment_blocked_without_useful_evidence_recommends_blocked(self):
        detail = {
            "seed_type": "domain",
            "seed_value": "example-target.test",
            "entities": [],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "relationships": [],
            "hypotheses": [],
            "jobs": [{"tool_name": "httpx", "status": "BLOCKED"}],
            "report_markdown": "",
            "quality_assessment": {
                "score": 0.0,
                "completion_ready": False,
                "missing_keys": ["official_website", "evidence_ledger"],
                "blocking_keys": ["official_website", "evidence_ledger"],
                "checks": [],
            },
            "gap_analysis": [{"gap_key": "official_website", "severity": "blocking"}],
            "gap_tool_plan": [
                {
                    "gap_key": "official_website",
                    "tool_name": "httpx",
                    "status": "missing_executable",
                    "health_reason": "httpx command is not installed",
                }
            ],
            "gap_followup_summary": {
                "total_gaps": 1,
                "blocking_gaps": 1,
                "ready": 0,
                "queued": 0,
                "already_attempted": 0,
                "blocked_by_config": 1,
                "exhausted": 0,
                "manual_review_required": 0,
            },
        }

        policy = build_completion_policy(detail)

        self.assertEqual(policy["completion_mode"], "blocked_by_environment")
        self.assertEqual(policy["recommended_status"], "BLOCKED")
        self.assertTrue(policy["environment_blocked"])
        self.assertTrue(policy["manual_decision_required"])
```

- [ ] **Step 2: Run the core policy tests and verify they fail because the module is missing**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_completion_policy.py' -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.completion_policy'`.

- [ ] **Step 3: Add the initial policy implementation**

Create `backend/app/core/completion_policy.py`:

```python
from __future__ import annotations

from app.core.gap_followups import build_gap_analysis, build_gap_followup_summary, build_gap_tool_plan


SUPPORTED_VERIFICATION_STATUSES = {"CONFIRMED", "LIKELY", "SUPPORTED"}
BLOCKED_TOOL_STATUSES = {"missing_config", "missing_executable", "credential_blocked", "disabled"}
NON_ACCEPTABLE_BLOCKERS = {
    "company_identity",
    "official_website",
    "evidence_ledger",
    "fact_pool",
    "cross_verification",
    "bluf_report",
    "contact_channel",
    "unresolved_contradiction",
}
BASE_ACCEPTABLE_LIMITATIONS = {"decision_maker", "purchase_intent", "contact_phone", "contact_email"}


def build_completion_policy(detail: dict) -> dict:
    assessment = _quality_assessment(detail)
    planner_detail = {**detail, "quality_assessment": assessment}
    gap_analysis = list(detail.get("gap_analysis") or build_gap_analysis(planner_detail))
    gap_tool_plan = list(detail.get("gap_tool_plan") or build_gap_tool_plan({**planner_detail, "gap_analysis": gap_analysis}))
    gap_summary = dict(detail.get("gap_followup_summary") or build_gap_followup_summary(gap_tool_plan, gap_analysis))
    evidence_floor = _evidence_floor(detail)
    remaining_blockers = _remaining_blockers(assessment, gap_analysis)
    strict_ready = bool(assessment.get("completion_ready"))
    ready_tools = int(gap_summary.get("ready") or 0) + int(gap_summary.get("queued") or 0)
    auto_exhausted = ready_tools == 0 and bool(gap_analysis or remaining_blockers)
    environment_blocked = _environment_blocked(gap_tool_plan, gap_summary)
    useful_evidence = _has_useful_evidence(detail)
    acceptable_limitations = _acceptable_limitations(detail, remaining_blockers, evidence_floor)
    limited_ready = (
        not strict_ready
        and not ready_tools
        and bool(remaining_blockers)
        and all(evidence_floor.values())
        and not _has_non_acceptable_blocker(remaining_blockers, detail)
        and set(remaining_blockers).issubset(set(acceptable_limitations))
    )

    if strict_ready:
        return _policy(
            recommended_status="COMPLETED",
            completion_mode="strict",
            strict_ready=True,
            limited_ready=False,
            auto_exhausted=False,
            manual_decision_required=False,
            environment_blocked=False,
            reason="Strict quality gate is satisfied.",
            remaining_blockers=[],
            acceptable_limitations=[],
            operator_next_actions=[],
            evidence_floor=evidence_floor,
        )

    if ready_tools:
        return _policy(
            recommended_status="NEEDS_REVIEW",
            completion_mode="continue_collection",
            strict_ready=False,
            limited_ready=False,
            auto_exhausted=False,
            manual_decision_required=False,
            environment_blocked=False,
            reason="Ready automatic follow-up tools remain available for unresolved evidence gaps.",
            remaining_blockers=remaining_blockers,
            acceptable_limitations=acceptable_limitations,
            operator_next_actions=["Run the ready gap follow-up jobs before deciding whether the task is complete."],
            evidence_floor=evidence_floor,
        )

    if limited_ready:
        return _policy(
            recommended_status="COMPLETED",
            completion_mode="limited",
            strict_ready=False,
            limited_ready=True,
            auto_exhausted=True,
            manual_decision_required=False,
            environment_blocked=False,
            reason=_limited_reason(remaining_blockers),
            remaining_blockers=remaining_blockers,
            acceptable_limitations=acceptable_limitations,
            operator_next_actions=_operator_actions(remaining_blockers),
            evidence_floor=evidence_floor,
        )

    if environment_blocked:
        return _policy(
            recommended_status="NEEDS_REVIEW" if useful_evidence else "BLOCKED",
            completion_mode="blocked_by_environment",
            strict_ready=False,
            limited_ready=False,
            auto_exhausted=True,
            manual_decision_required=True,
            environment_blocked=True,
            reason="Automatic collection is blocked by unavailable tools, configuration, credentials, or disabled routes.",
            remaining_blockers=remaining_blockers,
            acceptable_limitations=acceptable_limitations,
            operator_next_actions=_environment_actions(gap_tool_plan),
            evidence_floor=evidence_floor,
        )

    if _execution_failed_without_evidence(detail):
        return _policy(
            recommended_status="FAILED",
            completion_mode="failed",
            strict_ready=False,
            limited_ready=False,
            auto_exhausted=True,
            manual_decision_required=True,
            environment_blocked=False,
            reason="Execution failed without collecting useful evidence.",
            remaining_blockers=remaining_blockers,
            acceptable_limitations=acceptable_limitations,
            operator_next_actions=["Inspect failed job errors and rerun after the execution issue is fixed."],
            evidence_floor=evidence_floor,
        )

    return _policy(
        recommended_status="NEEDS_REVIEW",
        completion_mode="ready_for_human_decision",
        strict_ready=False,
        limited_ready=False,
        auto_exhausted=auto_exhausted,
        manual_decision_required=True,
        environment_blocked=False,
        reason="Automatic collection is exhausted, but required evidence is still insufficient for strict or limited completion.",
        remaining_blockers=remaining_blockers,
        acceptable_limitations=acceptable_limitations,
        operator_next_actions=_operator_actions(remaining_blockers),
        evidence_floor=evidence_floor,
    )


def _quality_assessment(detail: dict) -> dict:
    assessment = detail.get("quality_assessment")
    if assessment:
        return dict(assessment)
    from app.core.quality import build_quality_assessment

    return build_quality_assessment(detail)


def _policy(
    *,
    recommended_status: str,
    completion_mode: str,
    strict_ready: bool,
    limited_ready: bool,
    auto_exhausted: bool,
    manual_decision_required: bool,
    environment_blocked: bool,
    reason: str,
    remaining_blockers: list[str],
    acceptable_limitations: list[str],
    operator_next_actions: list[str],
    evidence_floor: dict,
) -> dict:
    return {
        "recommended_status": recommended_status,
        "completion_mode": completion_mode,
        "strict_completion_ready": strict_ready,
        "limited_completion_ready": limited_ready,
        "auto_exhausted": auto_exhausted,
        "manual_decision_required": manual_decision_required,
        "environment_blocked": environment_blocked,
        "reason": reason,
        "remaining_blockers": sorted(set(remaining_blockers)),
        "acceptable_limitations": sorted(set(acceptable_limitations)),
        "operator_next_actions": operator_next_actions,
        "evidence_floor": evidence_floor,
    }


def _remaining_blockers(assessment: dict, gap_analysis: list[dict]) -> list[str]:
    blockers = {str(item) for item in assessment.get("blocking_keys") or [] if str(item).strip()}
    for gap in gap_analysis:
        if gap.get("severity") == "blocking":
            gap_key = str(gap.get("gap_key") or "").strip()
            if gap_key:
                blockers.add(gap_key)
    return sorted(blockers)


def _evidence_floor(detail: dict) -> dict:
    seed_type = str(detail.get("seed_type") or "company")
    if seed_type in {"domain", "url"}:
        return {
            "identity": _has_entity_type(detail, {"company", "organization", "domain", "url", "website", "official_website"}),
            "official_website": _has_entity_type(detail, {"domain", "url", "website", "official_website"}) or _has_source_url(detail),
            "business_scope": _has_entity_type(detail, {"business_scope", "product_scope"}) or _has_fact_predicate(detail, "business_scope"),
            "evidence_ledger": _has_evidence_ledger(detail),
            "fact_pool": _has_linked_fact(detail),
            "cross_verification": _has_supported_verification(detail),
        }
    if seed_type in {"email", "username"}:
        return {
            "identity": _has_entity_type(detail, {"email", "username", "identity", "profile_url", "platform_account"}),
            "source_record": bool(detail.get("evidence") or detail.get("evidence_ledger") or detail.get("relationships")),
            "evidence_ledger": _has_evidence_ledger(detail),
            "risk_summary": bool(detail.get("risk_report") or detail.get("summary") or detail.get("report_markdown")),
        }
    return {
        "identity": _has_entity_type(detail, {"company", "organization"}) or _has_fact_predicate(detail, "company_identity"),
        "official_website": _has_entity_type(detail, {"domain", "url", "website", "official_website"}) or _has_source_url(detail),
        "business_scope": _has_entity_type(detail, {"business_scope", "product_scope"}) or _has_fact_predicate(detail, "business_scope"),
        "contact_channel": _has_entity_type(detail, {"email", "phone", "whatsapp"}) or _has_contact_page(detail),
        "evidence_ledger": _has_evidence_ledger(detail),
        "fact_pool": _has_linked_fact(detail),
        "cross_verification": _has_supported_verification(detail),
    }


def _acceptable_limitations(detail: dict, remaining_blockers: list[str], evidence_floor: dict) -> list[str]:
    if not all(evidence_floor.values()):
        return []
    accepted = set(BASE_ACCEPTABLE_LIMITATIONS)
    if _has_entity_type(detail, {"email"}) or _has_contact_page(detail):
        accepted.add("contact_phone")
    if _has_entity_type(detail, {"phone", "whatsapp"}) or _has_contact_page(detail):
        accepted.add("contact_email")
    return sorted(key for key in remaining_blockers if key in accepted)


def _has_non_acceptable_blocker(remaining_blockers: list[str], detail: dict) -> bool:
    if set(remaining_blockers) & NON_ACCEPTABLE_BLOCKERS:
        return True
    matrix = detail.get("cross_verification_matrix") or []
    return any(str(row.get("status") or "").upper() in {"CONFLICT", "CONTRADICTED", "HIGH_RISK_CONFLICT"} for row in matrix)


def _environment_blocked(gap_tool_plan: list[dict], gap_summary: dict) -> bool:
    if int(gap_summary.get("ready") or 0) + int(gap_summary.get("queued") or 0) > 0:
        return False
    if int(gap_summary.get("blocked_by_config") or 0) > 0:
        return True
    return any(str(item.get("status") or "") in BLOCKED_TOOL_STATUSES for item in gap_tool_plan)


def _has_useful_evidence(detail: dict) -> bool:
    return bool(detail.get("evidence_ledger") or detail.get("facts") or detail.get("entities") or detail.get("evidence"))


def _execution_failed_without_evidence(detail: dict) -> bool:
    jobs = detail.get("jobs") or []
    if _has_useful_evidence(detail) or not jobs:
        return False
    return all(str(job.get("status") or "") in {"FAILED", "PARTIAL_FAILED"} for job in jobs)


def _has_entity_type(detail: dict, accepted_types: set[str]) -> bool:
    return any(str(item.get("type") or "") in accepted_types and str(item.get("value") or "").strip() for item in detail.get("entities") or [])


def _has_source_url(detail: dict) -> bool:
    return any(str(item.get("source_url") or "").startswith(("http://", "https://")) for item in detail.get("evidence_ledger") or [])


def _has_contact_page(detail: dict) -> bool:
    for item in detail.get("evidence_ledger") or []:
        source_type = str(item.get("source_type") or "").lower()
        source_url = str(item.get("source_url") or "").lower()
        if "contact" in source_type or "/contact" in source_url:
            return True
    return any("contact" in str(item.get("evidence_kind") or "").lower() for item in detail.get("evidence") or [])


def _has_evidence_ledger(detail: dict) -> bool:
    return any(item.get("source_url") or item.get("source_type") for item in detail.get("evidence_ledger") or [])


def _has_linked_fact(detail: dict) -> bool:
    return any(item.get("evidence_ids") for item in detail.get("facts") or [])


def _has_fact_predicate(detail: dict, key: str) -> bool:
    return any(key in str(item.get("predicate") or "").lower() for item in detail.get("facts") or [])


def _has_supported_verification(detail: dict) -> bool:
    return any(str(item.get("status") or "").upper() in SUPPORTED_VERIFICATION_STATUSES for item in detail.get("cross_verification_matrix") or [])


def _limited_reason(remaining_blockers: list[str]) -> str:
    readable = ", ".join(remaining_blockers)
    return f"Core evidence floor is satisfied; only acceptable limitations remain: {readable}."


def _operator_actions(remaining_blockers: list[str]) -> list[str]:
    action_by_key = {
        "decision_maker": "Manually verify decision-maker from an official team page, public profile, or trusted directory.",
        "purchase_intent": "Manually review buying-intent context if this task is used for sales qualification.",
        "contact_phone": "Manually verify phone or WhatsApp if direct calling is required.",
        "contact_email": "Manually verify email if outbound email is required.",
        "official_website": "Confirm official website or trusted source boundary before closure.",
        "evidence_ledger": "Collect source-backed evidence records before accepting conclusions.",
        "fact_pool": "Promote source-backed claims into facts before accepting conclusions.",
        "cross_verification": "Run or perform cross-verification before accepting conclusions.",
    }
    if not remaining_blockers:
        return []
    return [action_by_key.get(key, f"Manually resolve evidence gap: {key}.") for key in sorted(set(remaining_blockers))]


def _environment_actions(gap_tool_plan: list[dict]) -> list[str]:
    actions = []
    for item in gap_tool_plan:
        status = str(item.get("status") or "")
        if status not in BLOCKED_TOOL_STATUSES:
            continue
        tool_name = str(item.get("tool_name") or "unknown_tool")
        reason = str(item.get("health_reason") or "Tool route is unavailable.")
        actions.append(f"Restore {tool_name}: {reason}")
    return actions or ["Restore blocked tool routes, credentials, or configuration, then rerun collection."]
```

- [ ] **Step 4: Run the core policy tests and verify they pass**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_completion_policy.py' -v
```

Expected: PASS for the three initial tests.

- [ ] **Step 5: Commit the core contract**

Run:

```bash
git add backend/app/core/completion_policy.py backend/tests/test_completion_policy.py
git commit -m "feat: add completion policy core"
```

---

### Task 2: Limited Completion Evidence Floor

**Files:**
- Modify: `backend/tests/test_completion_policy.py`
- Modify: `backend/app/core/completion_policy.py`

- [ ] **Step 1: Add failing tests for limited completion and non-waivable blockers**

Append these tests inside `CompletionPolicyTests`:

```python
    def test_company_can_complete_with_limited_decision_maker_shortfall(self):
        detail = complete_company_detail()
        detail["entities"] = [item for item in detail["entities"] if item["type"] != "decision_maker"]
        detail["quality_assessment"] = {
            "score": 84.0,
            "completion_ready": False,
            "missing_keys": ["decision_maker"],
            "blocking_keys": ["decision_maker"],
            "checks": [],
        }
        detail["gap_analysis"] = [{"gap_key": "decision_maker", "severity": "blocking"}]
        detail["gap_tool_plan"] = [
            {"gap_key": "decision_maker", "tool_name": "official_site_extractor", "status": "already_attempted"}
        ]
        detail["gap_followup_summary"] = {
            "total_gaps": 1,
            "blocking_gaps": 1,
            "ready": 0,
            "queued": 0,
            "already_attempted": 1,
            "blocked_by_config": 0,
            "exhausted": 0,
            "manual_review_required": 0,
        }

        policy = build_completion_policy(detail)

        self.assertEqual(policy["completion_mode"], "limited")
        self.assertEqual(policy["recommended_status"], "COMPLETED")
        self.assertFalse(policy["strict_completion_ready"])
        self.assertTrue(policy["limited_completion_ready"])
        self.assertEqual(policy["remaining_blockers"], ["decision_maker"])
        self.assertEqual(policy["acceptable_limitations"], ["decision_maker"])

    def test_missing_official_website_cannot_be_limited_completion(self):
        detail = complete_company_detail()
        detail["entities"] = [
            item for item in detail["entities"] if item["type"] not in {"domain", "url", "website", "official_website"}
        ]
        detail["evidence_ledger"] = [
            {
                "id": "ev-1",
                "source_url": "registry",
                "source_type": "trusted_directory",
                "source_tool": "company_osint",
                "admiralty_code": "B-2",
                "snippet": "Trusted directory names Sample Auto Parts Co.",
            }
        ]
        detail["quality_assessment"] = {
            "score": 78.0,
            "completion_ready": False,
            "missing_keys": ["official_website"],
            "blocking_keys": ["official_website"],
            "checks": [],
        }
        detail["gap_analysis"] = [{"gap_key": "official_website", "severity": "blocking"}]
        detail["gap_tool_plan"] = [
            {"gap_key": "official_website", "tool_name": "official_site_search", "status": "already_attempted"}
        ]
        detail["gap_followup_summary"] = {
            "total_gaps": 1,
            "blocking_gaps": 1,
            "ready": 0,
            "queued": 0,
            "already_attempted": 1,
            "blocked_by_config": 0,
            "exhausted": 0,
            "manual_review_required": 0,
        }

        policy = build_completion_policy(detail)

        self.assertEqual(policy["completion_mode"], "ready_for_human_decision")
        self.assertEqual(policy["recommended_status"], "NEEDS_REVIEW")
        self.assertFalse(policy["limited_completion_ready"])
        self.assertIn("official_website", policy["remaining_blockers"])

    def test_missing_evidence_ledger_cannot_be_limited_completion(self):
        detail = complete_company_detail()
        detail["evidence"] = []
        detail["evidence_ledger"] = []
        detail["facts"] = []
        detail["quality_assessment"] = {
            "score": 76.0,
            "completion_ready": False,
            "missing_keys": ["evidence_ledger", "fact_pool"],
            "blocking_keys": ["evidence_ledger", "fact_pool"],
            "checks": [],
        }
        detail["gap_analysis"] = [
            {"gap_key": "evidence_ledger", "severity": "blocking"},
            {"gap_key": "fact_pool", "severity": "blocking"},
        ]
        detail["gap_tool_plan"] = []
        detail["gap_followup_summary"] = {
            "total_gaps": 2,
            "blocking_gaps": 2,
            "ready": 0,
            "queued": 0,
            "already_attempted": 0,
            "blocked_by_config": 0,
            "exhausted": 0,
            "manual_review_required": 2,
        }

        policy = build_completion_policy(detail)

        self.assertEqual(policy["completion_mode"], "ready_for_human_decision")
        self.assertEqual(policy["recommended_status"], "NEEDS_REVIEW")
        self.assertFalse(policy["evidence_floor"]["evidence_ledger"])
        self.assertFalse(policy["evidence_floor"]["fact_pool"])
```

- [ ] **Step 2: Run the new limited-completion tests and verify they fail**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_completion_policy.CompletionPolicyTests.test_company_can_complete_with_limited_decision_maker_shortfall backend.tests.test_completion_policy.CompletionPolicyTests.test_missing_official_website_cannot_be_limited_completion backend.tests.test_completion_policy.CompletionPolicyTests.test_missing_evidence_ledger_cannot_be_limited_completion -v
```

Expected: FAIL if limited completion or evidence-floor behavior is incomplete.

- [ ] **Step 3: Adjust evidence-floor helpers only if the failing tests show a mismatch**

If the failure is in official website source-boundary handling, replace `_has_source_url()` with:

```python
def _has_source_url(detail: dict) -> bool:
    for item in detail.get("evidence_ledger") or []:
        source_url = str(item.get("source_url") or "")
        source_type = str(item.get("source_type") or "").lower()
        if source_url.startswith(("http://", "https://")):
            return True
        if source_type in {"official_site", "official_site_contact", "official_site_identity", "official_site_business_scope"}:
            return True
    return False
```

If the failure is in fact-pool support, replace `_has_linked_fact()` with:

```python
def _has_linked_fact(detail: dict) -> bool:
    for item in detail.get("facts") or []:
        status = str(item.get("status") or "").upper()
        if status not in {"CONFIRMED", "LIKELY", "SUPPORTED"}:
            continue
        if item.get("evidence_ids"):
            return True
    return False
```

- [ ] **Step 4: Run the full completion policy suite**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_completion_policy.py' -v
```

Expected: PASS.

- [ ] **Step 5: Commit the limited-completion rules**

Run:

```bash
git add backend/app/core/completion_policy.py backend/tests/test_completion_policy.py
git commit -m "feat: classify limited evidence completion"
```

---

### Task 3: Store Detail Integration

**Files:**
- Modify: `backend/tests/test_completion_policy.py`
- Modify: `backend/app/services/store.py`

- [ ] **Step 1: Add failing store detail tests**

Append this import near the top of `backend/tests/test_completion_policy.py`:

```python
from tempfile import TemporaryDirectory
from pathlib import Path

from app.services.store import MemoryStore, SQLiteStore
```

Append these tests inside `CompletionPolicyTests`:

```python
    def test_memory_store_detail_includes_completion_policy(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Example Manufacturing LLC review",
            seed_type="company",
            seed_value="Example Manufacturing LLC",
            strategy_name="quick",
        )

        detail = store.get_investigation(investigation.id)

        self.assertIn("completion_policy", detail)
        self.assertIn(detail["completion_policy"]["completion_mode"], {
            "continue_collection",
            "ready_for_human_decision",
            "blocked_by_environment",
            "failed",
            "limited",
            "strict",
        })

    def test_sqlite_store_detail_includes_completion_policy(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(Path(tmpdir) / "store.db")
            investigation = store.create_investigation(
                name="Example Manufacturing LLC review",
                seed_type="company",
                seed_value="Example Manufacturing LLC",
                strategy_name="quick",
            )

            detail = store.get_investigation(investigation.id)

        self.assertIn("completion_policy", detail)
        self.assertIn("recommended_status", detail["completion_policy"])
```

- [ ] **Step 2: Run store detail tests and verify they fail**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_completion_policy.CompletionPolicyTests.test_memory_store_detail_includes_completion_policy backend.tests.test_completion_policy.CompletionPolicyTests.test_sqlite_store_detail_includes_completion_policy -v
```

Expected: FAIL because `completion_policy` is not yet added to store details.

- [ ] **Step 3: Wire completion policy into store details and completion status**

In `backend/app/services/store.py`, add this import:

```python
from app.core.completion_policy import build_completion_policy
```

In both MemoryStore detail paths and SQLiteStore detail path, immediately after `_apply_gap_plans(data)`, add:

```python
        data["completion_policy"] = build_completion_policy(data)
```

In the shared helper area after `_apply_gap_plans(data)`, add:

```python
def _policy_status_for_detail(detail: dict, requested_status: str) -> str:
    if requested_status in {"FAILED", "PARTIAL_FAILED", "CANCELLED", "ARCHIVED"}:
        return requested_status
    policy = detail.get("completion_policy") or build_completion_policy(detail)
    if requested_status == "COMPLETED":
        return str(policy.get("recommended_status") or completion_status_for_detail(detail, requested_status))
    if requested_status == "BLOCKED" and policy.get("completion_mode") == "blocked_by_environment":
        return str(policy.get("recommended_status") or "BLOCKED")
    return completion_status_for_detail(detail, requested_status)
```

In `MemoryStore.complete_task()`, replace:

```python
            investigation.status = completion_status_for_detail(preview, status)
```

with:

```python
            preview["completion_policy"] = build_completion_policy(preview)
            investigation.status = _policy_status_for_detail(preview, status)
```

In `SQLiteStore.complete_task()`, replace:

```python
        final_status = completion_status_for_detail(detail, status)
```

with:

```python
        detail["completion_policy"] = build_completion_policy(detail)
        final_status = _policy_status_for_detail(detail, status)
```

- [ ] **Step 4: Run completion policy tests**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_completion_policy.py' -v
```

Expected: PASS.

- [ ] **Step 5: Commit store integration**

Run:

```bash
git add backend/app/services/store.py backend/tests/test_completion_policy.py
git commit -m "feat: expose completion policy in store details"
```

---

### Task 4: Worker Final Status Integration

**Files:**
- Modify: `backend/tests/test_worker.py`
- Modify: `backend/app/services/worker.py`

- [ ] **Step 1: Add a failing worker regression**

Add this import near the top of `backend/tests/test_worker.py`:

```python
from app.core.fact_pool import FactRecord
```

Append this test inside `WorkerTests`:

```python
    def test_worker_marks_limited_completion_completed_with_policy_summary(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="limited completion company",
            seed_type="company",
            seed_value="Sample Auto Parts Co.",
            strategy_name="quick",
        )
        first_job = store.list_jobs(investigation.id)[0]
        store.replace_jobs(
            investigation.id,
            [
                {
                    **first_job,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "depth": 0,
                    "status": "COMPLETED",
                    "agent_role": "analysis_judgement_agent",
                }
            ],
        )
        store.add_entity(investigation.id, "company", "Sample Auto Parts Co.", "company_osint", 0.9)
        store.add_entity(investigation.id, "domain", "example-target.test", "official_site_search", 0.82)
        store.add_entity(investigation.id, "url", "https://example-target.test", "httpx", 0.82)
        store.add_entity(investigation.id, "email", "sales@example-target.test", "official_site_extractor", 0.8)
        store.add_entity(investigation.id, "phone", "+1-555-0100", "official_site_extractor", 0.76)
        store.add_entity(investigation.id, "address", "Chicago, IL", "company_osint", 0.72)
        store.add_entity(investigation.id, "business_scope", "auto parts distribution", "official_site_extractor", 0.8)
        evidence = store.add_evidence_record(
            investigation.id,
            source_url="https://example-target.test/contact",
            source_type="official_site_contact",
            source_tool="official_site_extractor",
            snippet="Official contact page lists sales@example-target.test.",
            credibility=0.82,
        )
        store.add_fact(
            investigation.id,
            statement="Sample Auto Parts Co. lists a source-backed contact channel.",
            subject="Sample Auto Parts Co.",
            predicate="has_contact_email",
            object_value="sales@example-target.test",
            status="CONFIRMED",
            confidence=0.82,
            admiralty_code="A-2",
            evidence_ids=[evidence["id"]],
        )
        store.add_hypothesis(investigation.id, "h1", "Sample Auto Parts Co. is the target company.")
        store.score_hypotheses(
            investigation.id,
            [
                {
                    "id": evidence["id"],
                    "summary": "Official site contact evidence supports target identity.",
                    "kinds": ["official_site_contact"],
                    "supports": ["h1"],
                    "contradicts": [],
                    "source_reliability": "A",
                    "credibility": 0.82,
                    "keywords": ["sample", "auto parts"],
                }
            ],
        )

        with TemporaryDirectory() as tmpdir:
            summary = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=0,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: MinimalCompleteAdapter(name),
            )

        detail = store.get_investigation(investigation.id)

        self.assertEqual(summary["completion_mode"], "limited")
        self.assertEqual(summary["completion_policy"]["recommended_status"], "COMPLETED")
        self.assertFalse(summary["quality_assessment"]["completion_ready"])
        self.assertEqual(detail["status"], "COMPLETED")
        self.assertEqual(detail["completion_policy"]["completion_mode"], "limited")
```

- [ ] **Step 2: Run the new worker regression and verify it fails**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_worker.WorkerTests.test_worker_marks_limited_completion_completed_with_policy_summary -v
```

Expected: FAIL because worker summary does not expose `completion_policy` and final status still downgrades limited completion.

- [ ] **Step 3: Wire completion policy into worker final status**

In `backend/app/services/worker.py`, add this import:

```python
from app.core.completion_policy import build_completion_policy
```

Add this key to the initial `summary` dict:

```python
        "completion_policy": {},
```

In the busy-return branch, after `summary["quality_assessment"] = build_quality_assessment(detail)`, add:

```python
        summary["completion_policy"] = build_completion_policy({**detail, "quality_assessment": summary["quality_assessment"]})
        summary["completion_mode"] = summary["completion_policy"]["completion_mode"]
```

In the planning-blocked return branch, after `summary["quality_assessment"] = build_quality_assessment(detail)`, add the same two lines.

Near the final status computation, replace:

```python
    quality_assessment = build_quality_assessment(detail)
    requested_status = _final_status(detail, risk_report)
    final_status = completion_status_for_detail(detail, requested_status)
```

with:

```python
    quality_assessment = build_quality_assessment(detail)
    policy_detail = {**detail, "quality_assessment": quality_assessment}
    completion_policy = build_completion_policy(policy_detail)
    requested_status = _final_status(detail, risk_report)
    final_status = _final_status_from_completion_policy(requested_status, risk_report, completion_policy)
```

Add this helper below `_final_status()`:

```python
def _final_status_from_completion_policy(requested_status: str, risk_report: dict, completion_policy: dict) -> str:
    if risk_report.get("review_required"):
        return "NEEDS_REVIEW"
    if requested_status in {"FAILED", "PARTIAL_FAILED"}:
        return requested_status
    if requested_status == "BLOCKED" and completion_policy.get("completion_mode") != "blocked_by_environment":
        return "BLOCKED"
    recommended = str(completion_policy.get("recommended_status") or "")
    if recommended in {"COMPLETED", "NEEDS_REVIEW", "BLOCKED", "FAILED"}:
        return recommended
    return completion_status_for_detail({}, requested_status)
```

After the final store update, before `summary["risk_report"] = risk_report`, add:

```python
    summary["completion_policy"] = completion_policy
    summary["completion_mode"] = completion_policy["completion_mode"]
```

- [ ] **Step 4: Run worker tests for final status and gap followups**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_worker.py' -v
```

Expected: PASS.

- [ ] **Step 5: Commit worker integration**

Run:

```bash
git add backend/app/services/worker.py backend/tests/test_worker.py
git commit -m "feat: apply completion policy in worker"
```

---

### Task 5: Report Rendering

**Files:**
- Modify: `backend/tests/test_quality_gate.py`
- Modify: `backend/app/core/quality.py`

- [ ] **Step 1: Add a failing report rendering test**

Add this test inside `QualityGateTests`:

```python
    def test_report_renders_completion_policy_section(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Sample Auto Parts Co.",
            "entities": [
                {"type": "company", "value": "Sample Auto Parts Co.", "confidence": 0.9},
                {"type": "domain", "value": "example-target.test", "confidence": 0.82},
                {"type": "url", "value": "https://example-target.test", "confidence": 0.82},
                {"type": "email", "value": "sales@example-target.test", "confidence": 0.8},
                {"type": "phone", "value": "+1-555-0100", "confidence": 0.76},
                {"type": "business_scope", "value": "auto parts distribution", "confidence": 0.8},
            ],
            "evidence": [{"entity_value": "sales@example-target.test", "evidence_kind": "official_site_contact"}],
            "evidence_ledger": [
                {
                    "id": "ev-1",
                    "source_url": "https://example-target.test/contact",
                    "source_type": "official_site_contact",
                    "admiralty_code": "A-2",
                    "snippet": "Official contact page lists sales@example-target.test.",
                }
            ],
            "facts": [
                {
                    "id": "fact-1",
                    "statement": "Sample Auto Parts Co. lists a source-backed contact channel.",
                    "predicate": "has_contact_email",
                    "status": "CONFIRMED",
                    "promotion_stage": "ACCEPTED_FACT",
                    "evidence_ids": ["ev-1"],
                }
            ],
            "hypotheses": [{"id": "h1", "status": "MOST_LIKELY"}],
            "relationships": [{"from_value": "Sample Auto Parts Co.", "to_value": "sales@example-target.test"}],
            "report_markdown": "## BLUF\nSample Auto Parts Co. has source-backed contact and scope evidence.",
            "quality_assessment": {
                "score": 84.0,
                "completion_ready": False,
                "missing_keys": ["decision_maker"],
                "blocking_keys": ["decision_maker"],
                "checks": [],
            },
            "gap_analysis": [{"gap_key": "decision_maker", "severity": "blocking"}],
            "gap_tool_plan": [
                {"gap_key": "decision_maker", "tool_name": "official_site_extractor", "status": "already_attempted"}
            ],
            "gap_followup_summary": {
                "total_gaps": 1,
                "blocking_gaps": 1,
                "ready": 0,
                "queued": 0,
                "already_attempted": 1,
                "blocked_by_config": 0,
                "exhausted": 0,
                "manual_review_required": 0,
            },
            "cross_verification_matrix": [
                {"field_key": "company_identity", "status": "CONFIRMED", "candidate_value": "Sample Auto Parts Co."}
            ],
        }

        report = render_structured_report(detail, detail["quality_assessment"])

        self.assertIn("## 完成策略", report)
        self.assertIn("limited", report)
        self.assertIn("decision_maker", report)
        self.assertIn("Manually verify decision-maker", report)
```

- [ ] **Step 2: Run the report test and verify it fails**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_quality_gate.QualityGateTests.test_report_renders_completion_policy_section -v
```

Expected: FAIL because the report has no completion-policy section.

- [ ] **Step 3: Add completion policy rendering to reports**

In `backend/app/core/quality.py`, inside `render_structured_report()`, after `gap_tool_plan` is computed, add:

```python
    from app.core.completion_policy import build_completion_policy

    completion_policy = detail.get("completion_policy") or build_completion_policy(
        {
            **detail,
            "quality_assessment": assessment,
            "gap_analysis": gap_analysis,
            "gap_tool_plan": gap_tool_plan,
        }
    )
```

After the quality-gate block and before `lines.extend(_gap_followup_lines(gap_analysis, gap_tool_plan))`, add:

```python
    lines.extend(_completion_policy_lines(completion_policy))
```

Add these helpers near `_gap_followup_lines()`:

```python
def _completion_policy_lines(policy: dict) -> list[str]:
    mode = str(policy.get("completion_mode") or "unknown")
    status = str(policy.get("recommended_status") or "NEEDS_REVIEW")
    lines = [
        "",
        "## 完成策略",
        f"- 策略模式：{mode}",
        f"- 推荐状态：{status}",
        f"- 严格完成：{'是' if policy.get('strict_completion_ready') else '否'}",
        f"- 有限完成：{'是' if policy.get('limited_completion_ready') else '否'}",
        f"- 自动补采耗尽：{'是' if policy.get('auto_exhausted') else '否'}",
        f"- 原因：{policy.get('reason') or '未记录'}",
    ]
    blockers = [str(item) for item in policy.get("remaining_blockers") or []]
    if blockers:
        lines.append(f"- 剩余卡点：{'、'.join(blockers)}")
    limitations = [str(item) for item in policy.get("acceptable_limitations") or []]
    if limitations:
        lines.append(f"- 可接受限制：{'、'.join(limitations)}")
    actions = [str(item) for item in policy.get("operator_next_actions") or []]
    if actions:
        lines.append("- 操作员下一步：")
        for action in actions[:6]:
            lines.append(f"  - {action}")
    return lines
```

- [ ] **Step 4: Run quality gate tests**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_quality_gate.py' -v
```

Expected: PASS.

- [ ] **Step 5: Commit report integration**

Run:

```bash
git add backend/app/core/quality.py backend/tests/test_quality_gate.py
git commit -m "feat: render completion policy in reports"
```

---

### Task 6: Documentation, Verification, and Privacy Check

**Files:**
- Modify: `docs/UPDATE_LOG.md`

- [ ] **Step 1: Update the project log**

Add this entry near the top of `docs/UPDATE_LOG.md`:

```markdown
## 2026-07-06 Evidence shortfall completion policy

- Added deterministic `completion_policy` rules for strict, limited, continue-collection, human-decision, environment-blocked, and failed outcomes.
- Kept the strict quality gate unchanged; limited completion is represented by `completion_policy.completion_mode = "limited"` and persisted status `COMPLETED`.
- Exposed policy output in investigation detail, worker summaries, and structured reports.
- Added regression coverage for limited completion, non-waivable evidence gaps, store detail exposure, worker final status, and report rendering.
```

- [ ] **Step 2: Run targeted tests**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_completion_policy.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_worker.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_quality_gate.py' -v
```

Expected: all targeted tests PASS.

- [ ] **Step 3: Run full verification**

Run:

```bash
bash scripts/verify.sh
```

Expected: backend tests, frontend tests, and build verification PASS according to the script output.

- [ ] **Step 4: Run formatting and whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 5: Run privacy scan on the staged diff**

Run:

```bash
git diff --unified=0 -- . | rg '^\+' | rg -n 'SRR|srrautopartsonline|ZAWIJA|Family Hospitality|Long Way|in19034126503jgqn|JAPAN SRR|Genuine Parts|f1224594|d9bf6c4b|6999088c|a8df5c87|83a1a3a5|22f8ead9|b1767a1a|565694ff|1ac0604c|fa08c83b|266d697c|e9b5e99b|/home/aidi|/Users/aidi|\bn100\b|192\.168\.|10\.[0-9]+\.|172\.(1[6-9]|2[0-9]|3[01])\.|Bearer [A-Za-z0-9._~-]{12,}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}'
```

Expected: no output.

- [ ] **Step 6: Commit final documentation and verification record**

Run:

```bash
git add docs/UPDATE_LOG.md
git commit -m "docs: record completion policy implementation"
```

---

## Self-Review Notes

- Spec coverage: core contract, allowed modes, evidence floor, limited completion, non-waivable blockers, environment blockage, store detail exposure, worker status selection, report rendering, documentation, verification, and privacy scan are covered by tasks above.
- Type consistency: the public API is `build_completion_policy(detail: dict) -> dict`; all integration points use the same `completion_policy` field and `completion_mode` key.
- Execution order: each implementation task starts with a failing test, verifies failure, writes minimal production code, verifies pass, then commits.
