import unittest

from app.core.gap_followups import build_gap_analysis, build_gap_tool_plan


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


if __name__ == "__main__":
    unittest.main()
