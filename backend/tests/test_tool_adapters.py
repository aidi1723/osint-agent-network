import json
import tempfile
import unittest
from pathlib import Path

from app.tools.sherlock import SherlockAdapter
from app.tools.theharvester import TheHarvesterAdapter
from app.tools.amass import AmassAdapter
from app.tools.ghunt import GHuntAdapter
from app.tools.maigret import MaigretAdapter
from app.tools.phoneinfoga import PhoneInfogaAdapter
from app.tools.profile_parser import ProfileParserAdapter
from app.tools.spiderfoot import SpiderFootAdapter
from app.tools.socialscan import SocialScanAdapter
from app.tools.reconng import ReconNgAdapter
from app.tools.company_news import CompanyNewsAdapter


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
        self.assertIn(("external_link", "https://admin.example.com"), entities)
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
        self.assertIn(("external_link", "https://admin.example.com"), entities)
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
