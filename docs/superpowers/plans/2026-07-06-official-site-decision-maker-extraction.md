# Official Site Decision-Maker Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add conservative, source-backed public decision-maker candidate extraction to `official_site_extractor`.

**Architecture:** Extend the existing official-site HTML parser rather than adding a new tool. The parser will identify public person/title pairs from JSON-LD `Person` records and visible official-page text, then emit candidate entities, evidence, and relationships for existing quality and cross-verification flows.

**Tech Stack:** Python standard library HTML parsing and regex, existing `ParsedToolOutput`/normalization helpers, `unittest`, existing `scripts/verify.sh`.

---

## File Structure

- Modify `backend/app/tools/official_site_extractor.py`
  - Add role marker constants.
  - Add visible-text and JSON-LD person candidate extraction helpers.
  - Add candidate output helper that emits `person`, `job_title`, `decision_maker`, evidence, and relationships.
- Modify `backend/tests/test_tool_adapters.py`
  - Add parser tests for visible-text candidates, JSON-LD candidates, generic label rejection, and nearby contact linking.
- Modify `backend/tests/test_quality_gate.py`
  - Add a regression proving official-site person candidates satisfy the `decision_maker` signal while still not bypassing other completion gates.
- Modify docs after verification:
  - `docs/UPDATE_LOG.md`
  - `docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md`

## Task 1: Visible-Text Decision-Maker Candidate Test

**Files:**
- Modify: `backend/tests/test_tool_adapters.py`
- Modify: `backend/app/tools/official_site_extractor.py`

- [ ] **Step 1: Write the failing test**

Add this test inside `OfficialSiteExtractorAdapterTests`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_tool_adapters.OfficialSiteExtractorAdapterTests.test_parser_extracts_visible_text_decision_maker_candidate
```

Expected: fail because `person`, `job_title`, `decision_maker`, and decision-maker relationships are not emitted yet.

- [ ] **Step 3: Implement minimal visible-text extraction**

In `backend/app/tools/official_site_extractor.py`, add constants near `BUSINESS_SCOPE_PATTERNS`:

```python
ROLE_MARKERS = (
    "owner",
    "founder",
    "co-founder",
    "ceo",
    "president",
    "managing director",
    "director",
    "general manager",
    "sales manager",
    "export manager",
    "procurement manager",
    "purchasing manager",
    "contact person",
)

GENERIC_PERSON_LABELS = {
    "Contact Us",
    "Sales Team",
    "Customer Service",
    "About Us",
}
```

Add decision-maker emission before `return ParsedToolOutput(...)` in `parse_html`:

```python
        for candidate in _decision_maker_candidates(text, structured):
            _add_decision_maker_candidate(
                candidate,
                normalized_url,
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
            )
```

Add helper functions after `_addresses`:

```python
def _decision_maker_candidates(text: str, items: list[dict]) -> list[dict]:
    candidates = []
    candidates.extend(_json_ld_people(items))
    candidates.extend(_visible_text_people(text))
    seen: set[tuple[str, str]] = set()
    result = []
    for candidate in candidates:
        key = (candidate["name"].lower(), candidate["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result[:5]
```

Add minimal visible parser:

```python
def _visible_text_people(text: str) -> list[dict]:
    candidates = []
    sentence_parts = re.split(r"(?<=[.!?])\s+|\s{2,}", text)
    for part in sentence_parts:
        window = _normalize_space(part)
        if not window:
            continue
        for marker in ROLE_MARKERS:
            match = re.search(
                rf"\b([A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){{1,3}})\s*[,|-]\s*({re.escape(marker)})\b",
                window,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            name = _normalize_person_name(match.group(1))
            title = _normalize_job_title(match.group(2))
            if name and title:
                candidates.append({"name": name, "title": title, "confidence": 0.66, "context": window})
    return candidates
```

Add output helper:

```python
def _add_decision_maker_candidate(
    candidate: dict,
    url: str,
    entities: list[NormalizedEntity],
    evidence: list[NormalizedEvidence],
    relationships: list[NormalizedRelationship],
    seen_entities: set[tuple[str, str]],
    seen_evidence: set[tuple[str, str, str]],
    seen_relationships: set[tuple[str, str, str]],
) -> None:
    name = str(candidate.get("name") or "")
    title = str(candidate.get("title") or "")
    confidence = float(candidate.get("confidence") or 0.66)
    if not name or not title:
        return
    decision_value = f"{name} - {title}"
    snippet = f"Official site {url} lists {decision_value}"
    append_unique_entity(entities, seen_entities, NormalizedEntity("person", name, "official_site_extractor", confidence))
    append_unique_entity(entities, seen_entities, NormalizedEntity("job_title", title, "official_site_extractor", confidence))
    append_unique_entity(entities, seen_entities, NormalizedEntity("decision_maker", decision_value, "official_site_extractor", confidence))
    append_unique_evidence(
        evidence,
        seen_evidence,
        NormalizedEvidence(name, "official_site_decision_maker_candidate", "official_site_extractor", snippet),
    )
    append_unique_relationship(
        relationships,
        seen_relationships,
        NormalizedRelationship(url, name, "official_site_mentions_decision_maker", confidence),
    )
    append_unique_relationship(
        relationships,
        seen_relationships,
        NormalizedRelationship(name, title, "person_has_public_role", confidence),
    )
    for contact in _nearby_contacts(str(candidate.get("context") or "")):
        append_unique_relationship(
            relationships,
            seen_relationships,
            NormalizedRelationship(name, contact, "person_has_contact", min(confidence, 0.64)),
        )
```

Add normalization helpers:

```python
def _normalize_person_name(value: str) -> str:
    name = _normalize_space(value).strip(" .,:;-")
    if name in GENERIC_PERSON_LABELS:
        return ""
    tokens = name.split()
    if len(tokens) < 2 or len(tokens) > 4:
        return ""
    if any(token.lower() in {"contact", "sales", "team", "service", "about"} for token in tokens):
        return ""
    return name


def _normalize_job_title(value: str) -> str:
    title = _normalize_space(value).strip(" .,:;-")
    for marker in ROLE_MARKERS:
        if title.lower() == marker:
            return " ".join(part.capitalize() if part.lower() != "ceo" else "CEO" for part in marker.split())
    return ""


def _nearby_contacts(context: str) -> list[str]:
    contacts = []
    contacts.extend(_emails(context, []))
    contacts.extend(_phones(context, []))
    return contacts[:2]
```

- [ ] **Step 4: Run test to verify it passes**

Run the same command. Expected: pass.

## Task 2: JSON-LD Person Candidate Test

**Files:**
- Modify: `backend/tests/test_tool_adapters.py`
- Modify: `backend/app/tools/official_site_extractor.py`

- [ ] **Step 1: Write the failing test**

Add this test inside `OfficialSiteExtractorAdapterTests`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_tool_adapters.OfficialSiteExtractorAdapterTests.test_parser_extracts_json_ld_person_decision_maker_candidate
```

Expected: fail until `_json_ld_people` is implemented.

- [ ] **Step 3: Implement JSON-LD extraction**

Add this helper:

```python
def _json_ld_people(items: list[dict]) -> list[dict]:
    candidates = []
    for item in items:
        item_type = item.get("@type")
        types = item_type if isinstance(item_type, list) else [item_type]
        if not any(str(t).lower() == "person" for t in types):
            continue
        name = _normalize_person_name(str(item.get("name") or ""))
        title = _normalize_job_title(str(item.get("jobTitle") or item.get("title") or ""))
        if not name or not title:
            continue
        context = " ".join(
            str(item.get(key) or "")
            for key in ("name", "jobTitle", "title", "email", "telephone", "phone")
            if str(item.get(key) or "")
        )
        candidates.append({"name": name, "title": title, "confidence": 0.70, "context": context})
    return candidates
```

- [ ] **Step 4: Run test to verify it passes**

Run the same command. Expected: pass.

## Task 3: Rejection And Distant Contact Tests

**Files:**
- Modify: `backend/tests/test_tool_adapters.py`
- Modify: `backend/app/tools/official_site_extractor.py`

- [ ] **Step 1: Write the failing test**

Add this test inside `OfficialSiteExtractorAdapterTests`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails if safeguards are incomplete**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_tool_adapters.OfficialSiteExtractorAdapterTests.test_parser_rejects_generic_decision_labels_and_distant_contacts
```

Expected: fail if the visible-text parser captures generic labels or links page-level emails to unrelated people.

- [ ] **Step 3: Tighten visible-text parsing if needed**

Ensure `_visible_text_people` only scans short sentence/window fragments and passes only the matched fragment to `context`. Keep `_nearby_contacts()` limited to that candidate context.

- [ ] **Step 4: Run all official-site extractor adapter tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_tool_adapters.OfficialSiteExtractorAdapterTests
```

Expected: all tests pass, including existing organization/email/phone/business-scope tests.

## Task 4: Quality-Gate Regression

**Files:**
- Modify: `backend/tests/test_quality_gate.py`

- [ ] **Step 1: Write the quality-gate test**

Add this test inside `QualityGateTests`:

```python
    def test_official_site_person_candidate_satisfies_decision_maker_signal_only(self):
        detail = {
            "seed_type": "company",
            "seed_value": "Sample Auto Parts Co.",
            "entities": [
                {"type": "company", "value": "Sample Auto Parts Co.", "confidence": 0.82},
                {"type": "url", "value": "https://example.com/team", "confidence": 0.72},
                {"type": "person", "value": "Jane Smith", "confidence": 0.66, "source_tool": "official_site_extractor"},
                {"type": "job_title", "value": "Export Manager", "confidence": 0.66, "source_tool": "official_site_extractor"},
                {"type": "decision_maker", "value": "Jane Smith - Export Manager", "confidence": 0.66, "source_tool": "official_site_extractor"},
            ],
            "evidence": [
                {
                    "entity_value": "Jane Smith",
                    "evidence_kind": "official_site_decision_maker_candidate",
                    "source_tool": "official_site_extractor",
                }
            ],
            "evidence_ledger": [],
            "facts": [],
            "hypotheses": [],
            "relationships": [
                {"from_value": "https://example.com/team", "to_value": "Jane Smith", "relationship_type": "official_site_mentions_decision_maker"}
            ],
            "report_markdown": "",
        }

        assessment = build_quality_assessment(detail)

        self.assertNotIn("decision_maker", assessment["missing_keys"])
        self.assertIn("evidence_ledger", assessment["blocking_keys"])
        self.assertFalse(assessment["completion_ready"])
```

- [ ] **Step 2: Run quality-gate test**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_quality_gate.QualityGateTests.test_official_site_person_candidate_satisfies_decision_maker_signal_only
```

Expected: pass if the current quality gate already accepts `person`/`decision_maker` at confidence `>=0.55`.

## Task 5: Documentation, Verification, And Commit

**Files:**
- Modify: `docs/UPDATE_LOG.md`
- Modify: `docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md`

- [ ] **Step 1: Run targeted tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_tool_adapters.OfficialSiteExtractorAdapterTests backend.tests.test_quality_gate.QualityGateTests
```

Expected: pass.

- [ ] **Step 2: Run full local verification**

Run:

```bash
bash scripts/verify.sh
```

Expected: backend unit suite, regression smoke, frontend checks, Vitest, and production build pass.

- [ ] **Step 3: Run <production-host> readiness**

Run:

```bash
ssh <production-host> 'cd <production-path> && bash scripts/healthcheck.sh && PYTHONPATH=backend python3 scripts/production_readiness.py'
```

Expected: `ready=true`, `severity=ok`.

- [ ] **Step 4: Update docs**

Append a concise note to `docs/UPDATE_LOG.md` and `docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md` with:

- implemented `official_site_extractor` decision-maker candidate parsing;
- targeted tests run;
- full verification result;
- <production-host> readiness result;
- remaining caveat that candidates remain conservative and need cross-verification before accepted-fact promotion.

- [ ] **Step 5: Privacy scan**

Run:

```bash
git diff --unified=0 -- . | rg '^\+' | rg -n '<private-target-name>|<private-investigation-id>|<personal-home-path>|<private-host-alias>|192\.168\.|10\.[0-9]+\.|172\.(1[6-9]|2[0-9]|3[01])\.|Bearer [A-Za-z0-9._~-]{12,}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}'
```

Expected: no output and exit code `1`.

- [ ] **Step 6: Commit and push**

Run:

```bash
git add backend/app/tools/official_site_extractor.py backend/tests/test_tool_adapters.py backend/tests/test_quality_gate.py docs/UPDATE_LOG.md docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md docs/superpowers/plans/2026-07-06-official-site-decision-maker-extraction.md
git commit -m "Extract decision maker candidates from official sites"
git push origin main
```

Expected: push succeeds and `git status --short --branch` shows `main...origin/main` with no changes.
