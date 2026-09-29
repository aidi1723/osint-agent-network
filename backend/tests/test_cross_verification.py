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


if __name__ == "__main__":
    unittest.main()
