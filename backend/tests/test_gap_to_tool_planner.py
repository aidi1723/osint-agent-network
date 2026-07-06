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
