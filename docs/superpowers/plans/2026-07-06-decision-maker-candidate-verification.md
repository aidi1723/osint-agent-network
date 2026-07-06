# Decision-Maker Candidate Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `has_decision_maker_candidate` facts support the `decision_maker` field without confirming candidates.

**Architecture:** Add explicit decision-maker predicate matching in cross-verification and quality-gate helpers. Keep the change rule-based, local, and conservative.

**Tech Stack:** Python standard library, existing `unittest` suite, existing verification scripts.

---

## Task 1: Cross-Verification Candidate Fact Matching

**Files:**
- Modify: `backend/tests/test_cross_verification.py`
- Modify: `backend/app/core/cross_verification.py`

- [ ] **Step 1: Write failing test**

Add:

```python
    def test_decision_maker_candidate_fact_supports_decision_maker_field(self):
        detail = {
            "entities": [],
            "facts": [
                {
                    "id": "fact-decision-candidate",
                    "subject": "Sample Auto Parts Co.",
                    "predicate": "has_decision_maker_candidate",
                    "object_value": "Jane Smith - Export Manager",
                    "status": "LIKELY",
                    "promotion_stage": "NEEDS_REVIEW",
                    "confidence": 0.66,
                    "evidence_ids": ["ev-person"],
                }
            ],
            "evidence_ledger": [
                {
                    "id": "ev-person",
                    "source_type": "official_site_decision_maker_candidate",
                    "source_tool": "official_site_extractor",
                    "source_url": "https://example.com/team",
                    "admiralty_code": "A-3",
                    "snippet": "Official site lists Jane Smith - Export Manager",
                }
            ],
            "evidence": [],
            "relationships": [],
        }

        rows = build_cross_verification_matrix(detail)
        decision = next(row for row in rows if row["field_key"] == "decision_maker")

        self.assertEqual(decision["candidate_value"], "Jane Smith - Export Manager")
        self.assertIn(decision["status"], {"SUPPORTED", "LIKELY"})
        self.assertIn("fact-decision-candidate", decision["linked_fact_ids"])
```

- [ ] **Step 2: Run red test**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_cross_verification.CrossVerificationTests.test_decision_maker_candidate_fact_supports_decision_maker_field
```

Expected: fail because `_fact_matches_field()` does not recognize `has_decision_maker_candidate`.

- [ ] **Step 3: Implement predicate matching**

In `backend/app/core/cross_verification.py`, update `_fact_matches_field()` with:

```python
    if field_key == "decision_maker" and predicate in {"has_decision_maker_candidate", "has_public_profile_candidate"}:
        return True
```

- [ ] **Step 4: Run green test**

Run the same command. Expected: pass.

## Task 2: Quality-Gate Candidate Fact Matching

**Files:**
- Modify: `backend/tests/test_quality_gate.py`
- Modify: `backend/app/core/quality.py`

- [ ] **Step 1: Write failing test**

Add:

```python
    def test_decision_maker_candidate_fact_satisfies_decision_maker_without_completion(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Sample Auto Parts Co.",
            "entities": [{"type": "company", "value": "Sample Auto Parts Co.", "confidence": 0.82}],
            "facts": [
                {
                    "id": "fact-decision-candidate",
                    "predicate": "has_decision_maker_candidate",
                    "object_value": "Jane Smith - Export Manager",
                    "status": "LIKELY",
                    "promotion_stage": "NEEDS_REVIEW",
                    "confidence": 0.66,
                    "evidence_ids": ["ev-person"],
                }
            ],
            "evidence": [],
            "evidence_ledger": [
                {
                    "id": "ev-person",
                    "source_url": "https://example.com/team",
                    "source_type": "official_site_decision_maker_candidate",
                    "admiralty_code": "A-3",
                    "snippet": "Official site lists Jane Smith - Export Manager",
                }
            ],
            "relationships": [],
            "hypotheses": [],
            "report_markdown": "",
        }

        assessment = build_quality_assessment(detail)

        self.assertNotIn("decision_maker", assessment["missing_keys"])
        self.assertIn("bluf_report", assessment["blocking_keys"])
        self.assertFalse(assessment["completion_ready"])
```

- [ ] **Step 2: Run red test**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_quality_gate.QualityGateTests.test_decision_maker_candidate_fact_satisfies_decision_maker_without_completion
```

Expected: fail because `_fact_supports_field()` does not recognize the candidate predicate.

- [ ] **Step 3: Implement quality predicate matching**

In `backend/app/core/quality.py`, update `_fact_supports_field()` with:

```python
    if key == "decision_maker" and predicate in {"has_decision_maker_candidate", "has_public_profile_candidate"}:
        return True
```

- [ ] **Step 4: Run green test**

Run the same command. Expected: pass.

## Task 3: Verification And Records

**Files:**
- Modify: `docs/UPDATE_LOG.md`
- Modify: `docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md`

- [ ] **Step 1: Run targeted tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_cross_verification.CrossVerificationTests backend.tests.test_quality_gate.QualityGateTests
```

Expected: pass.

- [ ] **Step 2: Run full verification**

Run:

```bash
bash scripts/verify.sh
```

Expected: pass.

- [ ] **Step 3: Run <production-host> targeted verification**

Run targeted tests and readiness on <production-host>.

- [ ] **Step 4: Update docs**

Record the behavior, verification commands, and remaining caveat that candidates are not confirmed facts.

- [ ] **Step 5: Privacy scan, commit, push**

Run private-pattern scan against the diff, then commit and push.
