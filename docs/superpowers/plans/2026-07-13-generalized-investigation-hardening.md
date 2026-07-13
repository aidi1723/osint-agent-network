# Generalized Investigation Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve evidence and SSRF controls while adding reviewed fake-IP approvals, more general official-site extraction, accurate contact semantics, measurable acceptance, and tool-capability limits.

**Architecture:** `safe_http` remains the sole destination validator; an optional approval file produces the same exact-host `FakeIpAllowance` without widening the hostname boundary. A pure semantic helper converts official-page structure into source-backed scope/contact candidates. The acceptance runner uses only the standard library and cannot call an API unless `--execute` is explicit.

**Tech Stack:** Python 3.11+, `unittest`, `urllib.request`, `html.parser`, existing worker/report pipeline, JSON/HTML fixtures, npm/Vitest.

---

## File Structure

- Modify `backend/app/core/safe_http.py`: approval-file parsing and a safe review-required exception.
- Modify `backend/app/tools/official_site_extractor.py`: diagnostic handling, semantic input capture, normalized output.
- Create `backend/app/tools/official_site_semantics.py`: immutable scope/contact candidates and deterministic extraction.
- Modify `backend/app/core/tool_health.py`, `backend/app/services/worker.py`, `backend/app/core/quality.py`: capability impact in health, summary, and report.
- Modify `scripts/regression_smoke.py`; create `scripts/real_acceptance.py`.
- Create multilingual official-site fixtures, acceptance-manifest fixture, and focused `unittest` modules.
- Modify `.env.example`, deployment/baseline docs; create `docs/REAL_ACCEPTANCE_RUNBOOK.md`.

## Task 1: Reviewed Fake-IP Approval Contract

**Files:**

- Modify: `backend/app/core/safe_http.py:18-107,136-207,398-411`
- Modify: `backend/app/tools/official_site_extractor.py:10-136`
- Test: `backend/tests/test_safe_http.py`, `backend/tests/test_tool_adapters.py`
- Modify: `.env.example`, `docs/N100_DEPLOYMENT_RUNBOOK.md`
- Test: `backend/tests/test_environment_template.py`, `backend/tests/test_release_artifacts.py`

- [ ] **Step 1: Write failing safe HTTP and adapter tests**

```python
def test_reviewed_file_allows_only_unexpired_exact_hostname(self):
    now = datetime(2026, 7, 13, tzinfo=UTC)
    with TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "fake-ip-approvals.json"
        path.write_text(json.dumps({
            "version": 1,
            "networks": ["198.18.0.0/15"],
            "approvals": [{
                "hostname": "Example.COM.", "approved_by": "ops-reviewer",
                "approved_at": "2026-07-13T00:00:00Z",
                "expires_at": "2026-10-01T00:00:00Z",
                "reason": "Verified public official site",
            }],
        }), encoding="utf-8")
        allowance = fake_ip_allowance_from_env(
            {"OSINT_SAFE_HTTP_FAKE_IP_APPROVALS_FILE": str(path)}, now=now
        )
    self.assertEqual(
        validate_public_url("https://example.com/", resolver=resolver_for("198.18.100.99"), fake_ip_allowance=allowance).hostname,
        "example.com",
    )
    with self.assertRaises(FakeIpApprovalRequired) as caught:
        validate_public_url("https://www.example.com/", resolver=resolver_for("198.18.100.99"), fake_ip_allowance=allowance)
    self.assertEqual(caught.exception.hostname, "www.example.com")
```

Add separate failures for expired records, wildcard records, missing reviewer/reason/timestamps, duplicate normalized hosts, legacy/file mode mixing, direct fake-IP literals, and unapproved redirect hosts. Add:

```python
def test_run_reports_fake_ip_review_without_url_path_or_ip(self):
    with patch("app.tools.official_site_extractor.safe_fetch", side_effect=FakeIpApprovalRequired("www.example.com")), TemporaryDirectory() as tmpdir:
        result = OfficialSiteExtractorAdapter().run("url", "https://www.example.com/private-token", Path(tmpdir), 5)
    self.assertEqual(result.stderr_excerpt, "fake_ip_review_required: www.example.com")
    self.assertNotIn("private-token", result.stderr_excerpt)
    self.assertNotIn("198.18", result.stderr_excerpt)
```

- [ ] **Step 2: Verify that the tests fail before implementation**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_safe_http.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_tool_adapters.py' -v
```

Expected: the approval-file API and structured diagnostic do not yet exist.

- [ ] **Step 3: Implement strict file mode**

```python
class FakeIpApprovalRequired(BlockedNetworkTarget):
    def __init__(self, hostname: str):
        super().__init__("fake-IP host requires review")
        self.hostname = hostname

def fake_ip_allowance_from_env(environ: Mapping[str, str] | None = None, *, now: datetime | None = None) -> FakeIpAllowance:
    environ = os.environ if environ is None else environ
    approval_path = str(environ.get("OSINT_SAFE_HTTP_FAKE_IP_APPROVALS_FILE", "")).strip()
    legacy_cidrs = str(environ.get("OSINT_SAFE_HTTP_FAKE_IP_CIDRS", "")).strip()
    legacy_hosts = str(environ.get("OSINT_SAFE_HTTP_FAKE_IP_HOSTS", "")).strip()
    if approval_path:
        if legacy_cidrs or legacy_hosts:
            raise InvalidFakeIpConfiguration("invalid fake-IP allowance configuration")
        return _approval_file_allowance(Path(approval_path), now or datetime.now(UTC))
    return _legacy_fake_ip_allowance(legacy_cidrs, legacy_hosts)
```

Implement `_approval_file_allowance` with a 64 KiB read limit, `version == 1`, fake-supernet subnet validation, exact IDNA hostname normalization, reviewer/reason/timestamp validation, `expires_at > approved_at`, `expires_at > now`, and duplicate rejection. Every malformed input raises only `InvalidFakeIpConfiguration("invalid fake-IP allowance configuration")`.

Raise `FakeIpApprovalRequired(ascii_hostname)` for an unapproved nonliteral fake-IP hostname; retain `BlockedNetworkTarget` for direct literals, IPv6, private/reserved answers, and mixed unsafe results. Catch the new exception before broad `SafeHttpError` in the adapter and return `ToolRunResult(command, 1, "", f"fake_ip_review_required: {exc.hostname}")`.

- [ ] **Step 4: Document and prove the migration boundary**

Add `OSINT_SAFE_HTTP_FAKE_IP_APPROVALS_FILE=` after the legacy pair in `.env.example`. State in the runbook that file and legacy modes are mutually exclusive, hosts are exact, entries expire, wildcards are rejected, and IP literals stay blocked. Extend environment/release tests accordingly.

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_safe_http.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_tool_adapters.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_environment_template.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_release_artifacts.py' -v
```

Expected: only approved exact hosts can use fake-IP mappings, with no URL path, IP, credential, or resolver detail in review output.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/safe_http.py backend/app/tools/official_site_extractor.py backend/tests/test_safe_http.py backend/tests/test_tool_adapters.py backend/tests/test_environment_template.py backend/tests/test_release_artifacts.py .env.example docs/N100_DEPLOYMENT_RUNBOOK.md
git commit -m "feat: add reviewed fake-ip approvals"
```

## Task 2: Source-Backed Business Scope and Contact Semantics

**Files:**

- Create: `backend/app/tools/official_site_semantics.py`
- Modify: `backend/app/tools/official_site_extractor.py:15-45,145-250,268-574`
- Test: `backend/tests/test_tool_adapters.py`, `backend/tests/test_tool_fixture_regressions.py`
- Create: `backend/tests/fixtures/tool_outputs/official_site_extractor/chinese_services.html`
- Create: `backend/tests/fixtures/tool_outputs/official_site_extractor/french_catalog.json.html`

- [ ] **Step 1: Write failing semantic tests**

Require the Chinese fixture to contain a scope value including `膜过滤系统`, `official_site_business_scope_meta` or `official_site_business_scope_heading` evidence, a `fax` entity, and no `phone` entity for that fax number. Require the French JSON-LD fixture to emit `Pompes industrielles` with `official_site_business_scope_json_ld` evidence.

```python
def test_parser_only_links_contacts_to_named_roles_in_same_context(self):
    html = """<html><body>
      <p>Jane Smith, Export Manager - jane.smith@example.com - +1 212 555 0123</p>
      <p>Customer Service: service@example.com</p><p>Fax: +1 212 555 0199</p>
    </body></html>"""
    parsed = OfficialSiteExtractorAdapter().parse_html(html, "https://example.com/contact")
    entities = {(item.type, item.value) for item in parsed.entities}
    relationships = {(item.from_value, item.to_value, item.relationship_type) for item in parsed.relationships}
    self.assertIn(("fax", "+12125550199"), entities)
    self.assertNotIn(("phone", "+12125550199"), entities)
    self.assertIn(("Jane Smith", "jane.smith@example.com", "person_has_role_linked_contact"), relationships)
    self.assertNotIn(("Jane Smith", "service@example.com", "person_has_role_linked_contact"), relationships)
```

- [ ] **Step 2: Verify failures**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_tool_adapters.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_tool_fixture_regressions.py' -v
```

Expected: source-specific evidence, fixtures, fax classification, and role-linked relation are absent.

- [ ] **Step 3: Create pure candidate helpers**

```python
@dataclass(frozen=True)
class ScopeCandidate:
    value: str
    evidence_kind: str
    snippet: str
    confidence: float

@dataclass(frozen=True)
class ContactCandidate:
    entity_type: str
    value: str
    classification: str
    snippet: str
```

Implement `extract_scope_candidates(text, structured, descriptions, headings)` in source order: JSON-LD product/service/catalog values, JSON-LD descriptions, meta descriptions, headings, bounded English/Chinese cue-bearing text, fixed-pattern fallback. Normalize/cap/dedupe candidates and reject navigation, cookie, contact, and generic-only text. Structured product/service values remain language-neutral; free text is deterministic English/Chinese cue matching only.

Implement `extract_contact_candidates(text, structured)` for surrounding context and JSON-LD `email`, `telephone`, `phone`, and `faxNumber`. Classify `fax`, then `customer_service`, then `public_general`; fax never becomes a `phone` entity.

- [ ] **Step 4: Wire helpers into the adapter**

Extend `_OfficialSiteHTMLParser` with meta-description and `h1`-`h3` collection. Extend `_add_entity` with an optional evidence snippet:

```python
def _add_entity(
    entity_type: str,
    value: str,
    evidence_kind: str,
    relationship_type: str,
    url: str,
    entities: list[NormalizedEntity],
    evidence: list[NormalizedEvidence],
    relationships: list[NormalizedRelationship],
    seen_entities: set[tuple[str, str]],
    seen_evidence: set[tuple[str, str, str]],
    seen_relationships: set[tuple[str, str, str]],
    confidence: float,
    evidence_snippet: str | None = None,
) -> None:
    normalized_value = _normalize_entity_value(entity_type, value)
    if not normalized_value:
        return
    snippet = evidence_snippet or f"Official site {url} contains {entity_type}: {normalized_value}"
    append_unique_evidence(evidence, seen_evidence, NormalizedEvidence(normalized_value, evidence_kind, "official_site_extractor", snippet))
```

Emit business scopes with source-specific evidence; retain `official_site_business_scope` only for fixed-pattern fallback. Emit contacts as `email`, `phone`, or `fax` with `official_site_contact_<classification>` evidence and `official_site_lists_<classification>_<entity_type>` relationship. Replace `person_has_contact` with `person_has_role_linked_contact` only where person, title, and contact occur in one bounded context; do not emit delivery/call/reachability claims.

- [ ] **Step 5: Add fixtures, run tests, and commit**

Create Chinese scope text `工业水处理设备、膜过滤系统和工程服务`, with a named manager, separate service inbox, and separate fax. Create a JSON-LD French `Product` `Pompes industrielles` and `Service` `Maintenance hydraulique`, using only synthetic data.

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_tool_adapters.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_tool_fixture_regressions.py' -v
git add backend/app/tools/official_site_semantics.py backend/app/tools/official_site_extractor.py backend/tests/test_tool_adapters.py backend/tests/test_tool_fixture_regressions.py backend/tests/fixtures/tool_outputs/official_site_extractor/chinese_services.html backend/tests/fixtures/tool_outputs/official_site_extractor/french_catalog.json.html
git commit -m "feat: enrich official site evidence extraction"
```

Expected: legacy extraction stays stable; multilingual scopes remain source-backed; generic service and fax contacts never become decision-maker links.

## Task 3: Capability Impact Without Status Inflation

**Files:**

- Modify: `backend/app/core/tool_health.py:18-115`
- Modify: `backend/app/services/worker.py:74-188`
- Modify: `backend/app/core/quality.py:96-218,319-395`
- Test: `backend/tests/test_tool_health.py`, `backend/tests/test_quality_gate.py`, `backend/tests/test_worker.py`

- [ ] **Step 1: Write failing health/report tests**

```python
def test_unavailable_tools_are_grouped_by_affected_capability(self):
    registry = ToolRegistry([
        ToolDefinition("amass", "OWASP Amass", "sync_cli", ("domain",), ("subdomain",), False, 120, 0.5),
        ToolDefinition("socialscan", "socialscan", "sync_cli", ("email",), ("profile_url",), False, 120, 0.5),
    ])
    with patch("app.core.tool_health.shutil.which", return_value=None):
        report = build_tool_health_report(registry=registry, env={})
    by_name = {item["name"]: item for item in report["tools"]}
    self.assertEqual(by_name["amass"]["coverage_areas"], ["asset_discovery"])
    self.assertEqual(report["summary"]["affected_capabilities"], {"asset_discovery": ["amass"], "social_identity": ["socialscan"]})
```

Add a report test with unavailable `amass`, requiring `## 环境覆盖限制`, `asset_discovery`, and `amass`, while preserving its original `completion_ready` value.

- [ ] **Step 2: Verify failure, implement mapping, verify pass**

Add:

```python
TOOL_COVERAGE_AREAS = {
    "theharvester": ("contact_discovery",), "phoneinfoga": ("contact_validation_assist",),
    "maigret": ("social_identity",), "socialscan": ("social_identity",),
    "spiderfoot": ("contact_discovery", "social_identity", "asset_discovery"),
    "amass": ("asset_discovery",), "customs_supply_chain": ("supply_chain_evidence",),
}
```

Every health item gets `coverage_areas`; `_affected_capabilities` includes only unavailable statuses and returns sorted capability-to-tool lists in `summary["affected_capabilities"]`. Before final worker rendering, generate `health_snapshot = build_tool_health_report()`, include it in `summary["tool_health"]`, and call:

```python
report_markdown = render_structured_report(
    {**detail, "summary": summary_text, "completion_policy": completion_policy, "tool_health": health_snapshot},
    quality_assessment,
)
```

Add `_environment_coverage_lines` in `quality.py` after gap-followup lines. It says coverage is reduced; it does not change score, blockers, or recommended status.

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_tool_health.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_quality_gate.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_worker.py' -v
git add backend/app/core/tool_health.py backend/app/services/worker.py backend/app/core/quality.py backend/tests/test_tool_health.py backend/tests/test_quality_gate.py backend/tests/test_worker.py
git commit -m "feat: report investigation capability limits"
```

Expected: availability impact is visible, but no tool absence proves a fact missing or changes completion logic.

## Task 4: Explicit Real Acceptance and Synthetic Regression Labels

**Files:**

- Modify: `scripts/regression_smoke.py`, `backend/tests/test_regression_smoke.py`
- Create: `scripts/real_acceptance.py`, `backend/tests/test_real_acceptance.py`
- Create: `backend/tests/fixtures/real_acceptance_manifest.example.json`, `docs/REAL_ACCEPTANCE_RUNBOOK.md`
- Modify: `docs/CAPABILITY_BASELINE_2026-07-07.md`

- [ ] **Step 1: Write failing labels and dry-run tests**

```python
self.assertEqual(result["suite_kind"], "synthetic_contract")
self.assertFalse(result["network_accessed"])

@patch("scripts.real_acceptance.urlopen")
def test_dry_run_validates_manifest_without_http(self, urlopen_mock):
    manifest = {"version": 1, "cases": [{
        "id": "example-domain", "seed_type": "domain", "seed_value": "example.invalid",
        "real_target": False, "minimum_evidence": ["official_website", "business_scope"],
    }]}
    result = run_acceptance_manifest(manifest, execute=False)
    self.assertFalse(result["executed"])
    self.assertFalse(result["benchmark_established"])
    urlopen_mock.assert_not_called()
```

Add validation tests for duplicate IDs, unsupported seed type, empty evidence, execution of a non-real fixture, and missing token. Add a mocked protocol test for POST investigation, POST run-jobs, and GET polling.

- [ ] **Step 2: Implement the guarded runner**

Make `run_regression_cases` add `suite_kind: "synthetic_contract"` and `network_accessed: False` only. Create `load_manifest`, `validate_manifest`, and `run_acceptance_manifest` in `scripts/real_acceptance.py`.

`validate_manifest` accepts only version 1, unique IDs, `domain`/`company`/`sparse_lead`, nonempty string name/seed, bool `real_target`, and nonempty string `minimum_evidence`. Default execution makes zero HTTP calls. `--execute` requires HTTPS or localhost HTTP base URL, bearer token from `--token-env`, and every case marked `real_target: true`; then it performs create, run-jobs, and bounded polling without mutation retries.

Return status counts, completion rate, manual-intervention rate, evidence-floor rate, identity-conflict rate, and `reviewed_false_conflict_rate`. Set the last metric to `null` without operator `reviewed_conflict_outcome` labels.

- [ ] **Step 3: Document, verify, and commit**

Create a schema-only fixture with `purpose: "schema_example_only"`, `example.invalid`, and `real_target: false`. The runbook requires authorized domain/company/sparse-lead cohorts before a real benchmark is claimed. Update the baseline to call the four-case smoke result synthetic.

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_regression_smoke.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_real_acceptance.py' -v
backend/.venv/bin/python scripts/regression_smoke.py
backend/.venv/bin/python scripts/real_acceptance.py --manifest backend/tests/fixtures/real_acceptance_manifest.example.json
git add scripts/regression_smoke.py scripts/real_acceptance.py backend/tests/test_regression_smoke.py backend/tests/test_real_acceptance.py backend/tests/fixtures/real_acceptance_manifest.example.json docs/REAL_ACCEPTANCE_RUNBOOK.md docs/CAPABILITY_BASELINE_2026-07-07.md
git commit -m "feat: add opt-in real acceptance harness"
```

Expected: synthetic results are labelled; example acceptance returns `executed: false` and `benchmark_established: false` without network access.

## Task 5: Full Verification and Scope Check

**Files:** all approved files; modify only for a failing test tied to this plan.

- [ ] **Step 1: Run the complete local suite**

```bash
bash scripts/verify.sh
```

Expected: backend discovery, synthetic regression, release checks, frontend helper checks, Vitest, and production build pass.

- [ ] **Step 2: Re-run high-risk contracts and review the diff**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_safe_http.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_tool_adapters.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_real_acceptance.py' -v
git diff --check
git status --short
```

Expected: no unapproved fake-IP fetch, no generic contact promoted to a role-linked contact, no dry-run network traffic, no N100 deployment, and no third-party tool installation.

## Plan Self-Review

- Task 1 implements exact-host reviewed fake-IP approvals and preserves default denial.
- Task 2 implements source-backed multilingual structural extraction and static contact classifications.
- Task 3 makes unavailable-tool coverage explicit without completion inflation.
- Task 4 separates synthetic contracts from real acceptance claims.
- Task 5 verifies the security, extraction, and no-deployment boundaries.
