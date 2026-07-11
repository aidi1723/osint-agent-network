import unittest

from app.core.cross_verification import build_cross_verification_matrix, classify_source_family


class CrossVerificationTests(unittest.TestCase):
    def test_classifies_source_family(self):
        self.assertEqual(classify_source_family("official_website", "official_web"), "official")
        self.assertEqual(classify_source_family("registry", "state_registry"), "registry")
        self.assertEqual(classify_source_family("news", "company_news"), "news")
        self.assertEqual(classify_source_family("tool", "theHarvester"), "tool")

    def test_confirms_identity_with_official_and_registry_sources(self):
        detail = {
            "entities": [
                {"id": "e1", "type": "company", "value": "Example LLC", "source_tool": "official_web", "confidence": 0.8},
                {"id": "e2", "type": "company", "value": "Example LLC", "source_tool": "state_registry", "confidence": 0.9},
            ],
            "evidence_ledger": [
                {"id": "ev1", "source_type": "official_website", "source_tool": "official_web", "source_url": "https://example.com", "admiralty_code": "A-2", "snippet": "Example LLC"},
                {"id": "ev2", "source_type": "registry", "source_tool": "state_registry", "source_url": "https://registry.example", "admiralty_code": "A-2", "snippet": "Example LLC"},
            ],
            "facts": [
                {"id": "f1", "subject": "Example LLC", "predicate": "identity", "object": "Example LLC", "status": "CONFIRMED", "promotion_stage": "ACCEPTED_FACT", "confidence": 0.9, "evidence_ids": ["ev1", "ev2"]},
            ],
            "evidence": [],
            "relationships": [],
        }

        rows = build_cross_verification_matrix(detail)
        identity = next(row for row in rows if row["field_key"] == "company_identity")

        self.assertEqual(identity["status"], "CONFIRMED")
        self.assertEqual(identity["candidate_value"], "Example LLC")
        self.assertEqual(identity["independent_source_count"], 2)
        self.assertIn("official", identity["supporting_sources"])
        self.assertIn("registry", identity["supporting_sources"])

    def test_flags_conflicting_contact_values(self):
        detail = {
            "entities": [
                {"id": "e1", "type": "email", "value": "sales@example.com", "source_tool": "official_web", "confidence": 0.8},
                {"id": "e2", "type": "email", "value": "info@other.example", "source_tool": "directory_site", "confidence": 0.6},
            ],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "relationships": [],
        }

        rows = build_cross_verification_matrix(detail)
        email = next(row for row in rows if row["field_key"] == "contact_email")

        self.assertEqual(email["status"], "CONFLICTED")
        self.assertIn("directory", email["contradicting_sources"])

    def test_same_official_source_can_publish_multiple_phone_numbers(self):
        detail = {
            "entities": [
                {
                    "id": "phone-primary",
                    "type": "phone",
                    "value": "+12125550101",
                    "source_tool": "official_site_extractor",
                    "confidence": 0.82,
                },
                {
                    "id": "phone-secondary",
                    "type": "phone",
                    "value": "+12125550102",
                    "source_tool": "official_site_extractor",
                    "confidence": 0.78,
                },
            ],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "relationships": [],
        }

        rows = build_cross_verification_matrix(detail)
        phone = next(row for row in rows if row["field_key"] == "contact_phone")

        self.assertNotEqual(phone["status"], "CONFLICTED")
        self.assertEqual(phone["contradicting_sources"], [])

    def test_equivalent_official_website_url_and_domain_do_not_conflict(self):
        detail = {
            "entities": [
                {"id": "e-domain", "type": "domain", "value": "example-target.test", "source_tool": "official_site_search", "confidence": 0.74},
                {"id": "e-url", "type": "url", "value": "https://www.example-target.test/", "source_tool": "httpx", "confidence": 0.72},
            ],
            "facts": [
                {
                    "id": "fact-site",
                    "subject": "Sample Auto Parts Co.",
                    "predicate": "official_website",
                    "object": "https://example-target.test",
                    "status": "CONFIRMED",
                    "promotion_stage": "ACCEPTED_FACT",
                    "confidence": 0.84,
                    "evidence_ids": ["ev-site"],
                }
            ],
            "evidence_ledger": [
                {
                    "id": "ev-site",
                    "source_type": "official_site_profile",
                    "source_tool": "official_site_extractor",
                    "source_url": "https://example-target.test/about",
                    "admiralty_code": "A-2",
                    "snippet": "Official profile confirms https://example-target.test as the website.",
                }
            ],
            "evidence": [],
            "relationships": [],
        }

        rows = build_cross_verification_matrix(detail)
        website = next(row for row in rows if row["field_key"] == "official_website")

        self.assertNotEqual(website["status"], "CONFLICTED")
        self.assertEqual(website["contradicting_sources"], [])
        self.assertIn("official", website["supporting_sources"])
        self.assertIn("tool", website["supporting_sources"])
        self.assertIn("ev-site", website["linked_evidence_ids"])
        self.assertIn("fact-site", website["linked_fact_ids"])

    def test_distinct_official_website_domains_explain_conflict_sources(self):
        detail = {
            "entities": [
                {"id": "e-official", "type": "url", "value": "https://example-target.test", "source_tool": "official_site_search", "confidence": 0.84},
                {"id": "e-directory", "type": "url", "value": "https://conflicting-target.test", "source_tool": "directory_site", "confidence": 0.62},
            ],
            "evidence": [],
            "evidence_ledger": [],
            "facts": [],
            "relationships": [],
        }

        rows = build_cross_verification_matrix(detail)
        website = next(row for row in rows if row["field_key"] == "official_website")

        self.assertEqual(website["status"], "CONFLICTED")
        self.assertIn("directory", website["contradicting_sources"])
        self.assertIn("conflicting-target.test", website["rationale"])
        self.assertIn("directory", website["rationale"])

    def test_privacy_state_does_not_satisfy_email_or_phone_fields(self):
        detail = {
            "entities": [
                {
                    "id": "e1",
                    "type": "privacy_state",
                    "value": "email_hidden_phone_hidden",
                    "source_tool": "lead_anchor_extraction",
                    "confidence": 0.9,
                }
            ],
            "facts": [
                {
                    "id": "f1",
                    "subject": "Example Buyer",
                    "predicate": "has_privacy_state",
                    "object": "email_hidden_phone_hidden",
                    "statement": "Example Buyer has_privacy_state email_hidden_phone_hidden.",
                    "status": "CONFIRMED",
                    "promotion_stage": "ACCEPTED_FACT",
                    "confidence": 0.9,
                    "evidence_ids": ["ev1"],
                }
            ],
            "evidence_ledger": [
                {
                    "id": "ev1",
                    "source_type": "role_agent_collection",
                    "source_tool": "lead_anchor_extraction",
                    "source_url": "hcs://lead",
                    "admiralty_code": "F-3",
                    "snippet": "privacy_state=email_hidden_phone_hidden",
                }
            ],
            "evidence": [],
            "relationships": [],
        }

        rows = build_cross_verification_matrix(detail)
        email = next(row for row in rows if row["field_key"] == "contact_email")
        phone = next(row for row in rows if row["field_key"] == "contact_phone")

        self.assertEqual(email["status"], "MISSING")
        self.assertEqual(phone["status"], "MISSING")
        self.assertEqual(email["candidate_value"], "")
        self.assertEqual(phone["candidate_value"], "")

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


if __name__ == "__main__":
    unittest.main()
