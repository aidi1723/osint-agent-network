import json
import unittest
from pathlib import Path

from app.tools.httpx import HttpxAdapter
from app.tools.katana import KatanaAdapter
from app.tools.official_site_extractor import OfficialSiteExtractorAdapter
from app.tools.official_site_search import OfficialSiteSearchAdapter
from app.tools.subfinder import SubfinderAdapter


FIXTURES = Path(__file__).parent / "fixtures" / "tool_outputs"


def entity_pairs(parsed):
    return {(item.type, item.value) for item in parsed.entities}


def evidence_pairs(parsed):
    return {(item.entity_value, item.evidence_kind) for item in parsed.evidence}


def relationship_triples(parsed):
    return {
        (item.from_value, item.to_value, item.relationship_type)
        for item in parsed.relationships
    }


class ToolFixtureRegressionTests(unittest.TestCase):
    def test_official_site_search_fixture_keeps_official_candidate(self):
        parsed = OfficialSiteSearchAdapter(base_url="http://search.local/search").parse_artifact(
            FIXTURES / "official_site_search" / "example_company_results.json",
            target_value="Example Manufacturing LLC",
        )

        entities = entity_pairs(parsed)
        evidence = evidence_pairs(parsed)
        relationships = relationship_triples(parsed)

        self.assertIn(("company", "Example Manufacturing LLC"), entities)
        self.assertIn(("url", "https://www.example-target.test/about"), entities)
        self.assertNotIn(("url", "https://directory.example/listing/example-manufacturing"), entities)
        self.assertIn(("https://www.example-target.test/about", "official_site_search_result"), evidence)
        self.assertIn(
            (
                "Example Manufacturing LLC",
                "https://www.example-target.test/about",
                "company_has_official_site_candidate",
            ),
            relationships,
        )

    def test_httpx_fixture_keeps_live_url_metadata(self):
        parsed = HttpxAdapter().parse_artifact(
            FIXTURES / "httpx" / "example_company_live.jsonl",
            target_value="www.example.com",
        )

        entities = entity_pairs(parsed)
        evidence = evidence_pairs(parsed)
        relationships = relationship_triples(parsed)

        self.assertIn(("domain", "www.example.com"), entities)
        self.assertIn(("url", "https://www.example.com"), entities)
        self.assertIn(("website_title", "Example Manufacturing - Contact"), entities)
        self.assertIn(("technology", "nginx"), entities)
        self.assertIn(("https://www.example.com", "http_probe"), evidence)
        self.assertIn(("www.example.com", "https://www.example.com", "host_serves_url"), relationships)

    def test_katana_fixture_keeps_relevant_pages(self):
        parsed = KatanaAdapter().parse_artifact(
            FIXTURES / "katana" / "example_company_pages.jsonl",
            target_value="https://www.example.com",
        )

        entities = entity_pairs(parsed)
        evidence = evidence_pairs(parsed)
        relationships = relationship_triples(parsed)

        self.assertIn(("url", "https://www.example.com/contact"), entities)
        self.assertIn(("contact_page", "https://www.example.com/contact"), entities)
        self.assertIn(("url", "https://www.example.com/products/upvc-windows"), entities)
        self.assertIn(("business_scope_page", "https://www.example.com/products/upvc-windows"), entities)
        self.assertNotIn(("url", "https://www.example.com/assets/site.css"), entities)
        self.assertNotIn(("url", "https://www.example.com/privacy"), entities)
        self.assertIn(("https://www.example.com/contact", "katana_business_page"), evidence)
        self.assertIn(
            ("https://www.example.com", "https://www.example.com/contact", "site_has_relevant_page"),
            relationships,
        )

    def test_official_site_extractor_fixture_keeps_identity_contacts_and_scope(self):
        parsed = OfficialSiteExtractorAdapter().parse_artifact(
            FIXTURES / "official_site_extractor" / "example_company_official.html",
            target_value="https://www.example.com/about",
        )

        entities = entity_pairs(parsed)
        evidence = evidence_pairs(parsed)
        relationships = relationship_triples(parsed)

        self.assertIn(("organization", "Example Manufacturing LLC"), entities)
        self.assertIn(("email", "sales@example.com"), entities)
        self.assertIn(("phone", "+12125550123"), entities)
        self.assertIn(("business_scope", "uPVC windows"), entities)
        self.assertIn(("business_scope", "aluminum curtain wall systems"), entities)
        self.assertIn(("address", "88 Industrial Road, Newark, NJ"), entities)
        self.assertIn(("sales@example.com", "official_site_contact"), evidence)
        self.assertIn(("uPVC windows", "official_site_business_scope"), evidence)
        self.assertIn(
            ("https://www.example.com/about", "sales@example.com", "official_site_has_contact_email"),
            relationships,
        )

    def test_subfinder_fixture_keeps_passive_subdomains(self):
        parsed = SubfinderAdapter().parse_artifact(
            FIXTURES / "subfinder" / "example_company_subdomains.jsonl",
            target_value="example.com",
        )

        entities = entity_pairs(parsed)
        evidence = evidence_pairs(parsed)
        relationships = relationship_triples(parsed)

        self.assertIn(("domain", "example.com"), entities)
        self.assertIn(("subdomain", "www.example.com"), entities)
        self.assertIn(("subdomain", "support.example.com"), entities)
        self.assertIn(("www.example.com", "subfinder_passive_discovery"), evidence)
        self.assertIn(("example.com", "support.example.com", "domain_has_subdomain"), relationships)

    def test_role_agent_output_fixture_documents_public_safe_contract(self):
        payload = json.loads(
            (FIXTURES / "role_agent_outputs" / "example_sparse_lead_summary.json").read_text(encoding="utf-8")
        )

        self.assertEqual(payload["fixture_version"], 1)
        self.assertEqual(payload["target_type"], "sparse_lead")
        self.assertEqual(payload["target_value"], "Example Manufacturing LLC")
        self.assertEqual(payload["role"], "company_enrichment")
        self.assertEqual(payload["privacy"], "public_safe_synthetic")
        self.assertIn("official_site_candidates", payload)
        self.assertIn("collection_gaps", payload)
        self.assertEqual(payload["official_site_candidates"][0]["url"], "https://www.example-target.test/about")

    def test_official_site_fixture_chain_supports_source_backed_fact_inputs(self):
        search_output = OfficialSiteSearchAdapter(base_url="http://search.local/search").parse_artifact(
            FIXTURES / "official_site_search" / "example_company_results.json",
            target_value="Example Manufacturing LLC",
        )
        extractor_output = OfficialSiteExtractorAdapter().parse_artifact(
            FIXTURES / "official_site_extractor" / "example_company_official.html",
            target_value="https://www.example-target.test/about",
        )

        search_relationships = relationship_triples(search_output)
        extractor_evidence = evidence_pairs(extractor_output)
        extractor_relationships = relationship_triples(extractor_output)

        self.assertIn(
            (
                "Example Manufacturing LLC",
                "https://www.example-target.test/about",
                "company_has_official_site_candidate",
            ),
            search_relationships,
        )
        self.assertIn(("sales@example.com", "official_site_contact"), extractor_evidence)
        self.assertIn(
            (
                "https://www.example-target.test/about",
                "sales@example.com",
                "official_site_has_contact_email",
            ),
            extractor_relationships,
        )
