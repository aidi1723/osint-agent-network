import json
import gzip
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.safe_http import (
    FakeIpAllowance,
    InvalidFakeIpConfiguration,
    SafeHttpError,
    SafeHttpResponse,
)

from app.tools.sherlock import SherlockAdapter
from app.tools.theharvester import TheHarvesterAdapter
from app.tools.amass import AmassAdapter
from app.tools.ghunt import GHuntAdapter
from app.tools.maigret import MaigretAdapter
from app.tools.phoneinfoga import PhoneInfogaAdapter
from app.tools.profile_parser import ProfileParserAdapter
from app.tools.official_site_extractor import MAX_HTML_BYTES, OfficialSiteExtractorAdapter
from app.tools.official_site_search import OfficialSiteSearchAdapter
from app.tools.spiderfoot import SpiderFootAdapter
from app.tools.socialscan import SocialScanAdapter
from app.tools.reconng import ReconNgAdapter
from app.tools.company_news import CompanyNewsAdapter
from app.tools.subfinder import SubfinderAdapter
from app.tools.httpx import HttpxAdapter
from app.tools.katana import KatanaAdapter


class SherlockAdapterTests(unittest.TestCase):
    def test_parser_keeps_only_claimed_profiles(self):
        adapter = SherlockAdapter()
        raw = {
            "GitHub": {
                "status": "CLAIMED",
                "url_main": "https://github.com/admin",
            },
            "Twitter": {
                "status": "AVAILABLE",
                "url_main": "https://twitter.com/admin",
            },
        }

        parsed = adapter.parse_json(raw, username="admin")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("username", "admin"), entity_values)
        self.assertIn(("profile_url", "https://github.com/admin"), entity_values)
        self.assertNotIn(("profile_url", "https://twitter.com/admin"), entity_values)
        self.assertIn(("https://github.com/admin", "profile_exists"), evidence)
        self.assertIn(
            ("admin", "https://github.com/admin", "username_has_profile"),
            relationships,
        )

    def test_build_command_uses_argument_array_and_job_workdir(self):
        adapter = SherlockAdapter(command="python3", module="sherlock_project")
        with tempfile.TemporaryDirectory() as tmpdir:
            command = adapter.build_command(
                target_type="username",
                target_value="admin",
                workdir=Path(tmpdir),
                timeout_seconds=5,
            )

        self.assertEqual(command.args[:3], ["python3", "-m", "sherlock_project"])
        self.assertIn("admin", command.args)
        self.assertEqual(command.timeout_seconds, 5)
        self.assertTrue(command.expected_artifact.name.endswith(".json"))


class TheHarvesterAdapterTests(unittest.TestCase):
    def test_parser_emits_entities_evidence_and_relationships(self):
        adapter = TheHarvesterAdapter()
        raw = {
            "emails": ["admin@example.com", "sales@example.com"],
            "hosts": ["vpn.example.com", "example.com"],
            "urls": ["https://example.com/contact"],
        }

        parsed = adapter.parse_json(raw, domain="example.com")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("domain", "example.com"), entity_values)
        self.assertIn(("email", "admin@example.com"), entity_values)
        self.assertIn(("username", "admin"), entity_values)
        self.assertIn(("subdomain", "vpn.example.com"), entity_values)
        self.assertIn(("url", "https://example.com/contact"), entity_values)
        self.assertIn(("admin@example.com", "search_result"), evidence)
        self.assertIn(("vpn.example.com", "host_discovery"), evidence)
        self.assertIn(
            ("example.com", "admin@example.com", "domain_exposes_email"),
            relationships,
        )
        self.assertIn(
            ("example.com", "vpn.example.com", "domain_has_subdomain"),
            relationships,
        )
        self.assertIn(
            ("admin@example.com", "admin", "email_has_username"),
            relationships,
        )

    def test_parse_artifact_reads_harvester_json_file(self):
        adapter = TheHarvesterAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = Path(tmpdir) / "report.json"
            artifact.write_text(
                json.dumps({"emails": ["admin@example.com"], "hosts": []}),
                encoding="utf-8",
            )

            parsed = adapter.parse_artifact(artifact, target_value="example.com")

        self.assertIn(
            ("email", "admin@example.com"),
            {(item.type, item.value) for item in parsed.entities},
        )


class AmassAdapterTests(unittest.TestCase):
    def test_parser_reads_jsonl_and_links_subdomains_to_ips(self):
        adapter = AmassAdapter()
        lines = [
            {
                "name": "vpn.example.com",
                "domain": "example.com",
                "addresses": [{"ip": "203.0.113.10"}],
                "sources": ["crtsh"],
            },
            {
                "name": "mail.example.com",
                "addresses": [],
                "tag": "dns",
            },
        ]

        parsed = adapter.parse_jsonl(lines, domain="example.com")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("domain", "example.com"), entity_values)
        self.assertIn(("subdomain", "vpn.example.com"), entity_values)
        self.assertIn(("subdomain", "mail.example.com"), entity_values)
        self.assertIn(("ip", "203.0.113.10"), entity_values)
        self.assertIn(("vpn.example.com", "amass_name_discovery"), evidence)
        self.assertIn(
            ("example.com", "vpn.example.com", "domain_has_subdomain"),
            relationships,
        )
        self.assertIn(
            ("vpn.example.com", "203.0.113.10", "subdomain_resolves_to_ip"),
            relationships,
        )

    def test_parse_artifact_skips_blank_and_invalid_jsonl_lines(self):
        adapter = AmassAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = Path(tmpdir) / "amass.jsonl"
            artifact.write_text(
                "\n"
                '{"name":"vpn.example.com","addresses":[{"ip":"203.0.113.10"}]}\n'
                "{bad json}\n",
                encoding="utf-8",
            )

            parsed = adapter.parse_artifact(artifact, target_value="example.com")

        self.assertIn(
            ("subdomain", "vpn.example.com"),
            {(item.type, item.value) for item in parsed.entities},
        )


class SubfinderAdapterTests(unittest.TestCase):
    def test_parser_reads_jsonl_subdomains(self):
        adapter = SubfinderAdapter()
        records = [
            {"host": "www.example.com", "source": "crtsh"},
            {"host": "mail.example.com", "sources": ["alienvault", "certspotter"]},
        ]

        parsed = adapter.parse_jsonl(records, domain="example.com")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("domain", "example.com"), entity_values)
        self.assertIn(("subdomain", "www.example.com"), entity_values)
        self.assertIn(("subdomain", "mail.example.com"), entity_values)
        self.assertIn(("www.example.com", "subfinder_passive_discovery"), evidence)
        self.assertIn(
            ("example.com", "www.example.com", "domain_has_subdomain"),
            relationships,
        )

    def test_parser_caps_large_passive_subdomain_results(self):
        adapter = SubfinderAdapter(result_limit=2)
        records = [{"host": f"host-{index}.example.com", "source": "crtsh"} for index in range(5)]

        parsed = adapter.parse_jsonl(records, domain="example.com")

        subdomains = [item for item in parsed.entities if item.type == "subdomain"]
        self.assertEqual(len(subdomains), 2)
        self.assertEqual(len(parsed.evidence), 2)
        self.assertEqual(len(parsed.relationships), 2)

    def test_build_command_outputs_jsonl_artifact(self):
        adapter = SubfinderAdapter(command="subfinder")
        with tempfile.TemporaryDirectory() as tmpdir:
            command = adapter.build_command("domain", "example.com", Path(tmpdir), timeout_seconds=10)

        self.assertEqual(command.args[:4], ["subfinder", "-d", "example.com", "-json"])
        self.assertIn("-o", command.args)
        self.assertIn("-max-time", command.args)
        self.assertIn("1", command.args)
        self.assertIn("-timeout", command.args)
        self.assertEqual(command.timeout_seconds, 10)
        self.assertTrue(command.expected_artifact.name.endswith(".jsonl"))
        self.assertEqual(command.args[command.args.index("-o") + 1], command.expected_artifact.name)

    def test_parse_artifact_handles_missing_output_as_empty_result(self):
        adapter = SubfinderAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            parsed = adapter.parse_artifact(Path(tmpdir) / "missing.jsonl", target_value="example.com")

        self.assertEqual(parsed.tool, "subfinder")
        self.assertIn(("domain", "example.com"), {(item.type, item.value) for item in parsed.entities})


class HttpxAdapterTests(unittest.TestCase):
    def test_parser_reads_jsonl_live_urls_and_metadata(self):
        adapter = HttpxAdapter()
        records = [
            {
                "url": "https://www.example.com",
                "input": "www.example.com",
                "title": "Example Manufacturing",
                "tech": ["nginx", "WordPress"],
                "status_code": 200,
            }
        ]

        parsed = adapter.parse_jsonl(records, target_type="subdomain", target_value="www.example.com")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("subdomain", "www.example.com"), entity_values)
        self.assertIn(("url", "https://www.example.com"), entity_values)
        self.assertIn(("website_title", "Example Manufacturing"), entity_values)
        self.assertIn(("technology", "nginx"), entity_values)
        self.assertIn(("https://www.example.com", "http_probe"), evidence)
        self.assertIn(
            ("www.example.com", "https://www.example.com", "host_serves_url"),
            relationships,
        )

    def test_build_command_accepts_domain_target(self):
        adapter = HttpxAdapter(command="httpx")
        with tempfile.TemporaryDirectory() as tmpdir:
            command = adapter.build_command("domain", "example.com", Path(tmpdir), timeout_seconds=15)

        self.assertEqual(command.args[:2], ["httpx", "-json"])
        self.assertIn("-u", command.args)
        self.assertIn("https://example.com", command.args)
        self.assertIn("-timeout", command.args)
        self.assertIn("-retries", command.args)
        self.assertIn("0", command.args)
        self.assertIn("-rl", command.args)
        self.assertEqual(command.timeout_seconds, 15)
        self.assertEqual(command.args[command.args.index("-o") + 1], command.expected_artifact.name)

    def test_parse_artifact_handles_missing_output_as_empty_result(self):
        adapter = HttpxAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            parsed = adapter.parse_artifact(Path(tmpdir) / "missing.jsonl", target_value="example.com")

        self.assertEqual(parsed.tool, "httpx")
        self.assertIn(("domain", "example.com"), {(item.type, item.value) for item in parsed.entities})


class OfficialSiteSearchAdapterTests(unittest.TestCase):
    def test_parser_extracts_likely_official_urls_from_searxng_results(self):
        adapter = OfficialSiteSearchAdapter(base_url="http://search.local/search")
        raw = {
            "results": [
                {
                    "title": "Sample Auto Parts Co. - Official Website",
                    "url": "https://www.example-target.test/about?utm_source=x",
                    "content": "Manufacturer of auto parts and brake components.",
                },
                {
                    "title": "Directory Listing",
                    "url": "https://directory.example/listing/sample-auto-parts",
                    "content": "third-party listing",
                },
            ]
        }

        parsed = adapter.parse_json(raw, target_type="company", target_value="Sample Auto Parts Co.")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("company", "Sample Auto Parts Co."), entity_values)
        self.assertIn(("url", "https://www.example-target.test/about"), entity_values)
        self.assertNotIn(("url", "https://directory.example/listing/sample-auto-parts"), entity_values)
        self.assertIn(
            ("Sample Auto Parts Co.", "https://www.example-target.test/about", "company_has_official_site_candidate"),
            relationships,
        )

    def test_parser_filters_third_party_search_noise(self):
        adapter = OfficialSiteSearchAdapter(base_url="http://search.local/search")
        raw = {
            "results": [
                {
                    "title": "Example Domain",
                    "url": "https://example.com/",
                    "content": "This domain is for use in documentation examples.",
                },
                {
                    "title": "Professional email address when your own domain is taken",
                    "url": "https://www.reddit.com/r/productivity/comments/znibk5/professional_email_address_when_your_own_domain/",
                    "content": "Discussion mentioning Example Domain contact options.",
                },
                {
                    "title": "Example Domain setup notes",
                    "url": "https://laurens.io/blog/example-domain/",
                    "content": "A blog article about the Example Domain website.",
                },
                {
                    "title": "Register a domain name",
                    "url": "https://domain.by/en/domain-register/",
                    "content": "Domain registrar page unrelated to Example Domain.",
                },
                {
                    "title": "Directory Listing",
                    "url": "https://business-directory.example/example-domain",
                    "content": "Third-party listing for Example Domain.",
                },
            ]
        }

        parsed = adapter.parse_json(raw, target_type="company", target_value="Example Domain")

        url_entities = [item for item in parsed.entities if item.type == "url"]
        self.assertEqual({item.value for item in url_entities}, {"https://example.com/"})
        self.assertGreaterEqual(url_entities[0].confidence, 0.58)

    def test_parser_filters_third_party_foundation_database_results(self):
        adapter = OfficialSiteSearchAdapter(base_url="http://search.local/search")
        raw = {
            "results": [
                {
                    "title": "Grantmaker Profile",
                    "url": "https://fconline.foundationcenter.org/fdo-grantmaker-profile/",
                    "content": "Profile and contact information for Python Software Foundation.",
                },
                {
                    "title": "Python Software Foundation",
                    "url": "https://www.python.org/psf/about/",
                    "content": "About the Python Software Foundation.",
                },
            ]
        }

        parsed = adapter.parse_json(raw, target_type="company", target_value="Python Software Foundation")

        urls = {item.value for item in parsed.entities if item.type == "url"}
        self.assertEqual(urls, {"https://www.python.org/psf/about/"})

    def test_build_command_uses_internal_module_with_query_params(self):
        adapter = OfficialSiteSearchAdapter(base_url="http://search.local/search", command="python3")
        with tempfile.TemporaryDirectory() as tmpdir:
            command = adapter.build_command("company", "Sample Auto Parts Co.", Path(tmpdir), timeout_seconds=20)

        self.assertEqual(command.args[:3], ["python3", "-m", "app.tools.official_site_search"])
        self.assertIn("--query", command.args)
        self.assertIn('"Sample Auto Parts Co." official website contact', command.args)
        self.assertIn("--base-url", command.args)
        self.assertIn("http://search.local/search", command.args)
        self.assertEqual(command.timeout_seconds, 20)
        self.assertTrue(command.expected_artifact.name.endswith(".json"))


class KatanaAdapterTests(unittest.TestCase):
    def test_parser_keeps_relevant_business_pages(self):
        adapter = KatanaAdapter()
        records = [
            {"url": "https://example.com/contact", "source": "href"},
            {"url": "https://example.com/products/upvc-window", "source": "href"},
            {"url": "https://cdn.example.com/assets/module_productDetail.css", "source": "href"},
            {"url": "https://example.com/privacy", "source": "href"},
        ]

        parsed = adapter.parse_jsonl(records, url="https://example.com")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("url", "https://example.com/contact"), entity_values)
        self.assertIn(("url", "https://example.com/products/upvc-window"), entity_values)
        self.assertNotIn(("url", "https://cdn.example.com/assets/module_productDetail.css"), entity_values)
        self.assertIn(("contact_page", "https://example.com/contact"), entity_values)
        self.assertIn(("business_scope_page", "https://example.com/products/upvc-window"), entity_values)
        self.assertNotIn(("url", "https://example.com/privacy"), entity_values)
        self.assertIn(("https://example.com/contact", "katana_business_page"), evidence)
        self.assertIn(
            ("https://example.com", "https://example.com/contact", "site_has_relevant_page"),
            relationships,
        )

    def test_parser_ignores_malformed_output_lines(self):
        adapter = KatanaAdapter()
        records = [
            {"url": "http://[bad-ipv6"},
            {"url": "https://example.com/contact"},
        ]

        parsed = adapter.parse_jsonl(records, url="https://example.com")

        self.assertIn(("url", "https://example.com/contact"), {(item.type, item.value) for item in parsed.entities})

    def test_build_command_crawls_url_with_jsonl_output(self):
        adapter = KatanaAdapter(command="katana")
        with tempfile.TemporaryDirectory() as tmpdir:
            command = adapter.build_command("url", "https://example.com", Path(tmpdir), timeout_seconds=20)

        self.assertEqual(command.args[:2], ["katana", "-u"])
        self.assertIn("https://example.com", command.args)
        self.assertIn("-jsonl", command.args)
        self.assertIn("-ct", command.args)
        self.assertIn("30s", command.args)
        self.assertIn("-timeout", command.args)
        self.assertIn("-retry", command.args)
        self.assertEqual(command.timeout_seconds, 20)
        self.assertEqual(command.args[command.args.index("-o") + 1], command.expected_artifact.name)

    def test_parse_artifact_handles_missing_output_as_empty_result(self):
        adapter = KatanaAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            parsed = adapter.parse_artifact(Path(tmpdir) / "missing.jsonl", target_value="https://example.com")

        self.assertEqual(parsed.tool, "katana")
        self.assertIn(("url", "https://example.com"), {(item.type, item.value) for item in parsed.entities})


class OfficialSiteExtractorAdapterTests(unittest.TestCase):
    def test_parser_extracts_visible_text_decision_maker_candidate(self):
        adapter = OfficialSiteExtractorAdapter()
        html = """
        <html>
          <body>
            <section>
              <h2>Leadership</h2>
              <p>Jane Smith, Export Manager</p>
              <p>Email: jane.smith@example.com</p>
            </section>
          </body>
        </html>
        """

        parsed = adapter.parse_html(html, url="https://example.com/team")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("person", "Jane Smith"), entity_values)
        self.assertIn(("job_title", "Export Manager"), entity_values)
        self.assertIn(("decision_maker", "Jane Smith - Export Manager"), entity_values)
        self.assertIn(("Jane Smith", "official_site_decision_maker_candidate"), evidence)
        self.assertIn(
            ("https://example.com/team", "Jane Smith", "official_site_mentions_decision_maker"),
            relationships,
        )
        self.assertIn(("Jane Smith", "Export Manager", "person_has_public_role"), relationships)
        self.assertIn(("Jane Smith", "jane.smith@example.com", "person_has_contact"), relationships)

    def test_parser_extracts_json_ld_person_decision_maker_candidate(self):
        adapter = OfficialSiteExtractorAdapter()
        html = """
        <html>
          <head>
            <script type="application/ld+json">
              {"@type":"Person","name":"Michael Chen","jobTitle":"Managing Director","email":"michael.chen@example.com"}
            </script>
          </head>
          <body><p>Company leadership page.</p></body>
        </html>
        """

        parsed = adapter.parse_html(html, url="https://example.com/about")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("person", "Michael Chen"), entity_values)
        self.assertIn(("job_title", "Managing Director"), entity_values)
        self.assertIn(("decision_maker", "Michael Chen - Managing Director"), entity_values)
        self.assertIn(("Michael Chen", "michael.chen@example.com", "person_has_contact"), relationships)

    def test_parser_rejects_generic_decision_labels_and_distant_contacts(self):
        adapter = OfficialSiteExtractorAdapter()
        html = """
        <html>
          <body>
            <h1>Contact Us</h1>
            <p>Sales Team - Customer Service</p>
            <p>Generic inbox: info@example.com</p>
            <section>
              <p>Alice Brown, Sales Manager</p>
            </section>
          </body>
        </html>
        """

        parsed = adapter.parse_html(html, url="https://example.com/contact")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertNotIn(("person", "Contact Us"), entity_values)
        self.assertNotIn(("person", "Sales Team"), entity_values)
        self.assertIn(("person", "Alice Brown"), entity_values)
        self.assertNotIn(("Alice Brown", "info@example.com", "person_has_contact"), relationships)

    def test_parser_extracts_contact_and_business_fields_from_html(self):
        adapter = OfficialSiteExtractorAdapter()
        html = """
        <html>
          <head>
            <title>Example Manufacturing - uPVC Windows and Curtain Wall</title>
            <script type="application/ld+json">
              {"@type":"Organization","name":"Example Manufacturing LLC","url":"https://example.com","email":"sales@example.com","telephone":"+1 212 555 0123"}
            </script>
          </head>
          <body>
            <h1>Example Manufacturing LLC</h1>
            <p>We manufacture uPVC windows, aluminum curtain wall systems, and sliding doors for commercial projects.</p>
            <p>Contact sales@example.com or call +1 212 555 0123.</p>
            <p>Address: 88 Industrial Road, Newark, NJ.</p>
          </body>
        </html>
        """

        parsed = adapter.parse_html(html, url="https://example.com/about")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("url", "https://example.com/about"), entity_values)
        self.assertIn(("organization", "Example Manufacturing LLC"), entity_values)
        self.assertIn(("email", "sales@example.com"), entity_values)
        self.assertIn(("phone", "+12125550123"), entity_values)
        self.assertIn(("business_scope", "uPVC windows"), entity_values)
        self.assertIn(("business_scope", "aluminum curtain wall systems"), entity_values)
        self.assertIn(("address", "88 Industrial Road, Newark, NJ"), entity_values)
        self.assertIn(("sales@example.com", "official_site_contact"), evidence)
        self.assertIn(("uPVC windows", "official_site_business_scope"), evidence)
        self.assertIn(
            ("https://example.com/about", "sales@example.com", "official_site_has_contact_email"),
            relationships,
        )

    def test_build_command_is_artifact_parser(self):
        adapter = OfficialSiteExtractorAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            command = adapter.build_command("url", "https://example.com/contact", Path(tmpdir), timeout_seconds=5)

        self.assertEqual(command.args, ["PARSE_ARTIFACT", "https://example.com/contact"])
        self.assertEqual(command.expected_artifact.name, "official_site_input.html")
        self.assertEqual(command.timeout_seconds, 5)

    def test_run_fetches_html_to_expected_artifact(self):
        html = b"""
        <html><body>
          <h1>Example Manufacturing LLC</h1>
          <p>Contact sales@example.com for uPVC windows.</p>
        </body></html>
        """

        url = "https://example.com/contact"
        adapter = OfficialSiteExtractorAdapter()
        fetched = SafeHttpResponse(200, {"Content-Encoding": "gzip"}, gzip.compress(html), url)
        with patch("app.tools.official_site_extractor.safe_fetch", return_value=fetched):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = adapter.run("url", url, Path(tmpdir), timeout_seconds=5)
                artifact_exists = result.command.expected_artifact.exists()
                parsed = adapter.parse_artifact(result.command.expected_artifact, target_value=url)

        self.assertEqual(result.returncode, 0)
        self.assertTrue(artifact_exists)
        self.assertIn(("email", "sales@example.com"), {(item.type, item.value) for item in parsed.entities})

    def test_run_passes_configured_fake_ip_allowance_to_safe_fetch(self):
        allowance = FakeIpAllowance()
        fetched = SafeHttpResponse(200, {}, b"<html></html>", "https://example.com/")
        with patch(
            "app.tools.official_site_extractor.fake_ip_allowance_from_env",
            return_value=allowance,
        ), patch(
            "app.tools.official_site_extractor.safe_fetch",
            return_value=fetched,
        ) as safe_fetch_mock:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = OfficialSiteExtractorAdapter().run(
                    "url",
                    "https://example.com/",
                    Path(tmpdir),
                    timeout_seconds=5,
                )

        self.assertEqual(result.returncode, 0)
        safe_fetch_mock.assert_called_once_with(
            "https://example.com/",
            timeout_seconds=5,
            max_bytes=MAX_HTML_BYTES,
            headers={
                "User-Agent": "osint-agent-network/1.0 (+official-site-extractor)",
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            },
            fake_ip_allowance=allowance,
        )

    def test_run_fails_closed_on_invalid_fake_ip_configuration(self):
        with patch(
            "app.tools.official_site_extractor.fake_ip_allowance_from_env",
            side_effect=InvalidFakeIpConfiguration("sensitive configuration details"),
        ), patch("app.tools.official_site_extractor.safe_fetch") as safe_fetch_mock:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = OfficialSiteExtractorAdapter().run(
                    "url",
                    "https://example.com/private-token",
                    Path(tmpdir),
                    timeout_seconds=5,
                )
                artifact = result.command.expected_artifact.read_bytes()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr_excerpt, "official site fetch failed")
        self.assertEqual(artifact, b"")
        self.assertNotIn("sensitive", repr(result))
        self.assertNotIn("private-token", repr(result))
        safe_fetch_mock.assert_not_called()

    def test_run_bounds_high_ratio_gzip_expansion(self):
        expanded = b"A" * (32 * 1024 * 1024)
        fetched = SafeHttpResponse(
            200,
            {"Content-Encoding": "gzip"},
            gzip.compress(expanded),
            "https://example.com/",
        )

        with patch("app.tools.official_site_extractor.safe_fetch", return_value=fetched), patch(
            "app.tools.official_site_extractor.gzip.decompress",
            side_effect=AssertionError("unbounded gzip decode used"),
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = OfficialSiteExtractorAdapter().run("url", "https://example.com/", Path(tmpdir), 5)
                artifact = result.command.expected_artifact.read_bytes()

        self.assertLess(len(fetched.body), 64 * 1024)
        self.assertEqual(len(artifact), MAX_HTML_BYTES)
        self.assertEqual(artifact, b"A" * MAX_HTML_BYTES)
        self.assertIn("truncated=True", result.stdout_excerpt)

    def test_run_bounds_concatenated_gzip_members(self):
        compressed = gzip.compress(b"A" * MAX_HTML_BYTES) + gzip.compress(b"B" * MAX_HTML_BYTES)
        fetched = SafeHttpResponse(200, {"Content-Encoding": "gzip"}, compressed, "https://example.com/")

        with patch("app.tools.official_site_extractor.safe_fetch", return_value=fetched):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = OfficialSiteExtractorAdapter().run("url", "https://example.com/", Path(tmpdir), 5)
                artifact = result.command.expected_artifact.read_bytes()

        self.assertEqual(len(artifact), MAX_HTML_BYTES)
        self.assertEqual(artifact, b"A" * MAX_HTML_BYTES)
        self.assertIn("truncated=True", result.stdout_excerpt)

    def test_run_preserves_invalid_gzip_fallback_within_cap(self):
        invalid = b"\x1f\x8bnot-a-valid-stream"
        fetched = SafeHttpResponse(200, {"Content-Encoding": "gzip"}, invalid, "https://example.com/")

        with patch("app.tools.official_site_extractor.safe_fetch", return_value=fetched):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = OfficialSiteExtractorAdapter().run("url", "https://example.com/", Path(tmpdir), 5)
                artifact = result.command.expected_artifact.read_bytes()

        self.assertEqual(artifact, invalid)
        self.assertIn("truncated=False", result.stdout_excerpt)

    def test_run_returns_sanitized_failure_for_private_credentialed_url(self):
        target = "https://user:" + "supersecret@127.0.0.1/private-token"

        with tempfile.TemporaryDirectory() as tmpdir:
            result = OfficialSiteExtractorAdapter().run("url", target, Path(tmpdir), 5)
            artifact = result.command.expected_artifact.read_bytes()

        rendered = repr(result)
        for sensitive in ("user", "supersecret", "private-token"):
            self.assertNotIn(sensitive, rendered)
            self.assertNotIn(sensitive.encode(), artifact)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr_excerpt, "official site fetch failed")
        self.assertEqual(artifact, b"")

    def test_run_maps_safe_http_failure_without_leaking_url(self):
        adapter = OfficialSiteExtractorAdapter()
        target = "https://example.com/private-token"

        with patch("app.tools.official_site_extractor.safe_fetch", side_effect=SafeHttpError("sensitive details")):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = adapter.run("url", target, Path(tmpdir), timeout_seconds=5)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr_excerpt, "official site fetch failed")
        self.assertNotIn("private-token", result.stderr_excerpt)

    def test_run_maps_lazy_resolver_failure_without_leaking_details(self):
        def failing_fetch(url, timeout_seconds, max_bytes, headers, fake_ip_allowance):
            def lazy_answers():
                yield (2, 1, 6, "", ("8.8.8.8", 443))
                raise OSError("secret.internal resolver detail")

            from app.core.safe_http import safe_fetch

            return safe_fetch(
                url,
                timeout_seconds=timeout_seconds,
                max_bytes=max_bytes,
                headers=headers,
                fake_ip_allowance=fake_ip_allowance,
                resolver=lambda *args, **kwargs: lazy_answers(),
                connector=lambda *args: self.fail("connector must not run"),
            )

        adapter = OfficialSiteExtractorAdapter()
        with patch("app.tools.official_site_extractor.safe_fetch", side_effect=failing_fetch):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = adapter.run("url", "https://example.com/secret-path", Path(tmpdir), timeout_seconds=5)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr_excerpt, "official site fetch failed")
        self.assertNotIn("secret", result.stderr_excerpt)

    def test_parser_extracts_srr_style_identity_scope_and_filters_script_phone_noise(self):
        adapter = OfficialSiteExtractorAdapter()
        html = """
        <html>
          <head>
            <title>SAMPLE AUTO PARTS COMPANY LIMITED</title>
            <meta name="description" content="SampleCo auto parts, automotive spare parts and brake components supplier">
          </head>
          <body>
            <h1>SAMPLE AUTO PARTS COMPANY LIMITED</h1>
            <p>We supply auto parts, brake components, suspension parts and engine parts.</p>
            <p>Tel: +852 8206 1801</p>
            <p>Tel: 020-3880-6857</p>
            <p>Noise: +86 991 3966766 3966788</p>
          </body>
        </html>
        """

        parsed = adapter.parse_html(html, url="https://example-target.test")

        entity_values = {(item.type, item.value) for item in parsed.entities}

        self.assertIn(("organization", "SAMPLE AUTO PARTS COMPANY LIMITED"), entity_values)
        self.assertIn(("business_scope", "auto parts"), entity_values)
        self.assertIn(("business_scope", "brake components"), entity_values)
        self.assertIn(("phone", "+85282061801"), entity_values)
        self.assertIn(("phone", "02038806857"), entity_values)
        self.assertNotIn(("phone", "+8699139667663966788"), entity_values)


class GHuntAdapterTests(unittest.TestCase):
    def test_parser_extracts_google_identity_and_public_profiles(self):
        adapter = GHuntAdapter()
        raw = {
            "email": "target@gmail.com",
            "exists": True,
            "profile": {
                "name": "Alice Example",
                "profile_url": "https://profiles.google.com/alice",
            },
            "youtube": {
                "channel_url": "https://www.youtube.com/@alice",
            },
        }

        parsed = adapter.parse_json(raw, email="target@gmail.com")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("email", "target@gmail.com"), entity_values)
        self.assertIn(("real_name", "Alice Example"), entity_values)
        self.assertIn(("profile_url", "https://www.youtube.com/@alice"), entity_values)
        self.assertIn(("target@gmail.com", "google_account_exists"), evidence)
        self.assertIn(
            ("target@gmail.com", "Alice Example", "email_has_real_name"),
            relationships,
        )
        self.assertIn(
            ("target@gmail.com", "https://www.youtube.com/@alice", "email_has_profile"),
            relationships,
        )

    def test_parser_emits_negative_evidence_for_missing_account(self):
        adapter = GHuntAdapter()

        parsed = adapter.parse_json({"exists": False, "message": "not found"}, email="missing@gmail.com")

        self.assertIn(
            ("missing@gmail.com", "negative_result"),
            {(item.entity_value, item.evidence_kind) for item in parsed.evidence},
        )


class MaigretAdapterTests(unittest.TestCase):
    def test_parser_extracts_claimed_profiles_and_public_metadata(self):
        adapter = MaigretAdapter()
        raw = {
            "GitHub": {
                "status": "Claimed",
                "url_user": "https://github.com/admin",
                "ids_data": {
                    "fullname": "Admin Example",
                    "bio": "Open source builder in Singapore",
                    "location": "Singapore",
                    "avatar": "https://avatars.githubusercontent.com/u/1",
                    "website": "https://admin.example.com",
                },
            },
            "Reddit": {
                "status": "Available",
                "url_user": "https://www.reddit.com/user/admin",
            },
        }

        parsed = adapter.parse_json(raw, username="admin")

        entities = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("username", "admin"), entities)
        self.assertIn(("profile_url", "https://github.com/admin"), entities)
        self.assertIn(("social_profile", "github:admin"), entities)
        self.assertIn(("bio_snippet", "Open source builder in Singapore"), entities)
        self.assertIn(("declared_location", "Singapore"), entities)
        self.assertIn(("profile_image_url", "https://avatars.githubusercontent.com/u/1"), entities)
        self.assertIn(("external_link", "https://admin.example.com/"), entities)
        self.assertNotIn(("profile_url", "https://www.reddit.com/user/admin"), entities)
        self.assertIn(("https://github.com/admin", "social_profile_exists"), evidence)
        self.assertIn(("admin", "https://github.com/admin", "username_has_social_profile"), relationships)

    def test_build_command_uses_argument_array(self):
        adapter = MaigretAdapter(command="maigret")
        with tempfile.TemporaryDirectory() as tmpdir:
            command = adapter.build_command(
                target_type="username",
                target_value="admin",
                workdir=Path(tmpdir),
                timeout_seconds=5,
            )

        self.assertEqual(command.args[:2], ["maigret", "admin"])
        self.assertIn("--json", command.args)
        self.assertEqual(command.timeout_seconds, 5)


class PhoneInfogaAdapterTests(unittest.TestCase):
    def test_parser_extracts_phone_metadata_and_footprint_urls(self):
        adapter = PhoneInfogaAdapter()
        raw = {
            "number": "+639171234567",
            "valid": True,
            "country": "Philippines",
            "carrier": "Globe",
            "timezones": ["Asia/Manila"],
            "footprints": [
                {
                    "url": "https://example.com/users/jane",
                    "source": "google",
                }
            ],
        }

        parsed = adapter.parse_json(raw, phone="+63 917-123-4567")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("phone", "+639171234567"), entity_values)
        self.assertIn(("url", "https://example.com/users/jane"), entity_values)
        self.assertIn(("+639171234567", "phone_metadata"), evidence)
        self.assertIn(("https://example.com/users/jane", "phone_public_footprint"), evidence)
        self.assertIn(
            ("+639171234567", "https://example.com/users/jane", "phone_referenced_by_url"),
            relationships,
        )


class ProfileParserAdapterTests(unittest.TestCase):
    def test_parser_extracts_public_profile_metadata_from_html(self):
        adapter = ProfileParserAdapter()
        html = """
        <html>
          <head>
            <title>Admin Example</title>
            <meta property="og:description" content="Builder, runner, fintech operator in Singapore">
            <meta property="og:image" content="https://example.com/avatar.jpg">
          </head>
          <body>
            <a href="https://admin.example.com">Website</a>
            <span class="location">Singapore</span>
          </body>
        </html>
        """

        parsed = adapter.parse_html(html, profile_url="https://github.com/admin")

        entities = {(item.type, item.value) for item in parsed.entities}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("profile_url", "https://github.com/admin"), entities)
        self.assertIn(("bio_snippet", "Builder, runner, fintech operator in Singapore"), entities)
        self.assertIn(("profile_image_url", "https://example.com/avatar.jpg"), entities)
        self.assertIn(("external_link", "https://admin.example.com/"), entities)
        self.assertIn(("declared_location", "Singapore"), entities)
        self.assertIn(("interest_tag", "fintech"), entities)
        self.assertIn(("https://github.com/admin", "Singapore", "profile_declares_location"), relationships)


class SocialScanAdapterTests(unittest.TestCase):
    def test_parser_extracts_positive_and_negative_platform_results(self):
        adapter = SocialScanAdapter()
        raw = {
            "results": [
                {"platform": "github", "exists": True, "url": "https://github.com/admin"},
                {"platform": "twitter", "exists": False, "message": "not found"},
            ]
        }

        parsed = adapter.parse_json(raw, target_type="email", target_value="admin@example.com")

        entities = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("email", "admin@example.com"), entities)
        self.assertIn(("profile_url", "https://github.com/admin"), entities)
        self.assertIn(("platform_account", "github:admin@example.com"), entities)
        self.assertIn(("https://github.com/admin", "account_exists"), evidence)
        self.assertIn(("twitter:admin@example.com", "negative_result"), evidence)
        self.assertIn(("admin@example.com", "https://github.com/admin", "email_linked_to_social_profile"), relationships)


class SpiderFootAdapterTests(unittest.TestCase):
    def test_parser_maps_high_value_event_types(self):
        adapter = SpiderFootAdapter()
        raw = [
            {"type": "EMAILADDR", "data": "admin@example.com", "source": "sfp_email"},
            {"type": "INTERNET_NAME", "data": "vpn.example.com", "source": "sfp_dns"},
            {"type": "IP_ADDRESS", "data": "203.0.113.10", "source": "sfp_dns"},
            {"type": "URL", "data": "https://example.com/contact", "source": "sfp_spider"},
        ]

        parsed = adapter.parse_json(raw, target_type="domain", target_value="example.com")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("domain", "example.com"), entity_values)
        self.assertIn(("email", "admin@example.com"), entity_values)
        self.assertIn(("subdomain", "vpn.example.com"), entity_values)
        self.assertIn(("ip", "203.0.113.10"), entity_values)
        self.assertIn(("admin@example.com", "spiderfoot_event"), evidence)
        self.assertIn(
            ("example.com", "vpn.example.com", "target_has_finding"),
            relationships,
        )

    def test_parser_maps_core_osint_event_types_for_dual_core_fusion(self):
        adapter = SpiderFootAdapter()
        raw = {
            "results": [
                {"type": "EMAILADDR", "data": "sales@example.com", "source": "sfp_email"},
                {"type": "INTERNET_NAME", "data": "vpn.example.com", "source": "sfp_dns"},
                {"type": "IP_ADDRESS", "data": "203.0.113.10", "source": "sfp_dns"},
                {"type": "URL", "data": "https://example.com/contact", "source": "sfp_spider"},
                {"type": "USERNAME", "data": "buyer-admin", "source": "sfp_accounts"},
                {"type": "HUMAN_NAME", "data": "Alice Buyer", "source": "sfp_names"},
                {"type": "COMPANY_NAME", "data": "Example Trading LLC", "source": "sfp_company"},
            ]
        }

        parsed = adapter.parse_json(raw, target_type="domain", target_value="example.com")

        entities = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("email", "sales@example.com"), entities)
        self.assertIn(("subdomain", "vpn.example.com"), entities)
        self.assertIn(("ip", "203.0.113.10"), entities)
        self.assertIn(("url", "https://example.com/contact"), entities)
        self.assertIn(("username", "buyer-admin"), entities)
        self.assertIn(("real_name", "Alice Buyer"), entities)
        self.assertIn(("company", "Example Trading LLC"), entities)
        self.assertIn(("sales@example.com", "spiderfoot_event"), evidence)
        self.assertIn(("example.com", "buyer-admin", "target_has_finding"), relationships)


class ReconNgAdapterTests(unittest.TestCase):
    def test_parser_extracts_workspace_report_records(self):
        adapter = ReconNgAdapter()
        raw = {
            "hosts": [{"host": "vpn.example.com"}],
            "contacts": [
                {
                    "email": "admin@example.com",
                    "first_name": "Alice",
                    "last_name": "Example",
                }
            ],
            "companies": [{"company": "Example Inc"}],
        }

        parsed = adapter.parse_json(raw, target_type="domain", target_value="example.com")

        entity_values = {(item.type, item.value) for item in parsed.entities}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("domain", "example.com"), entity_values)
        self.assertIn(("subdomain", "vpn.example.com"), entity_values)
        self.assertIn(("email", "admin@example.com"), entity_values)
        self.assertIn(("real_name", "Alice Example"), entity_values)
        self.assertIn(("company", "Example Inc"), entity_values)
        self.assertIn(
            ("example.com", "admin@example.com", "reconng_finding"),
            relationships,
        )

    def test_build_command_writes_safe_resource_script(self):
        adapter = ReconNgAdapter(command="recon-ng")
        with tempfile.TemporaryDirectory() as tmpdir:
            command = adapter.build_command(
                target_type="domain",
                target_value="example.com",
                workdir=Path(tmpdir),
                timeout_seconds=90,
            )
            script = command.args[-1]

            script_text = Path(script).read_text(encoding="utf-8")

        self.assertEqual(command.args[:2], ["recon-ng", "-r"])
        self.assertIn("db insert domains example.com", script_text)
        self.assertIn("reporting/json", script_text)
        self.assertNotIn(";", script_text)


class CompanyNewsAdapterTests(unittest.TestCase):
    def test_parser_extracts_news_articles_and_business_signals(self):
        adapter = CompanyNewsAdapter()
        raw = {
            "articles": [
                {
                    "title": "Example Inc opens new hotel project with local supplier",
                    "url": "https://news.example.com/example-hotel-project",
                    "source": "Local Business Journal",
                    "published_at": "2026-05-01",
                    "snippet": "Example Inc announced a new hotel project and supplier partnership.",
                },
                {
                    "title": "Example Inc faces lawsuit over unpaid invoices",
                    "link": "https://news.example.com/example-lawsuit",
                    "source_media": "Court Watch",
                    "date": "2026-04-20",
                    "summary": "The company is named in a lawsuit over unpaid invoices.",
                },
            ]
        }

        parsed = adapter.parse_json(raw, company="Example Inc")

        entities = {(item.type, item.value) for item in parsed.entities}
        evidence = {(item.entity_value, item.evidence_kind) for item in parsed.evidence}
        relationships = {
            (item.from_value, item.to_value, item.relationship_type)
            for item in parsed.relationships
        }

        self.assertIn(("company", "Example Inc"), entities)
        self.assertIn(("news_article", "Example Inc opens new hotel project with local supplier"), entities)
        self.assertIn(("external_link", "https://news.example.com/example-hotel-project"), entities)
        self.assertIn(("published_at", "2026-05-01"), entities)
        self.assertIn(("news_summary", "Example Inc announced a new hotel project and supplier partnership."), entities)
        self.assertIn(("news_summary", "The company is named in a lawsuit over unpaid invoices."), entities)
        self.assertIn(("Example Inc opens new hotel project with local supplier", "company_news_report"), evidence)
        self.assertIn(("Example Inc announced a new hotel project and supplier partnership.", "news_buying_signal"), evidence)
        self.assertIn(("The company is named in a lawsuit over unpaid invoices.", "news_risk_signal"), evidence)
        self.assertIn(("Example Inc", "Example Inc opens new hotel project with local supplier", "company_has_news_article"), relationships)
        self.assertIn(("Example Inc", "Example Inc announced a new hotel project and supplier partnership.", "news_supports_buying_signal"), relationships)
        self.assertIn(("Example Inc", "The company is named in a lawsuit over unpaid invoices.", "news_supports_risk_signal"), relationships)

    def test_build_command_uses_configured_news_sources(self):
        adapter = CompanyNewsAdapter(command="python3", source="gnews")
        with tempfile.TemporaryDirectory() as tmpdir:
            command = adapter.build_command(
                target_type="company",
                target_value="Example Inc",
                workdir=Path(tmpdir),
                timeout_seconds=45,
            )

        self.assertEqual(command.args[:3], ["python3", "-m", "app.tools.company_news"])
        self.assertIn("--source", command.args)
        self.assertIn("gnews", command.args)
        self.assertEqual(command.timeout_seconds, 45)
        self.assertTrue(command.expected_artifact.name.endswith(".json"))

    def test_fetch_news_uses_discovery_and_article_parser_functions(self):
        discovered = [
            {
                "title": "Example Inc announces expansion",
                "url": "https://news.example.com/expansion",
                "source": "Google News",
                "published_at": "2026-05-01",
                "snippet": "Short snippet",
            }
        ]

        def fake_discover(company, source, limit, days):
            return discovered

        def fake_parse(url, timeout_seconds):
            return {
                "title": "Example Inc announces expansion",
                "url": url,
                "source": "Industry Daily",
                "published_at": "2026-05-02",
                "summary": "Example Inc announces an expansion project and supplier search.",
            }

        payload = CompanyNewsAdapter.fetch_news_payload(
            company="Example Inc",
            source="gnews",
            limit=3,
            days=30,
            timeout_seconds=10,
            discover_fn=fake_discover,
            parse_article_fn=fake_parse,
        )

        self.assertEqual(payload["source"], "gnews")
        self.assertEqual(payload["articles"][0]["source"], "Industry Daily")
        self.assertEqual(payload["articles"][0]["summary"], "Example Inc announces an expansion project and supplier search.")

    def test_fetch_news_treats_unavailable_discovery_as_empty_result(self):
        payload = CompanyNewsAdapter.fetch_news_payload(
            company="Example Inc",
            source="gnews",
            limit=3,
            days=30,
            timeout_seconds=10,
            discover_fn=lambda *args: (_ for _ in ()).throw(RuntimeError("rss parser unavailable")),
            parse_article_fn=lambda url, timeout_seconds: {"url": url},
        )

        self.assertEqual(payload["articles"], [])

    def test_fetch_news_filters_articles_that_do_not_mention_company_terms(self):
        payload = CompanyNewsAdapter.fetch_news_payload(
            company="Example Inc",
            source="gnews",
            limit=5,
            days=30,
            timeout_seconds=10,
            discover_fn=lambda *args: [
                {"title": "3M now has more than 100,000 patents", "url": "https://news.example.com/3m"},
                {"title": "Example Inc announces new supplier project", "url": "https://news.example.com/example"},
            ],
            parse_article_fn=lambda url, timeout_seconds: {"url": url},
        )

        self.assertEqual(len(payload["articles"]), 1)
        self.assertEqual(payload["articles"][0]["title"], "Example Inc announces new supplier project")

    def test_run_writes_company_news_artifact_without_subprocess(self):
        adapter = CompanyNewsAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = adapter.run(
                target_type="company",
                target_value="Example Inc",
                workdir=Path(tmpdir),
                timeout_seconds=5,
                fetch_fn=lambda **kwargs: {
                    "source": "gnews",
                    "query": '"Example Inc" company news',
                    "articles": [{"title": "Example Inc announces project"}],
                },
            )

            artifact = result.command.expected_artifact
            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["articles"][0]["title"], "Example Inc announces project")


if __name__ == "__main__":
    unittest.main()
