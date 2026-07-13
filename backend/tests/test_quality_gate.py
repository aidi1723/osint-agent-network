import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.intelligence_memory import build_intelligence_memory
from app.core.quality import build_quality_assessment, completion_status_for_detail, render_structured_report
from app.services.store import SQLiteStore


class QualityGateTests(unittest.TestCase):
    def test_report_renders_completion_policy_section(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Sample Auto Parts Co.",
            "entities": [],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "hypotheses": [],
            "relationships": [],
            "report_markdown": "## BLUF\nSample Auto Parts Co. has source-backed contact and scope evidence.",
            "quality_assessment": {
                "score": 84.0,
                "completion_ready": False,
                "missing_keys": ["decision_maker"],
                "blocking_keys": ["decision_maker"],
                "checks": [],
            },
            "completion_policy": {
                "recommended_status": "COMPLETED",
                "completion_mode": "limited",
                "strict_completion_ready": False,
                "limited_completion_ready": True,
                "auto_exhausted": True,
                "manual_decision_required": False,
                "environment_blocked": False,
                "reason": "Core evidence floor is satisfied; only acceptable limitations remain: decision_maker.",
                "remaining_blockers": ["decision_maker"],
                "acceptable_limitations": ["decision_maker"],
                "operator_next_actions": [
                    "Manually verify decision-maker from an official team page, public profile, or trusted directory."
                ],
                "evidence_floor": {},
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
            "cross_verification_matrix": [],
        }

        report = render_structured_report(detail, detail["quality_assessment"])

        self.assertIn("## 完成策略", report)
        self.assertIn("limited", report)
        self.assertIn("decision_maker", report)
        self.assertIn("Manually verify decision-maker", report)

    def test_quality_assessment_marks_sparse_results_incomplete(self):
        detail = {
            "seed_value": "Sample Hospitality LLC",
            "entities": [{"type": "company", "value": "Sample Hospitality LLC", "confidence": 0.7}],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "hypotheses": [],
            "relationships": [],
            "report_markdown": "",
        }

        assessment = build_quality_assessment(detail)

        self.assertLess(assessment["score"], 50)
        self.assertFalse(assessment["completion_ready"])
        self.assertIn("official_website", assessment["missing_keys"])
        self.assertIn("evidence_ledger", assessment["missing_keys"])
        self.assertIn("bluf_report", assessment["missing_keys"])

    def test_low_confidence_platform_identity_keeps_decision_maker_gap(self):
        detail = {
            "seed_value": "Sample Sparse Lead / Contact A",
            "entities": [
                {"type": "company", "value": "Sample Sparse Lead / Contact A", "confidence": 0.62},
                {"type": "identity", "value": "Contact A", "confidence": 0.62, "source_tool": "candidate_business_discovery"},
            ],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "hypotheses": [],
            "relationships": [],
            "jobs": [],
            "report_markdown": "",
        }

        assessment = build_quality_assessment(detail)
        memory = build_intelligence_memory(detail)

        self.assertIn("decision_maker", assessment["missing_keys"])
        self.assertTrue(any(gap["key"] == "decision_maker" for gap in memory["collection_gaps"]))

    def test_quality_assessment_accepts_evidence_backed_report(self):
        detail = {
            "seed_value": "Sample Auto Parts Co.",
            "entities": [
                {"type": "company", "value": "Sample Auto Parts Co.", "confidence": 0.9},
                {"type": "domain", "value": "example-target.test", "confidence": 0.8},
                {"type": "email", "value": "xs@csituo.com", "confidence": 0.8},
                {"type": "phone", "value": "+86-991-3966766", "confidence": 0.76},
                {"type": "address", "value": "Urumqi, Xinjiang", "confidence": 0.72},
                {"type": "business_scope", "value": "auto parts", "confidence": 0.8},
                {"type": "product_scope", "value": "spare parts", "confidence": 0.75},
                {"type": "decision_maker", "value": "Export manager candidate", "confidence": 0.62},
            ],
            "evidence": [{"entity_value": "xs@csituo.com", "evidence_kind": "contact_page", "source_tool": "agent"}],
            "evidence_ledger": [{"id": "ev-1", "source_url": "https://example.com", "admiralty_code": "A-2"}],
            "facts": [
                {
                    "id": "fact-1",
                    "statement": "SampleCo lists xs@csituo.com as a contact email.",
                    "status": "CONFIRMED",
                    "promotion_stage": "ACCEPTED_FACT",
                    "confidence": 0.82,
                    "evidence_ids": ["ev-1"],
                }
            ],
            "hypotheses": [{"id": "h1", "status": "MOST_LIKELY", "support_score": 0.8}],
            "relationships": [{"from_value": "Sample Auto Parts Co.", "to_value": "xs@csituo.com"}],
            "report_markdown": "## BLUF\nSampleCo is likely an active export-facing auto parts supplier.",
            "intelligence_requirements": {
                "pirs": [{"id": "pir_identity", "status": "ANSWERED"}],
                "eeis": [{"id": "eei_company_identity", "field_key": "company_identity", "required": True, "status": "CONFIRMED"}],
            },
            "cross_verification_matrix": [
                {"field_key": "company_identity", "status": "CONFIRMED", "candidate_value": "Sample Auto Parts Co."}
            ],
        }

        assessment = build_quality_assessment(detail)

        self.assertGreaterEqual(assessment["score"], 80)
        self.assertTrue(assessment["completion_ready"])
        self.assertEqual(completion_status_for_detail(detail, requested_status="COMPLETED"), "COMPLETED")

    def test_completion_gate_downgrades_incomplete_completed_status(self):
        detail = {
            "seed_value": "No Evidence LLC",
            "entities": [{"type": "company", "value": "No Evidence LLC", "confidence": 0.7}],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "hypotheses": [],
            "relationships": [],
            "report_markdown": "short summary",
        }

        self.assertEqual(
            completion_status_for_detail(detail, requested_status="COMPLETED"),
            "NEEDS_REVIEW",
        )

    def test_completion_gate_blocks_high_score_without_business_closure(self):
        detail = {
            "seed_value": "Sample Sparse Lead / Contact A",
            "entities": [
                {"type": "company", "value": "Sample Sparse Lead / Contact A", "confidence": 0.82},
                {"type": "business_scope", "value": "Truck Spare Parts", "confidence": 0.72},
                {"type": "country_region", "value": "Zambia", "confidence": 0.7},
            ],
            "evidence": [{"entity_value": "Truck Spare Parts", "evidence_kind": "platform_business_scope_candidate"}],
            "evidence_ledger": [{"id": "ev-1", "source_url": "hcs://role-agent", "admiralty_code": "C-3"}],
            "facts": [
                {
                    "id": "fact-1",
                    "statement": "The lead is associated with truck spare parts.",
                    "status": "LIKELY",
                    "promotion_stage": "ACCEPTED_FACT",
                    "confidence": 0.72,
                    "evidence_ids": ["ev-1"],
                }
            ],
            "hypotheses": [{"id": "alpha_real_procurement", "status": "MOST_LIKELY"}],
            "relationships": [{"from_value": "Sample Sparse Lead / Contact A", "to_value": "Truck Spare Parts"}],
            "report_markdown": "## BLUF\nThe lead has useful but incomplete public evidence.",
            "intelligence_requirements": {
                "pirs": [{"id": "pir_identity", "status": "ANSWERED"}],
                "eeis": [{"id": "eei_company_identity", "field_key": "company_identity", "required": True, "status": "LIKELY"}],
            },
            "cross_verification_matrix": [
                {"field_key": "company_identity", "status": "LIKELY", "candidate_value": "Sample Sparse Lead / Contact A"}
            ],
        }

        assessment = build_quality_assessment(detail)

        self.assertGreaterEqual(assessment["score"], assessment["minimum_score"])
        self.assertFalse(assessment["completion_ready"])
        self.assertIn("official_website", assessment["blocking_keys"])
        self.assertIn("contact_channel", assessment["blocking_keys"])
        self.assertIn("decision_maker", assessment["blocking_keys"])

    def test_official_site_person_candidate_satisfies_decision_maker_signal_only(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Sample Auto Parts Co.",
            "entities": [
                {"type": "company", "value": "Sample Auto Parts Co.", "confidence": 0.82},
                {"type": "url", "value": "https://example.com/team", "confidence": 0.72},
                {"type": "person", "value": "Jane Smith", "confidence": 0.66, "source_tool": "official_site_extractor"},
                {"type": "job_title", "value": "Export Manager", "confidence": 0.66, "source_tool": "official_site_extractor"},
                {
                    "type": "decision_maker",
                    "value": "Jane Smith - Export Manager",
                    "confidence": 0.66,
                    "source_tool": "official_site_extractor",
                },
            ],
            "evidence": [
                {
                    "entity_value": "Jane Smith",
                    "evidence_kind": "official_site_decision_maker_candidate",
                    "source_tool": "official_site_extractor",
                }
            ],
            "evidence_ledger": [],
            "facts": [],
            "hypotheses": [],
            "relationships": [
                {
                    "from_value": "https://example.com/team",
                    "to_value": "Jane Smith",
                    "relationship_type": "official_site_mentions_decision_maker",
                }
            ],
            "report_markdown": "",
        }

        assessment = build_quality_assessment(detail)

        self.assertNotIn("decision_maker", assessment["missing_keys"])
        self.assertIn("evidence_ledger", assessment["blocking_keys"])
        self.assertFalse(assessment["completion_ready"])

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

    def test_domain_recon_quality_gate_does_not_require_decision_maker(self):
        detail = {
            "seed_type": "domain",
            "seed_value": "example-target.test",
            "entities": [
                {"type": "organization", "value": "SAMPLE AUTO PARTS COMPANY LIMITED", "confidence": 0.76},
                {"type": "url", "value": "https://example-target.test", "confidence": 0.72},
                {"type": "phone", "value": "+85282061801", "confidence": 0.78},
                {"type": "business_scope", "value": "auto parts", "confidence": 0.74},
            ],
            "evidence": [{"entity_value": "auto parts", "evidence_kind": "official_site_business_scope"}],
            "evidence_ledger": [{"id": "ev-1", "source_url": "https://example-target.test", "admiralty_code": "A-2"}],
            "facts": [
                {
                    "id": "fact-identity",
                    "predicate": "has_company_identity",
                    "object": "SAMPLE AUTO PARTS COMPANY LIMITED",
                    "status": "CONFIRMED",
                    "promotion_stage": "ACCEPTED_FACT",
                    "evidence_ids": ["ev-1"],
                }
            ],
            "hypotheses": [],
            "relationships": [{"from_value": "https://example-target.test", "to_value": "auto parts"}],
            "report_markdown": "## BLUF\nOfficial site source-backed domain reconnaissance is complete.",
            "intelligence_requirements": {
                "pirs": [{"id": "pir_identity", "status": "ANSWERED"}],
                "eeis": [{"id": "eei_company_identity", "field_key": "company_identity", "required": True, "status": "CONFIRMED"}],
            },
            "cross_verification_matrix": [
                {"field_key": "company_identity", "status": "CONFIRMED", "candidate_value": "SAMPLE AUTO PARTS COMPANY LIMITED"},
                {"field_key": "official_website", "status": "CONFIRMED", "candidate_value": "https://example-target.test"},
                {"field_key": "business_scope", "status": "CONFIRMED", "candidate_value": "auto parts"},
            ],
        }

        assessment = build_quality_assessment(detail)

        self.assertIn("decision_maker", assessment["missing_keys"])
        self.assertNotIn("decision_maker", assessment["blocking_keys"])

    def test_structured_report_uses_facts_gaps_and_actions(self):
        detail = {
            "name": "SampleCo core report",
            "seed_value": "Sample Auto Parts Co.",
            "summary": "Agent summary",
            "facts": [
                {
                    "statement": "SampleCo lists xs@csituo.com as a contact email.",
                    "status": "CONFIRMED",
                    "confidence": 0.82,
                    "admiralty_code": "A-2",
                }
            ],
            "evidence_ledger": [
                {
                    "source_url": "https://www.example-target.test/en/contact",
                    "source_type": "official_website",
                    "admiralty_code": "A-2",
                    "snippet": "Contact page lists xs@csituo.com.",
                }
            ],
            "hypothesis_analysis": {"most_likely_hypothesis": "h1", "confidence_language": "很有可能"},
            "intelligence_memory": {
                "collection_gaps": [{"label": "决策人", "reason": "缺少负责人公开主页"}],
                "directed_collection": [{"agent_focus": "决策人", "prompt": "继续查官网团队页"}],
            },
        }

        report = render_structured_report(detail, build_quality_assessment(detail))

        self.assertIn("## BLUF", report)
        self.assertIn("## 已确认事实", report)
        self.assertIn("SampleCo lists xs@csituo.com", report)
        self.assertIn("## 情报缺口", report)
        self.assertIn("继续查官网团队页", report)

    def test_structured_report_includes_gap_followup_plan(self):
        detail = {
            "name": "Example Manufacturing LLC",
            "seed_value": "Example Manufacturing LLC",
            "summary": "Needs review.",
            "entities": [],
            "facts": [],
            "evidence_ledger": [],
            "relationships": [],
            "hypotheses": [],
            "report_markdown": "## BLUF\nNeeds review.",
            "gap_analysis": [
                {
                    "gap_key": "official_website",
                    "label": "Official website",
                    "severity": "blocking",
                    "current_state": "No accepted official website or domain is linked to the target.",
                    "missing_evidence": [
                        "Official domain or URL tied to the target",
                        "Page title or snippet showing target identity",
                    ],
                    "why_it_matters": "The task cannot be completed confidently without an official source boundary.",
                    "manual_review_hint": "Inspect public registry if automated search remains inconclusive.",
                }
            ],
            "gap_tool_plan": [
                {
                    "gap_key": "official_website",
                    "tool_name": "official_site_search",
                    "status": "ready",
                    "reason": "Find official website candidates before crawling pages.",
                },
                {
                    "gap_key": "official_website",
                    "tool_name": "httpx",
                    "status": "missing_executable",
                    "health_reason": "executable not found: httpx",
                },
                {
                    "gap_key": "official_website",
                    "tool_name": "company_osint",
                    "status": "already_attempted",
                },
            ],
        }

        report = render_structured_report(detail, build_quality_assessment(detail))

        self.assertIn("## 卡点与补采计划", report)
        self.assertIn("Official website", report)
        self.assertIn("Official domain or URL tied to the target", report)
        self.assertIn("可自动补采：official_site_search", report)
        self.assertIn("已尝试：company_osint", report)
        self.assertIn("环境/配置阻塞：httpx", report)
        self.assertIn("executable not found: httpx", report)
        self.assertIn("Inspect public registry", report)

    def test_environment_coverage_limit_is_reported_without_changing_completion(self):
        detail = {
            "seed_type": "domain",
            "seed_value": "example-target.test",
            "entities": [
                {"type": "organization", "value": "SampleCo", "confidence": 0.8},
                {"type": "domain", "value": "example-target.test", "confidence": 0.8},
                {"type": "email", "value": "contact@example-target.test", "confidence": 0.8},
                {"type": "phone", "value": "+1-555-0100", "confidence": 0.8},
                {"type": "business_scope", "value": "industrial components", "confidence": 0.8},
            ],
            "evidence_ledger": [{"id": "ev-1", "source_url": "https://example-target.test", "admiralty_code": "A-2"}],
            "facts": [
                {
                    "id": "fact-1",
                    "statement": "SampleCo publishes a contact channel.",
                    "status": "CONFIRMED",
                    "promotion_stage": "ACCEPTED_FACT",
                    "confidence": 0.8,
                    "evidence_ids": ["ev-1"],
                }
            ],
            "hypotheses": [{"id": "h1", "status": "MOST_LIKELY"}],
            "relationships": [{"from_value": "SampleCo", "to_value": "example-target.test"}],
            "report_markdown": "## BLUF\nSampleCo has source-backed public business evidence.",
            "intelligence_requirements": {
                "pirs": [{"id": "pir-1", "status": "ANSWERED"}],
                "eeis": [{"id": "eei-1", "field_key": "company_identity", "required": True, "status": "CONFIRMED"}],
            },
            "cross_verification_matrix": [
                {"field_key": "company_identity", "status": "CONFIRMED", "candidate_value": "SampleCo"}
            ],
            "gap_analysis": [],
            "gap_tool_plan": [],
        }
        tool_health = {
            "summary": {
                "affected_capabilities": {
                    "asset_discovery": ["amass"],
                    "social_identity": ["socialscan"],
                }
            },
            "tools": [],
        }

        assessment_before = build_quality_assessment(detail)
        status_before = completion_status_for_detail(detail, requested_status="COMPLETED")
        report = render_structured_report(detail, assessment_before, tool_health=tool_health)
        assessment_after = build_quality_assessment({**detail, "tool_health": tool_health})
        status_after = completion_status_for_detail({**detail, "tool_health": tool_health}, requested_status="COMPLETED")

        self.assertIn("## 环境覆盖限制", report)
        self.assertIn("asset_discovery", report)
        self.assertIn("amass", report)
        self.assertIn("social_identity", report)
        self.assertIn("socialscan", report)
        self.assertLess(report.index("## 卡点与补采计划"), report.index("## 环境覆盖限制"))
        self.assertLess(report.index("## 环境覆盖限制"), report.index("## EEI 覆盖摘要"))
        self.assertEqual(assessment_after["completion_ready"], assessment_before["completion_ready"])
        self.assertEqual(status_after, status_before)

    def test_sqlite_complete_task_applies_quality_gate_and_structured_report(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            investigation = store.create_investigation(
                name="Incomplete company",
                seed_type="company",
                seed_value="Incomplete LLC",
                strategy_name="standard",
            )
            updated = store.complete_task(
                investigation_id=investigation.id,
                agent_id="agent-1",
                status="COMPLETED",
                summary="Done",
                report_markdown="Done",
                confidence=0.9,
            )

        self.assertEqual(updated["status"], "NEEDS_REVIEW")
        self.assertIn("quality_assessment", updated)
        self.assertLess(updated["quality_assessment"]["score"], 50)
        self.assertIn("## BLUF", updated["report_markdown"])

    def test_quality_assessment_includes_core_v3_checks(self):
        detail = {
            "seed_value": "Example LLC",
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

    def test_quality_assessment_counts_verified_matrix_fields_without_entities(self):
        detail = {
            "seed_value": "Sample Auto Parts Co. / SAMPLE AUTO PARTS COMPANY LIMITED",
            "entities": [],
            "evidence_ledger": [{"id": "ev-1", "source_url": "https://example.com/contact", "admiralty_code": "A-2"}],
            "facts": [
                {
                    "id": "fact-email",
                    "subject": "Sample Auto Parts Co.",
                    "predicate": "uses_contact_email",
                    "object": "xs@csituo.com",
                    "status": "CONFIRMED",
                    "promotion_stage": "ACCEPTED_FACT",
                    "evidence_ids": ["ev-1"],
                },
                {
                    "id": "fact-phone",
                    "subject": "Sample Auto Parts Co.",
                    "predicate": "uses_contact_phone",
                    "object": "0991-3966766 / 0991-3966788",
                    "status": "CONFIRMED",
                    "promotion_stage": "ACCEPTED_FACT",
                    "evidence_ids": ["ev-1"],
                },
                {
                    "id": "fact-location",
                    "subject": "Sample Auto Parts Co.",
                    "predicate": "has_operation_location",
                    "object": "Guangzhou",
                    "status": "CONFIRMED",
                    "promotion_stage": "ACCEPTED_FACT",
                    "evidence_ids": ["ev-1"],
                },
                {
                    "id": "fact-scope",
                    "subject": "Sample Auto Parts Co.",
                    "predicate": "has_business_scope",
                    "object": "shock absorber; suspension; braking",
                    "status": "CONFIRMED",
                    "promotion_stage": "ACCEPTED_FACT",
                    "evidence_ids": ["ev-1"],
                },
            ],
            "relationships": [],
            "hypotheses": [],
            "report_markdown": "# BLUF\nSampleCo contact and product fields are supported.",
            "intelligence_requirements": {
                "pirs": [{"id": "pir_contact_confidence", "status": "ANSWERED"}],
                "eeis": [
                    {"id": "eei_contact_email", "field_key": "contact_email", "required": False, "status": "CONFIRMED"},
                    {"id": "eei_contact_phone", "field_key": "contact_phone", "required": False, "status": "CONFIRMED"},
                    {"id": "eei_operation_location", "field_key": "operation_location", "required": True, "status": "CONFIRMED"},
                    {"id": "eei_business_scope", "field_key": "business_scope", "required": True, "status": "CONFIRMED"},
                ],
            },
            "cross_verification_matrix": [
                {"field_key": "company_identity", "status": "MISSING", "candidate_value": ""},
                {"field_key": "official_website", "status": "MISSING", "candidate_value": ""},
                {"field_key": "contact_email", "status": "CONFIRMED", "candidate_value": "xs@csituo.com"},
                {"field_key": "contact_phone", "status": "CONFIRMED", "candidate_value": "0991-3966766 / 0991-3966788"},
                {"field_key": "operation_location", "status": "CONFIRMED", "candidate_value": "Guangzhou"},
                {"field_key": "business_scope", "status": "CONFIRMED", "candidate_value": "shock absorber; suspension; braking"},
                {"field_key": "decision_maker", "status": "MISSING", "candidate_value": ""},
            ],
        }

        assessment = build_quality_assessment(detail)

        self.assertNotIn("contact_email", assessment["missing_keys"])
        self.assertNotIn("contact_phone", assessment["missing_keys"])
        self.assertNotIn("operation_location", assessment["missing_keys"])
        self.assertNotIn("business_scope", assessment["missing_keys"])
        self.assertIn("company_identity", assessment["missing_keys"])
        self.assertIn("official_website", assessment["missing_keys"])
        self.assertIn("decision_maker", assessment["missing_keys"])

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


if __name__ == "__main__":
    unittest.main()
