# Real Sample Regression Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public-safe file-level regression fixture pack that protects core OSINT parser behavior from future drift.

**Architecture:** Add minimal synthetic-realistic tool output files under `backend/tests/fixtures/tool_outputs/` and a focused unittest module that calls each adapter's `parse_artifact()` method. Keep tests assertion-based rather than snapshot-based, and update phase documentation with verification and privacy-scan results after implementation.

**Tech Stack:** Python `unittest`, existing adapter classes in `backend/app/tools/`, JSON/JSONL/HTML fixtures, existing `bash scripts/verify.sh` verification flow.

---

## File Structure

- Create: `backend/tests/test_tool_fixture_regressions.py`
  - Owns file-level parser regression tests for the P1 fixture pack.
- Create: `backend/tests/fixtures/tool_outputs/official_site_search/example_company_results.json`
  - Public-safe SearXNG-like official-site search response.
- Create: `backend/tests/fixtures/tool_outputs/httpx/example_company_live.jsonl`
  - Public-safe `httpx -json` style live URL output.
- Create: `backend/tests/fixtures/tool_outputs/katana/example_company_pages.jsonl`
  - Public-safe `katana -jsonl` style crawl output.
- Create: `backend/tests/fixtures/tool_outputs/official_site_extractor/example_company_official.html`
  - Public-safe official-site HTML containing identity, contacts, scope, and address.
- Create: `backend/tests/fixtures/tool_outputs/subfinder/example_company_subdomains.jsonl`
  - Public-safe `subfinder -json` style passive subdomain output.
- Create: `backend/tests/fixtures/tool_outputs/role_agent_outputs/example_sparse_lead_summary.json`
  - Public-safe role-agent summary contract sample.
- Modify: `docs/NEXT_PHASE_ROADMAP_2026-07-06.md`
  - Mark P1 progress and record verification evidence.

## Task 1: Add Fixture Regression Test Skeleton

**Files:**
- Create: `backend/tests/test_tool_fixture_regressions.py`

- [x] **Step 1: Write the failing test module**

Create `backend/tests/test_tool_fixture_regressions.py` with this content:

```python
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
```

- [x] **Step 2: Run test to verify it fails because fixtures are missing**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_tool_fixture_regressions.py' -v
```

Expected: FAIL or ERROR with missing fixture file paths under `backend/tests/fixtures/tool_outputs/`.

## Task 2: Add Public-Safe Tool Output Fixtures

**Files:**
- Create: `backend/tests/fixtures/tool_outputs/official_site_search/example_company_results.json`
- Create: `backend/tests/fixtures/tool_outputs/httpx/example_company_live.jsonl`
- Create: `backend/tests/fixtures/tool_outputs/katana/example_company_pages.jsonl`
- Create: `backend/tests/fixtures/tool_outputs/official_site_extractor/example_company_official.html`
- Create: `backend/tests/fixtures/tool_outputs/subfinder/example_company_subdomains.jsonl`
- Create: `backend/tests/fixtures/tool_outputs/role_agent_outputs/example_sparse_lead_summary.json`

- [x] **Step 1: Add official-site search JSON fixture**

Create `backend/tests/fixtures/tool_outputs/official_site_search/example_company_results.json`:

```json
{
  "target_type": "company",
  "target_value": "Example Manufacturing LLC",
  "query": "\"Example Manufacturing LLC\" official website contact",
  "results": [
    {
      "title": "Example Manufacturing LLC - Official Website",
      "url": "https://www.example-target.test/about?utm_source=fixture",
      "content": "Official site for Example Manufacturing LLC. Contact our sales team for uPVC windows and curtain wall systems."
    },
    {
      "title": "Example Manufacturing LLC directory profile",
      "url": "https://directory.example/listing/example-manufacturing",
      "content": "Third-party listing compiled from public business directories."
    }
  ]
}
```

- [x] **Step 2: Add httpx JSONL fixture**

Create `backend/tests/fixtures/tool_outputs/httpx/example_company_live.jsonl`:

```jsonl
{"url":"https://www.example.com","input":"www.example.com","title":"Example Manufacturing - Contact","tech":["nginx","WordPress"],"status_code":200}
```

- [x] **Step 3: Add katana JSONL fixture**

Create `backend/tests/fixtures/tool_outputs/katana/example_company_pages.jsonl`:

```jsonl
{"url":"https://www.example.com/contact","source":"href"}
{"url":"https://www.example.com/products/upvc-windows","source":"href"}
{"url":"https://www.example.com/assets/site.css","source":"href"}
{"url":"https://www.example.com/privacy","source":"href"}
```

- [x] **Step 4: Add official-site extractor HTML fixture**

Create `backend/tests/fixtures/tool_outputs/official_site_extractor/example_company_official.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <title>Example Manufacturing - uPVC Windows and Curtain Wall</title>
    <meta name="description" content="Example Manufacturing LLC supplies uPVC windows, aluminum curtain wall systems, and sliding doors.">
    <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Organization","name":"Example Manufacturing LLC","url":"https://www.example.com","email":"sales@example.com","telephone":"+1 212 555 0123","address":{"@type":"PostalAddress","streetAddress":"88 Industrial Road","addressLocality":"Newark","addressRegion":"NJ"}}
    </script>
  </head>
  <body>
    <h1>Example Manufacturing LLC</h1>
    <p>We manufacture uPVC windows, aluminum curtain wall systems, and sliding doors for commercial projects.</p>
    <p>Contact sales@example.com or call +1 212 555 0123.</p>
    <p>Address: 88 Industrial Road, Newark, NJ</p>
  </body>
</html>
```

- [x] **Step 5: Add subfinder JSONL fixture**

Create `backend/tests/fixtures/tool_outputs/subfinder/example_company_subdomains.jsonl`:

```jsonl
{"host":"www.example.com","source":"crtsh"}
{"host":"support.example.com","sources":["alienvault","certspotter"]}
{"host":"example.com","source":"root-domain"}
```

- [x] **Step 6: Add role-agent summary fixture**

Create `backend/tests/fixtures/tool_outputs/role_agent_outputs/example_sparse_lead_summary.json`:

```json
{
  "fixture_version": 1,
  "privacy": "public_safe_synthetic",
  "target_type": "sparse_lead",
  "target_value": "Example Manufacturing LLC",
  "role": "company_enrichment",
  "official_site_candidates": [
    {
      "url": "https://www.example-target.test/about",
      "source_tool": "official_site_search",
      "reason": "Search title and snippet indicate an official company site."
    }
  ],
  "collection_gaps": [
    {
      "field": "decision_maker",
      "status": "needs_review",
      "reason": "No named executive was confirmed by the public-safe fixture."
    }
  ],
  "notes": "Synthetic sample for regression tests only."
}
```

- [x] **Step 7: Run fixture regression tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_tool_fixture_regressions.py' -v
```

Expected: PASS. If a parser mismatch appears, inspect the adapter and change only the smallest necessary fixture or assertion unless the adapter is dropping intended evidence.

## Task 3: Run Shared Backend Test Surface

**Files:**
- Test: `backend/tests/test_tool_fixture_regressions.py`
- Test: `backend/tests/test_tool_adapters.py`

- [x] **Step 1: Run adapter and fixture tests together**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_tool_adapters.py' -v
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_tool_fixture_regressions.py' -v
```

Expected: PASS. This confirms the new fixture regression pack did not weaken existing adapter behavior.

- [x] **Step 2: Review diff for parser changes**

Run:

```bash
git diff -- backend/app/tools backend/tests/test_tool_fixture_regressions.py backend/tests/fixtures/tool_outputs
```

Expected: Only the new test and fixtures should normally appear. If adapter code changed, the diff must show a narrow parser gap fix tied to a failing fixture regression.

## Task 4: Update Phase Records

**Files:**
- Modify: `docs/NEXT_PHASE_ROADMAP_2026-07-06.md`

- [x] **Step 1: Add a P1 progress note**

Append this section near the end of `docs/NEXT_PHASE_ROADMAP_2026-07-06.md`:

```markdown
## P1 Progress - Real Sample Regression Pack

Implemented public-safe file-level parser fixtures for:

- `official_site_search`
- `httpx`
- `katana`
- `official_site_extractor`
- `subfinder`
- role-agent sparse-lead summary output

Protected behavior:

- official-site candidates remain linked to company targets;
- live URLs keep title, technology, and probe evidence;
- crawler output keeps relevant business/contact pages and filters noise;
- official-site HTML yields identity, contact, scope, address, evidence, and relationships;
- passive subdomains keep source evidence and root-domain relationships;
- role-agent output has a public-safe documented fixture shape.

Verification:

- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_tool_adapters.py' -v`
- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_tool_fixture_regressions.py' -v`
- `bash scripts/verify.sh`
- added-line privacy scan
```

- [x] **Step 2: Run documentation diff review**

Run:

```bash
git diff -- docs/NEXT_PHASE_ROADMAP_2026-07-06.md
```

Expected: The roadmap records P1 completion evidence without exposing private task names, hostnames, local paths, or tokens.

## Task 5: Full Verification, Privacy Scan, and Commit

**Files:**
- All files changed in this plan.

- [x] **Step 1: Run full verification**

Run:

```bash
bash scripts/verify.sh
```

Expected: backend tests pass, frontend helper checks pass, Vitest passes, and frontend production build passes.

- [x] **Step 2: Run added-line privacy scan**

Run:

Run the added-line privacy scan documented in
`docs/PUBLIC_REPOSITORY_MAINTENANCE.md`.

Expected: no matches. If `rg` exits with code `1`, that means no matches were found.

- [x] **Step 3: Review final status**

Run:

```bash
git status --short
```

Expected: only intended test, fixture, and documentation files are modified or untracked.

- [x] **Step 4: Commit implementation**

Run:

```bash
git add backend/tests/test_tool_fixture_regressions.py backend/tests/fixtures/tool_outputs docs/NEXT_PHASE_ROADMAP_2026-07-06.md
git commit -m "test: add real sample parser regression pack"
```

Expected: commit succeeds.

- [x] **Step 5: Push if the repository is clean and verification passed**

Run:

```bash
git push
```

Expected: remote branch receives the P1 implementation commit.

## Self-Review Checklist

- Spec coverage: all requested P1 adapters, role-agent sample, official-site evidence chain, verification, and privacy scan are represented.
- No broad snapshots: tests assert selected entities, evidence, and relationships.
- No live collection: all tests use local public-safe fixtures.
- No new dependencies: only standard library and existing adapter classes are used.
- Public safety: all sample values use `example.com`, `example-target.test`, and generic company names.
