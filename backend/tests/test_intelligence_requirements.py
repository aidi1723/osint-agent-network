import unittest

from app.core.intelligence_requirements import (
    DEFAULT_EEI_STATUS,
    DEFAULT_PIR_STATUS,
    build_intelligence_requirements,
    requirement_coverage,
)


class IntelligenceRequirementsTests(unittest.TestCase):
    def test_company_defaults_include_identity_purchase_contact_and_risk(self):
        req = build_intelligence_requirements("company", "Sample Hospitality LLC", "standard", {})

        pir_ids = {item["id"] for item in req["pirs"]}
        eei_ids = {item["id"] for item in req["eeis"]}

        self.assertIn("pir_identity", pir_ids)
        self.assertIn("pir_purchase_capacity", pir_ids)
        self.assertIn("pir_contact_confidence", pir_ids)
        self.assertIn("pir_risk", pir_ids)
        self.assertIn("eei_company_identity", eei_ids)
        self.assertIn("eei_official_website", eei_ids)
        self.assertIn("eei_contact_email", eei_ids)
        self.assertEqual(req["pirs"][0]["status"], DEFAULT_PIR_STATUS)
        self.assertEqual(req["eeis"][0]["status"], DEFAULT_EEI_STATUS)

    def test_sparse_lead_defaults_include_identity_match_pir(self):
        req = build_intelligence_requirements(
            "sparse_lead",
            "Sample Lead / member-redacted",
            "quick",
            {"country_region": "IN", "platform": "Alibaba"},
        )

        questions = " ".join(item["question"] for item in req["pirs"])
        eei_ids = {item["id"] for item in req["eeis"]}

        self.assertIn("same buyer", questions.lower())
        self.assertIn("eei_platform_anchor", eei_ids)
        self.assertIn("eei_identity_match", eei_ids)

    def test_normalizes_operator_supplied_requirements(self):
        req = build_intelligence_requirements(
            "domain",
            "example.com",
            "deep",
            {
                "intelligence_requirements": {
                    "decision_context": "qualify supplier",
                    "confidence_requirement": "strict",
                    "pirs": [{"question": "Is this domain official?", "priority": "high"}],
                    "eeis": [{"label": "WHOIS or official page", "field_key": "official_website"}],
                }
            },
        )

        self.assertEqual(req["decision_context"], "qualify supplier")
        self.assertEqual(req["confidence_requirement"], "strict")
        self.assertEqual(req["pirs"][0]["id"], "pir_custom_1")
        self.assertEqual(req["eeis"][0]["id"], "eei_custom_1")
        self.assertTrue(req["eeis"][0]["required"])

    def test_requirement_coverage_counts_answered_and_confirmed_items(self):
        req = build_intelligence_requirements("email", "buyer@example.com", "standard", {})
        req["pirs"][0]["status"] = "ANSWERED"
        req["eeis"][0]["status"] = "CONFIRMED"

        coverage = requirement_coverage(req)

        self.assertGreater(coverage["pir_answered"], 0)
        self.assertGreater(coverage["eei_confirmed"], 0)
        self.assertGreater(coverage["required_eei_total"], 0)


if __name__ == "__main__":
    unittest.main()
