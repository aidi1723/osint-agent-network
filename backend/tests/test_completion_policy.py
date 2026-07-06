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

    def test_environment_blocked_with_only_raw_seed_entity_recommends_blocked(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "entities": [{"type": "company", "value": "Example Manufacturing LLC", "confidence": 0.72}],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "relationships": [],
            "hypotheses": [],
            "jobs": [{"tool_name": "official_site_search", "status": "BLOCKED"}],
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
                    "tool_name": "official_site_search",
                    "status": "missing_config",
                    "health_reason": "search provider API key is not configured",
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

    def test_failed_without_evidence_recommends_failed(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "entities": [],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "relationships": [],
            "hypotheses": [],
            "jobs": [
                {"tool_name": "official_site_search", "status": "FAILED"},
                {"tool_name": "company_osint", "status": "PARTIAL_FAILED"},
            ],
            "report_markdown": "",
            "quality_assessment": {
                "score": 0.0,
                "completion_ready": False,
                "missing_keys": [],
                "blocking_keys": [],
                "checks": [],
            },
            "gap_analysis": [],
            "gap_tool_plan": [],
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

        policy = build_completion_policy(detail)

        self.assertEqual(policy["completion_mode"], "failed")
        self.assertEqual(policy["recommended_status"], "FAILED")
        self.assertTrue(policy["manual_decision_required"])
        self.assertTrue(policy["auto_exhausted"])

    def test_ready_for_human_decision_respects_explicit_empty_gap_fields(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "entities": [],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "relationships": [],
            "hypotheses": [],
            "jobs": [],
            "report_markdown": "",
            "quality_assessment": {
                "score": 10.0,
                "completion_ready": False,
                "missing_keys": ["official_website"],
                "blocking_keys": ["official_website"],
                "checks": [],
            },
            "gap_analysis": [],
            "gap_tool_plan": [],
            "gap_followup_summary": {},
        }

        policy = build_completion_policy(detail)

        self.assertEqual(policy["completion_mode"], "ready_for_human_decision")
        self.assertEqual(policy["recommended_status"], "NEEDS_REVIEW")
        self.assertTrue(policy["manual_decision_required"])
        self.assertTrue(policy["auto_exhausted"])
        self.assertIn("official_website", policy["remaining_blockers"])
