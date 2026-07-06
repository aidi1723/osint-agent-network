import unittest

from app.core.completion_policy import build_completion_policy


REQUIRED_POLICY_KEYS = {
    "recommended_status",
    "completion_mode",
    "strict_completion_ready",
    "limited_completion_ready",
    "auto_exhausted",
    "manual_decision_required",
    "environment_blocked",
    "reason",
    "remaining_blockers",
    "acceptable_limitations",
    "operator_next_actions",
    "evidence_floor",
}


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
                "source_url": "https://example-target.test/about",
                "source_type": "official_site_profile",
                "source_tool": "official_site_extractor",
                "admiralty_code": "A-2",
                "snippet": "Official profile confirms Sample Auto Parts Co. identity and auto parts distribution.",
            },
            {
                "id": "ev-2",
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
                "statement": "Sample Auto Parts Co. is the company identity on the official website.",
                "predicate": "company_identity",
                "subject": "Sample Auto Parts Co.",
                "object": "Sample Auto Parts Co.",
                "status": "CONFIRMED",
                "promotion_stage": "ACCEPTED_FACT",
                "confidence": 0.86,
                "evidence_ids": ["ev-1"],
            },
            {
                "id": "fact-2",
                "statement": "Sample Auto Parts Co. official website is https://example-target.test.",
                "predicate": "official_website",
                "subject": "Sample Auto Parts Co.",
                "object": "https://example-target.test",
                "status": "CONFIRMED",
                "promotion_stage": "ACCEPTED_FACT",
                "confidence": 0.84,
                "evidence_ids": ["ev-1"],
            },
            {
                "id": "fact-3",
                "statement": "Sample Auto Parts Co. business scope is auto parts distribution.",
                "predicate": "business_scope",
                "subject": "Sample Auto Parts Co.",
                "object": "auto parts distribution",
                "status": "CONFIRMED",
                "promotion_stage": "ACCEPTED_FACT",
                "confidence": 0.82,
                "evidence_ids": ["ev-1"],
            },
            {
                "id": "fact-4",
                "statement": "Sample Auto Parts Co. lists a source-backed contact channel.",
                "predicate": "has_contact_email",
                "subject": "Sample Auto Parts Co.",
                "object": "sales@example-target.test",
                "status": "CONFIRMED",
                "promotion_stage": "ACCEPTED_FACT",
                "confidence": 0.82,
                "evidence_ids": ["ev-2"],
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
            {
                "field_key": "company_identity",
                "status": "CONFIRMED",
                "candidate_value": "Sample Auto Parts Co.",
                "linked_evidence_ids": ["ev-1"],
                "linked_fact_ids": ["fact-1"],
            },
            {
                "field_key": "official_website",
                "status": "SUPPORTED",
                "candidate_value": "https://example-target.test",
                "linked_evidence_ids": ["ev-1"],
                "linked_fact_ids": ["fact-2"],
            },
            {
                "field_key": "business_scope",
                "status": "SUPPORTED",
                "candidate_value": "auto parts distribution",
                "linked_evidence_ids": ["ev-1"],
                "linked_fact_ids": ["fact-3"],
            },
            {
                "field_key": "contact_channel",
                "status": "SUPPORTED",
                "candidate_value": "sales@example-target.test",
                "linked_evidence_ids": ["ev-2"],
                "linked_fact_ids": ["fact-4"],
            },
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

    def test_strict_completion_rejects_explicit_blocking_gap(self):
        detail = complete_company_detail()
        detail["quality_assessment"] = {
            "score": 95.0,
            "completion_ready": True,
            "missing_keys": [],
            "blocking_keys": [],
            "checks": [],
        }
        detail["gap_analysis"] = [{"gap_key": "official_website", "severity": "blocking"}]
        detail["gap_tool_plan"] = []
        detail["gap_followup_summary"] = {
            "total_gaps": 1,
            "blocking_gaps": 1,
            "ready": 0,
            "queued": 0,
            "already_attempted": 0,
            "blocked_by_config": 0,
            "exhausted": 0,
            "manual_review_required": 0,
        }

        policy = build_completion_policy(detail)

        self.assertNotEqual(policy["completion_mode"], "strict")
        self.assertNotEqual(policy["recommended_status"], "COMPLETED")
        self.assertIn("official_website", policy["remaining_blockers"])

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

    def test_raw_unlinked_strict_quality_ready_does_not_complete_when_evidence_floor_false(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "entities": [
                {"type": "company", "value": "Example Manufacturing LLC", "confidence": 0.92},
                {"type": "domain", "value": "example-target.test", "confidence": 0.82},
                {"type": "email", "value": "sales@example-target.test", "confidence": 0.78},
                {"type": "business_scope", "value": "manufacturing", "confidence": 0.74},
            ],
            "evidence": [
                {
                    "entity_value": "Example Manufacturing LLC",
                    "evidence_kind": "search_result_summary",
                    "snippet": "Unlinked detail says the company exists.",
                }
            ],
            "evidence_ledger": [],
            "facts": [],
            "relationships": [],
            "hypotheses": [],
            "report_markdown": "## BLUF\nRaw unlinked detail only.",
            "quality_assessment": {
                "score": 95.0,
                "completion_ready": True,
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
            "cross_verification_matrix": [
                {
                    "field_key": "company_identity",
                    "status": "SUPPORTED",
                    "candidate_value": "Example Manufacturing LLC",
                }
            ],
        }

        policy = build_completion_policy(detail)

        self.assertNotEqual(policy["recommended_status"], "COMPLETED")
        self.assertNotEqual(policy["completion_mode"], "strict")
        self.assertFalse(all(policy["evidence_floor"].values()))

    def test_company_strict_quality_ready_rejects_bare_entities_and_fact_predicates(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "entities": [
                {"type": "company", "value": "Example Manufacturing LLC", "confidence": 0.96},
                {"type": "domain", "value": "example-target.test", "confidence": 0.88},
                {"type": "url", "value": "https://example-target.test", "confidence": 0.88},
                {"type": "business_scope", "value": "industrial equipment", "confidence": 0.82},
                {"type": "email", "value": "sales@example-target.test", "confidence": 0.8},
            ],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [
                {
                    "id": "fact-identity",
                    "statement": "Example Manufacturing LLC is a company.",
                    "predicate": "company_identity",
                    "subject": "Example Manufacturing LLC",
                    "object": "Example Manufacturing LLC",
                    "status": "CONFIRMED",
                    "evidence_ids": [],
                },
                {
                    "id": "fact-website",
                    "statement": "Example Manufacturing LLC official website is https://example-target.test.",
                    "predicate": "official_website",
                    "subject": "Example Manufacturing LLC",
                    "object": "https://example-target.test",
                    "status": "CONFIRMED",
                    "evidence_ids": [],
                },
                {
                    "id": "fact-scope",
                    "statement": "Example Manufacturing LLC sells industrial equipment.",
                    "predicate": "business_scope",
                    "subject": "Example Manufacturing LLC",
                    "object": "industrial equipment",
                    "status": "CONFIRMED",
                    "evidence_ids": [],
                },
            ],
            "relationships": [],
            "hypotheses": [],
            "report_markdown": "## BLUF\nBare entities and unlinked fact predicates only.",
            "quality_assessment": {
                "score": 95.0,
                "completion_ready": True,
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
            "cross_verification_matrix": [
                {
                    "field_key": "company_identity",
                    "status": "CONFIRMED",
                    "candidate_value": "Example Manufacturing LLC",
                },
                {
                    "field_key": "official_website",
                    "status": "SUPPORTED",
                    "candidate_value": "https://example-target.test",
                },
                {
                    "field_key": "business_scope",
                    "status": "SUPPORTED",
                    "candidate_value": "industrial equipment",
                },
            ],
        }

        policy = build_completion_policy(detail)

        self.assertNotEqual(policy["completion_mode"], "strict")
        self.assertNotEqual(policy["recommended_status"], "COMPLETED")
        self.assertFalse(policy["strict_completion_ready"])
        self.assertFalse(policy["evidence_floor"]["identity"])
        self.assertFalse(policy["evidence_floor"]["official_website"])
        self.assertFalse(policy["evidence_floor"]["business_scope"])

    def test_company_limited_completion_rejects_raw_unlinked_contact_page_evidence(self):
        detail = complete_company_detail()
        detail["entities"] = [
            {"type": "company", "value": "Sample Auto Parts Co.", "confidence": 0.9},
            {"type": "domain", "value": "example-target.test", "confidence": 0.82},
            {"type": "url", "value": "https://example-target.test", "confidence": 0.82},
            {"type": "business_scope", "value": "auto parts distribution", "confidence": 0.8},
        ]
        detail["evidence"] = [
            {
                "entity_value": "sales@example-target.test",
                "evidence_kind": "official_site_contact",
                "source_tool": "official_site_extractor",
            }
        ]
        detail["evidence_ledger"] = []
        detail["facts"] = []
        detail["quality_assessment"] = {
            "score": 78.0,
            "completion_ready": False,
            "missing_keys": ["contact_phone"],
            "blocking_keys": ["contact_phone"],
            "checks": [],
        }
        detail["gap_analysis"] = [{"gap_key": "contact_phone", "severity": "blocking"}]
        detail["gap_tool_plan"] = []
        detail["gap_followup_summary"] = {
            "total_gaps": 1,
            "blocking_gaps": 1,
            "ready": 0,
            "queued": 0,
            "already_attempted": 1,
            "blocked_by_config": 0,
            "exhausted": 1,
            "manual_review_required": 0,
        }
        detail["cross_verification_matrix"] = []

        policy = build_completion_policy(detail)

        self.assertFalse(policy["evidence_floor"]["contact_channel"])
        self.assertNotIn("contact_phone", policy["acceptable_limitations"])
        self.assertNotEqual(policy["completion_mode"], "limited")
        self.assertNotEqual(policy["recommended_status"], "COMPLETED")
        self.assertFalse(policy["limited_completion_ready"])

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

    def test_environment_blocked_with_only_raw_evidence_recommends_blocked(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "entities": [{"type": "company", "value": "Example Manufacturing LLC", "confidence": 0.72}],
            "evidence": [
                {
                    "entity_value": "Example Manufacturing LLC",
                    "evidence_kind": "search_result_summary",
                    "snippet": "Unlinked search summary mentions Example Manufacturing LLC.",
                }
            ],
            "evidence_ledger": [],
            "facts": [],
            "relationships": [],
            "hypotheses": [],
            "jobs": [{"tool_name": "official_site_search", "status": "BLOCKED"}],
            "report_markdown": "",
            "quality_assessment": {
                "score": 5.0,
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

    def test_environment_blocked_with_source_backed_ledger_recommends_review(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Example Manufacturing LLC",
            "entities": [{"type": "company", "value": "Example Manufacturing LLC", "confidence": 0.72}],
            "evidence": [],
            "evidence_ledger": [
                {
                    "id": "ev-source-1",
                    "source_url": "https://example-target.test/about",
                    "source_type": "official_site_identity",
                    "source_tool": "official_site_extractor",
                    "snippet": "Official page references Example Manufacturing LLC.",
                }
            ],
            "facts": [],
            "relationships": [],
            "hypotheses": [],
            "jobs": [{"tool_name": "official_site_search", "status": "BLOCKED"}],
            "report_markdown": "",
            "quality_assessment": {
                "score": 20.0,
                "completion_ready": False,
                "missing_keys": ["official_website", "fact_pool"],
                "blocking_keys": ["official_website", "fact_pool"],
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
        self.assertEqual(policy["recommended_status"], "NEEDS_REVIEW")
        self.assertTrue(policy["environment_blocked"])
        self.assertTrue(policy["manual_decision_required"])

    def test_environment_blocked_with_bare_cross_verification_candidate_recommends_blocked(self):
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
                "score": 5.0,
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
            "cross_verification_matrix": [
                {
                    "field_key": "company_identity",
                    "status": "CONFIRMED",
                    "candidate_value": "Example Manufacturing LLC",
                }
            ],
        }

        policy = build_completion_policy(detail)

        self.assertEqual(policy["completion_mode"], "blocked_by_environment")
        self.assertEqual(policy["recommended_status"], "BLOCKED")
        self.assertTrue(policy["environment_blocked"])
        self.assertTrue(policy["manual_decision_required"])

    def test_limited_completion_with_only_decision_maker_remaining_recommends_completed(self):
        detail = complete_company_detail()
        detail["entities"] = [
            item for item in detail["entities"] if item["type"] != "decision_maker"
        ]
        detail["quality_assessment"] = {
            "score": 78.0,
            "completion_ready": False,
            "missing_keys": ["decision_maker"],
            "blocking_keys": ["decision_maker"],
            "checks": [],
        }
        detail["gap_analysis"] = [{"gap_key": "decision_maker", "severity": "blocking"}]
        detail["gap_tool_plan"] = []
        detail["gap_followup_summary"] = {
            "total_gaps": 1,
            "blocking_gaps": 1,
            "ready": 0,
            "queued": 0,
            "already_attempted": 1,
            "blocked_by_config": 0,
            "exhausted": 1,
            "manual_review_required": 0,
        }

        policy = build_completion_policy(detail)

        self.assertEqual(policy["completion_mode"], "limited")
        self.assertEqual(policy["recommended_status"], "COMPLETED")
        self.assertTrue(policy["limited_completion_ready"])
        self.assertFalse(policy["strict_completion_ready"])
        self.assertEqual(policy["remaining_blockers"], ["decision_maker"])

    def test_limited_completion_requires_source_backed_cross_verification(self):
        detail = complete_company_detail()
        detail["entities"] = [
            item for item in detail["entities"] if item["type"] != "decision_maker"
        ]
        detail["quality_assessment"] = {
            "score": 78.0,
            "completion_ready": False,
            "missing_keys": ["decision_maker"],
            "blocking_keys": ["decision_maker"],
            "checks": [],
        }
        detail["gap_analysis"] = [{"gap_key": "decision_maker", "severity": "blocking"}]
        detail["gap_tool_plan"] = []
        detail["gap_followup_summary"] = {
            "total_gaps": 1,
            "blocking_gaps": 1,
            "ready": 0,
            "queued": 0,
            "already_attempted": 1,
            "blocked_by_config": 0,
            "exhausted": 1,
            "manual_review_required": 0,
        }
        detail["cross_verification_matrix"] = [
            {
                "field_key": "company_identity",
                "status": "SUPPORTED",
                "candidate_value": "Sample Auto Parts Co.",
            }
        ]

        policy = build_completion_policy(detail)

        self.assertNotEqual(policy["completion_mode"], "limited")
        self.assertNotEqual(policy["recommended_status"], "COMPLETED")
        self.assertFalse(policy["limited_completion_ready"])
        self.assertFalse(policy["evidence_floor"]["cross_verification"])

    def test_username_strict_quality_ready_requires_source_backed_cross_verification(self):
        detail = {
            "seed_type": "username",
            "seed_value": "sample_user",
            "entities": [
                {"type": "username", "value": "sample_user", "confidence": 0.92},
                {"type": "profile_url", "value": "https://profiles.example-target.test/sample_user", "confidence": 0.84},
            ],
            "evidence": [
                {
                    "entity_value": "sample_user",
                    "evidence_kind": "profile_observation",
                    "source_tool": "profile_lookup",
                }
            ],
            "evidence_ledger": [
                {
                    "id": "ev-profile-1",
                    "source_url": "https://profiles.example-target.test/sample_user",
                    "source_type": "public_profile",
                    "source_tool": "profile_lookup",
                    "snippet": "Public profile uses sample_user.",
                }
            ],
            "facts": [],
            "relationships": [{"from_value": "sample_user", "to_value": "https://profiles.example-target.test/sample_user"}],
            "hypotheses": [],
            "summary": "sample_user has a public profile record.",
            "quality_assessment": {
                "score": 95.0,
                "completion_ready": True,
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
            "cross_verification_matrix": [
                {
                    "field_key": "profile_identity",
                    "status": "SUPPORTED",
                    "candidate_value": "sample_user",
                }
            ],
        }

        policy = build_completion_policy(detail)

        self.assertNotEqual(policy["completion_mode"], "strict")
        self.assertNotEqual(policy["recommended_status"], "COMPLETED")

    def test_username_strict_quality_ready_rejects_bare_identity_floor(self):
        detail = {
            "seed_type": "username",
            "seed_value": "sample_user",
            "entities": [{"type": "username", "value": "sample_user", "confidence": 0.96}],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "relationships": [{"from_value": "sample_user", "to_value": "sample@example-target.test"}],
            "hypotheses": [],
            "summary": "sample_user has only a bare identity signal.",
            "quality_assessment": {
                "score": 95.0,
                "completion_ready": True,
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
            "cross_verification_matrix": [
                {
                    "field_key": "profile_identity",
                    "status": "SUPPORTED",
                    "candidate_value": "sample_user",
                }
            ],
        }

        policy = build_completion_policy(detail)

        self.assertNotEqual(policy["completion_mode"], "strict")
        self.assertNotEqual(policy["recommended_status"], "COMPLETED")
        self.assertFalse(policy["evidence_floor"]["identity"])
        self.assertFalse(policy["evidence_floor"]["source_record"])

    def test_email_limited_completion_requires_source_backed_cross_verification(self):
        detail = {
            "seed_type": "email",
            "seed_value": "sample@example-target.test",
            "entities": [
                {"type": "email", "value": "sample@example-target.test", "confidence": 0.9},
                {"type": "profile_url", "value": "https://profiles.example-target.test/sample", "confidence": 0.76},
            ],
            "evidence": [
                {
                    "entity_value": "sample@example-target.test",
                    "evidence_kind": "profile_contact",
                    "source_tool": "profile_lookup",
                }
            ],
            "evidence_ledger": [
                {
                    "id": "ev-email-1",
                    "source_url": "https://profiles.example-target.test/sample",
                    "source_type": "public_profile",
                    "source_tool": "profile_lookup",
                    "snippet": "Public profile lists sample@example-target.test.",
                }
            ],
            "facts": [],
            "relationships": [{"from_value": "sample@example-target.test", "to_value": "sample_user"}],
            "hypotheses": [],
            "risk_report": {"summary": "No high-risk conflicts identified."},
            "quality_assessment": {
                "score": 78.0,
                "completion_ready": False,
                "missing_keys": ["decision_maker"],
                "blocking_keys": ["decision_maker"],
                "checks": [],
            },
            "gap_analysis": [{"gap_key": "decision_maker", "severity": "blocking"}],
            "gap_tool_plan": [],
            "gap_followup_summary": {
                "total_gaps": 1,
                "blocking_gaps": 1,
                "ready": 0,
                "queued": 0,
                "already_attempted": 1,
                "blocked_by_config": 0,
                "exhausted": 1,
                "manual_review_required": 0,
            },
            "cross_verification_matrix": [
                {
                    "field_key": "profile_contact",
                    "status": "SUPPORTED",
                    "candidate_value": "sample@example-target.test",
                }
            ],
        }

        policy = build_completion_policy(detail)

        self.assertNotEqual(policy["completion_mode"], "limited")
        self.assertNotEqual(policy["recommended_status"], "COMPLETED")
        self.assertFalse(policy["limited_completion_ready"])

    def test_company_limited_completion_rejects_bare_email_contact_limitation(self):
        detail = complete_company_detail()
        detail["entities"] = [
            item for item in detail["entities"] if item["type"] not in {"phone", "decision_maker"}
        ]
        detail["evidence"] = []
        detail["evidence_ledger"] = [
            {
                "id": "ev-1",
                "source_url": "https://example-target.test/about",
                "source_type": "official_site_profile",
                "source_tool": "official_site_extractor",
                "admiralty_code": "A-2",
                "snippet": "Official profile confirms Sample Auto Parts Co. and its business scope.",
            }
        ]
        detail["facts"] = [
            {
                "id": "fact-1",
                "statement": "Sample Auto Parts Co. distributes auto parts.",
                "predicate": "business_scope",
                "object": "auto parts distribution",
                "status": "CONFIRMED",
                "promotion_stage": "ACCEPTED_FACT",
                "confidence": 0.82,
                "evidence_ids": ["ev-1"],
            }
        ]
        detail["relationships"] = []
        detail["quality_assessment"] = {
            "score": 78.0,
            "completion_ready": False,
            "missing_keys": ["contact_phone"],
            "blocking_keys": ["contact_phone"],
            "checks": [],
        }
        detail["gap_analysis"] = [{"gap_key": "contact_phone", "severity": "blocking"}]
        detail["gap_tool_plan"] = []
        detail["gap_followup_summary"] = {
            "total_gaps": 1,
            "blocking_gaps": 1,
            "ready": 0,
            "queued": 0,
            "already_attempted": 1,
            "blocked_by_config": 0,
            "exhausted": 1,
            "manual_review_required": 0,
        }
        detail["cross_verification_matrix"] = [
            {
                "field_key": "company_identity",
                "status": "SUPPORTED",
                "candidate_value": "Sample Auto Parts Co.",
                "linked_evidence_ids": ["ev-1"],
                "linked_fact_ids": ["fact-1"],
            }
        ]

        policy = build_completion_policy(detail)

        self.assertNotIn("contact_phone", policy["acceptable_limitations"])
        self.assertNotEqual(policy["completion_mode"], "limited")
        self.assertNotEqual(policy["recommended_status"], "COMPLETED")
        self.assertFalse(policy["limited_completion_ready"])

    def test_non_waivable_blocker_prevents_limited_completion(self):
        detail = complete_company_detail()
        detail["entities"] = [
            item for item in detail["entities"] if item["type"] not in {"domain", "url"}
        ]
        detail["evidence_ledger"] = [
            {
                "id": "ev-1",
                "source_url": "https://example-target.test/contact",
                "source_type": "official_site_contact",
                "source_tool": "official_site_extractor",
                "admiralty_code": "A-2",
                "snippet": "Official contact page lists sales@example-target.test.",
            },
            {
                "id": "ev-2",
                "source_type": "business_registry",
                "source_tool": "registry_lookup",
                "admiralty_code": "B-2",
                "snippet": "Registry profile confirms Example Manufacturing LLC identity.",
            },
        ]
        detail["quality_assessment"] = {
            "score": 70.0,
            "completion_ready": False,
            "missing_keys": ["official_website"],
            "blocking_keys": ["official_website"],
            "checks": [],
        }
        detail["gap_analysis"] = [{"gap_key": "official_website", "severity": "blocking"}]
        detail["gap_tool_plan"] = []
        detail["gap_followup_summary"] = {
            "total_gaps": 1,
            "blocking_gaps": 1,
            "ready": 0,
            "queued": 0,
            "already_attempted": 1,
            "blocked_by_config": 0,
            "exhausted": 1,
            "manual_review_required": 0,
        }

        policy = build_completion_policy(detail)

        self.assertEqual(policy["completion_mode"], "ready_for_human_decision")
        self.assertEqual(policy["recommended_status"], "NEEDS_REVIEW")
        self.assertFalse(policy["limited_completion_ready"])
        self.assertIn("official_website", policy["remaining_blockers"])

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

    def test_representative_policies_return_required_key_set(self):
        details = [
            complete_company_detail(),
            {
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
            },
            {
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
            },
        ]

        for detail in details:
            with self.subTest(seed_type=detail["seed_type"], seed_value=detail["seed_value"]):
                self.assertEqual(set(build_completion_policy(detail)), REQUIRED_POLICY_KEYS)
