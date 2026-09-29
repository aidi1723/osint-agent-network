import unittest

from app.core.osint_fusion import derive_osint_signals
from app.tools.base import (
    NormalizedEntity,
    NormalizedEvidence,
    NormalizedRelationship,
    ParsedToolOutput,
)


class OsintFusionTests(unittest.TestCase):
    def test_amass_subdomain_and_ip_map_to_organization_asset_candidates(self):
        parsed = ParsedToolOutput(
            tool="amass",
            target_type="domain",
            target_value="example.com",
            entities=[
                NormalizedEntity("domain", "example.com", "amass", 0.5),
                NormalizedEntity("subdomain", "vpn.example.com", "amass", 0.5),
                NormalizedEntity("ip", "203.0.113.10", "amass", 0.45),
            ],
            evidence=[
                NormalizedEvidence("vpn.example.com", "amass_name_discovery", "amass", "Amass discovered vpn.example.com via crtsh"),
                NormalizedEvidence("203.0.113.10", "dns_resolution", "amass", "Amass linked vpn.example.com to 203.0.113.10"),
            ],
            relationships=[
                NormalizedRelationship("example.com", "vpn.example.com", "domain_has_subdomain", 0.5),
                NormalizedRelationship("vpn.example.com", "203.0.113.10", "subdomain_resolves_to_ip", 0.45),
            ],
        )

        signals = derive_osint_signals(parsed)
        by_value = {signal.entity_value: signal for signal in signals}

        self.assertEqual(by_value["vpn.example.com"].core_axis, "organization_asset")
        self.assertEqual(by_value["vpn.example.com"].slot_hint, "digital-footprint")
        self.assertEqual(by_value["vpn.example.com"].review_status, "candidate")
        self.assertEqual(by_value["203.0.113.10"].core_axis, "organization_asset")
        self.assertEqual(by_value["203.0.113.10"].slot_hint, "digital-footprint")

    def test_spiderfoot_email_same_domain_becomes_bridge_company_contact_candidate(self):
        parsed = ParsedToolOutput(
            tool="spiderfoot",
            target_type="domain",
            target_value="example.com",
            entities=[
                NormalizedEntity("domain", "example.com", "spiderfoot", 0.3),
                NormalizedEntity("email", "sales@example.com", "spiderfoot", 0.3),
                NormalizedEntity("company", "Example Trading LLC", "spiderfoot", 0.3),
                NormalizedEntity("username", "buyer-admin", "spiderfoot", 0.3),
            ],
            evidence=[
                NormalizedEvidence("sales@example.com", "spiderfoot_event", "spiderfoot", "SpiderFoot returned EMAILADDR"),
                NormalizedEvidence("Example Trading LLC", "spiderfoot_event", "spiderfoot", "SpiderFoot returned COMPANY_NAME"),
                NormalizedEvidence("buyer-admin", "spiderfoot_event", "spiderfoot", "SpiderFoot returned USERNAME"),
            ],
            relationships=[
                NormalizedRelationship("example.com", "sales@example.com", "target_has_finding", 0.3),
                NormalizedRelationship("example.com", "Example Trading LLC", "target_has_finding", 0.3),
                NormalizedRelationship("example.com", "buyer-admin", "target_has_finding", 0.3),
            ],
        )

        signals = derive_osint_signals(parsed)
        by_value = {signal.entity_value: signal for signal in signals}

        self.assertEqual(by_value["sales@example.com"].core_axis, "bridge")
        self.assertEqual(by_value["sales@example.com"].slot_hint, "company_contact")
        self.assertEqual(by_value["Example Trading LLC"].core_axis, "organization_asset")
        self.assertEqual(by_value["Example Trading LLC"].slot_hint, "landed-entity")
        self.assertEqual(by_value["buyer-admin"].core_axis, "decision_will")
        self.assertEqual(by_value["buyer-admin"].review_status, "candidate")

    def test_sherlock_profile_remains_decision_candidate(self):
        parsed = ParsedToolOutput(
            tool="sherlock",
            target_type="username",
            target_value="admin",
            entities=[
                NormalizedEntity("username", "admin", "sherlock", 0.35),
                NormalizedEntity("profile_url", "https://github.com/admin", "sherlock", 0.35),
            ],
            evidence=[
                NormalizedEvidence("https://github.com/admin", "profile_exists", "sherlock", "Sherlock claimed profile on GitHub"),
            ],
            relationships=[
                NormalizedRelationship("admin", "https://github.com/admin", "username_has_profile", 0.35),
            ],
        )

        signals = derive_osint_signals(parsed)
        by_value = {signal.entity_value: signal for signal in signals}

        self.assertEqual(by_value["admin"].core_axis, "decision_will")
        self.assertEqual(by_value["admin"].slot_hint, "persona-role")
        self.assertEqual(by_value["https://github.com/admin"].core_axis, "decision_will")
        self.assertEqual(by_value["https://github.com/admin"].slot_hint, "persona-role")
        self.assertEqual(by_value["https://github.com/admin"].review_status, "candidate")


if __name__ == "__main__":
    unittest.main()
