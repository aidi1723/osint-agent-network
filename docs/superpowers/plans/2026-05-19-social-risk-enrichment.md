# Social Risk Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add public social-media enrichment for username/email investigations, with evidence-backed risk signals, total score, and category scores for manual risk review.

**Architecture:** Extend the current lightweight Python backend patterns: tool registry metadata, adapter classes, planner functions, and unit tests. New tools parse artifacts into the existing `ParsedToolOutput`, while risk modules consume normalized entities/evidence/relationships and produce deterministic review summaries.

**Tech Stack:** Python 3.11+, standard library parsing, existing `unittest` test style, existing CLI adapter flow in `app.agent_client`.

---

## File Structure

- Modify `backend/app/core/normalization.py`: accept `profile_url` targets with sanitized public HTTP(S) URLs.
- Modify `backend/app/core/registry.py`: register `maigret`, `socialscan`, and `profile_parser`.
- Modify `backend/app/core/planner.py`: plan initial and follow-up social enrichment jobs.
- Create `backend/app/core/social_risk.py`: identity grouping, risk signal extraction, category scoring, and report assembly.
- Modify `backend/app/tools/__init__.py`: expose new adapters through `get_adapter`.
- Create `backend/app/tools/maigret.py`: parse Maigret JSON output and build a command.
- Create `backend/app/tools/socialscan.py`: parse socialscan JSON output and build a command.
- Create `backend/app/tools/profile_parser.py`: parse saved public profile HTML/JSON artifacts.
- Modify `backend/app/agent_client.py`: allow new tool names in `run-tool` and default timeouts.
- Modify `backend/tests/test_core.py`: tests for normalization, registry, planner, and risk scoring.
- Modify `backend/tests/test_tool_adapters.py`: tests for Maigret, socialscan, and profile parser adapters.
- Modify `backend/tests/test_agent_client.py`: tests for new `run-tool` choices where needed.

## Task 1: Normalize Profile URLs

**Files:**
- Modify: `backend/app/core/normalization.py`
- Test: `backend/tests/test_core.py`

- [ ] **Step 1: Add failing tests for profile URL normalization**

Add these tests to `NormalizationTests` in `backend/tests/test_core.py`:

```python
    def test_normalizes_public_profile_urls(self):
        self.assertEqual(
            normalize_target("profile_url", " https://github.com/Admin?tab=repositories "),
            "https://github.com/Admin",
        )
        self.assertEqual(
            normalize_target("url", "https://example.com/path?utm_source=test"),
            "https://example.com/path",
        )

    def test_rejects_private_or_non_http_profile_urls(self):
        with self.assertRaises(NormalizationError):
            normalize_target("profile_url", "javascript:alert(1)")
        with self.assertRaises(NormalizationError):
            normalize_target("profile_url", "http://localhost/admin")
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `python -m pytest backend/tests/test_core.py::NormalizationTests -v`

Expected: fails because `profile_url` and `url` are unsupported or not sanitized.

- [ ] **Step 3: Implement URL normalization**

Update `backend/app/core/normalization.py`:

```python
from urllib.parse import urlsplit, urlunsplit
```

Add this helper near the regex definitions:

```python
_PRIVATE_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
```

Add this branch before the final unsupported-target branch:

```python
    if target_type in {"url", "profile_url"}:
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise NormalizationError(f"invalid {target_type}: {value}")
        hostname = (parsed.hostname or "").lower()
        if hostname in _PRIVATE_HOSTS or hostname.endswith(".local"):
            raise NormalizationError(f"private {target_type}: {value}")
        path = parsed.path or ""
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))
```

- [ ] **Step 4: Run the tests and verify pass**

Run: `python -m pytest backend/tests/test_core.py::NormalizationTests -v`

Expected: all normalization tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/app/core/normalization.py backend/tests/test_core.py
git commit -m "feat: normalize public profile urls"
```

## Task 2: Register Social Enrichment Tools

**Files:**
- Modify: `backend/app/core/registry.py`
- Test: `backend/tests/test_core.py`

- [ ] **Step 1: Add failing registry tests**

Add this test to `RegistryTests` in `backend/tests/test_core.py`:

```python
    def test_registry_selects_social_enrichment_tools(self):
        registry = default_tool_registry()

        username_tools = {tool.name for tool in registry.accepting("username")}
        email_tools = {tool.name for tool in registry.accepting("email")}
        profile_tools = {tool.name for tool in registry.accepting("profile_url")}

        self.assertIn("maigret", username_tools)
        self.assertIn("socialscan", username_tools)
        self.assertIn("socialscan", email_tools)
        self.assertIn("profile_parser", profile_tools)
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `python -m pytest backend/tests/test_core.py::RegistryTests -v`

Expected: fails because the new tools are not registered.

- [ ] **Step 3: Add tool definitions**

Append these `ToolDefinition` entries in `default_tool_registry()` after `sherlock` and before `theharvester`:

```python
            ToolDefinition(
                name="maigret",
                display_name="Maigret",
                execution_mode="sync_cli",
                accepts=("username",),
                produces=(
                    "social_profile",
                    "profile_url",
                    "platform_account",
                    "bio_snippet",
                    "profile_image_url",
                    "declared_location",
                    "external_link",
                ),
                requires_credentials=False,
                default_timeout_seconds=300,
                base_confidence=0.40,
            ),
            ToolDefinition(
                name="socialscan",
                display_name="socialscan",
                execution_mode="sync_cli",
                accepts=("email", "username"),
                produces=("platform_account", "social_profile", "negative_result"),
                requires_credentials=False,
                default_timeout_seconds=120,
                base_confidence=0.35,
            ),
            ToolDefinition(
                name="profile_parser",
                display_name="Public Profile Parser",
                execution_mode="artifact_parser",
                accepts=("profile_url",),
                produces=(
                    "bio_snippet",
                    "profile_image_url",
                    "declared_location",
                    "external_link",
                    "interest_tag",
                    "age_claim",
                ),
                requires_credentials=False,
                default_timeout_seconds=60,
                base_confidence=0.25,
            ),
```

- [ ] **Step 4: Run registry tests**

Run: `python -m pytest backend/tests/test_core.py::RegistryTests -v`

Expected: all registry tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/app/core/registry.py backend/tests/test_core.py
git commit -m "feat: register social enrichment tools"
```

## Task 3: Plan Social Enrichment Jobs

**Files:**
- Modify: `backend/app/core/planner.py`
- Test: `backend/tests/test_core.py`

- [ ] **Step 1: Add failing planner tests**

Add these tests to `PlannerTests` in `backend/tests/test_core.py`:

```python
    def test_initial_username_strategy_queues_sherlock_and_maigret(self):
        registry = default_tool_registry()
        jobs = plan_initial_jobs(
            seed_type="username",
            seed_value="Admin_007",
            strategy=StrategyProfile.standard(),
            registry=registry,
        )

        planned_tools = {job.tool_name for job in jobs}
        self.assertIn("sherlock", planned_tools)
        self.assertIn("maigret", planned_tools)
        self.assertIn("socialscan", planned_tools)

    def test_initial_email_strategy_queues_socialscan_ghunt_and_username_tools(self):
        registry = default_tool_registry()
        jobs = plan_initial_jobs(
            seed_type="email",
            seed_value="Admin@example.com",
            strategy=StrategyProfile.standard(),
            registry=registry,
        )

        job_keys = {(job.tool_name, job.target_type, job.target_value) for job in jobs}
        self.assertIn(("socialscan", "email", "admin@example.com"), job_keys)
        self.assertIn(("sherlock", "username", "admin"), job_keys)
        self.assertIn(("maigret", "username", "admin"), job_keys)

    def test_profile_url_followup_queues_profile_parser(self):
        registry = default_tool_registry()
        jobs = plan_followup_jobs(
            entity_type="profile_url",
            entity_value="https://github.com/admin?tab=repositories",
            depth=0,
            strategy=StrategyProfile.standard(),
            registry=registry,
            already_planned=set(),
        )

        self.assertEqual(
            {(job.tool_name, job.target_type, job.target_value) for job in jobs},
            {("profile_parser", "profile_url", "https://github.com/admin")},
        )
```

- [ ] **Step 2: Run planner tests and verify failure**

Run: `python -m pytest backend/tests/test_core.py::PlannerTests -v`

Expected: email and profile URL planning tests fail because planner does not derive these jobs yet.

- [ ] **Step 3: Extend initial planning**

Update `plan_initial_jobs()` in `backend/app/core/planner.py` so it builds a candidate list:

```python
    candidates = [(seed_type, target_value)]
    if seed_type == "email":
        local, _domain = target_value.split("@", 1)
        candidates.append(("username", normalize_target("username", local)))

    jobs = []
    for candidate_type, candidate_value in candidates:
        for tool in registry.accepting(candidate_type):
            jobs.append(
                PlannedJob(
                    tool_name=tool.name,
                    target_type=candidate_type,
                    target_value=candidate_value,
                    depth=0,
                )
            )
```

Keep the existing quick strategy filter after the new `jobs` list is built.

- [ ] **Step 4: Extend follow-up planning**

Add this branch in `plan_followup_jobs()` after the username branch:

```python
    elif entity_type == "profile_url":
        candidates.append(("profile_url", normalized))
```

This uses `normalize_target("profile_url", ...)` from Task 1.

- [ ] **Step 5: Run planner tests**

Run: `python -m pytest backend/tests/test_core.py::PlannerTests -v`

Expected: all planner tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/app/core/planner.py backend/tests/test_core.py
git commit -m "feat: plan social enrichment jobs"
```

## Task 4: Add Maigret Adapter

**Files:**
- Create: `backend/app/tools/maigret.py`
- Modify: `backend/app/tools/__init__.py`
- Modify: `backend/app/agent_client.py`
- Test: `backend/tests/test_tool_adapters.py`

- [ ] **Step 1: Add failing Maigret adapter tests**

Add imports in `backend/tests/test_tool_adapters.py`:

```python
from app.tools.maigret import MaigretAdapter
```

Add this test class:

```python
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
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest backend/tests/test_tool_adapters.py::MaigretAdapterTests -v`

Expected: import fails because `app.tools.maigret` does not exist.

- [ ] **Step 3: Implement MaigretAdapter**

Create `backend/app/tools/maigret.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

from app.core.normalization import normalize_target
from app.tools.base import (
    NormalizedEntity,
    NormalizedEvidence,
    NormalizedRelationship,
    ParsedToolOutput,
    ToolCommand,
    append_unique_entity,
    append_unique_evidence,
    append_unique_relationship,
    read_json_artifact,
)


class MaigretAdapter:
    name = "maigret"
    target_type = "username"
    base_confidence = 0.40

    def __init__(self, command: str | None = None):
        self.command = command or os.getenv("MAIGRET_COMMAND", "maigret")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != self.target_type:
            raise ValueError("Maigret only accepts username targets")
        return normalize_target("username", target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 300,
    ) -> ToolCommand:
        username = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / f"maigret_{username}.json"
        return ToolCommand(
            args=[self.command, username, "--json", str(artifact), "--timeout", str(timeout_seconds)],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        return self.parse_json(read_json_artifact(artifact_path), username=target_value)

    def parse_json(self, raw: dict, username: str) -> ParsedToolOutput:
        normalized_username = normalize_target("username", username)
        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        append_unique_entity(
            entities,
            seen_entities,
            NormalizedEntity("username", normalized_username, self.name, self.base_confidence),
        )

        records = raw.get("sites", raw) if isinstance(raw, dict) else {}
        for platform, item in records.items():
            if not isinstance(item, dict) or not _is_claimed(item):
                continue
            url = str(item.get("url_user") or item.get("url") or item.get("profile_url") or "").strip()
            if not url:
                continue
            try:
                profile_url = normalize_target("profile_url", url)
            except ValueError:
                continue
            platform_key = str(platform).strip().lower().replace(" ", "_")
            social_profile = f"{platform_key}:{normalized_username}"
            ids_data = item.get("ids_data") if isinstance(item.get("ids_data"), dict) else {}

            for entity in [
                NormalizedEntity("profile_url", profile_url, self.name, self.base_confidence),
                NormalizedEntity("social_profile", social_profile, self.name, self.base_confidence),
                NormalizedEntity("platform_account", social_profile, self.name, self.base_confidence),
            ]:
                append_unique_entity(entities, seen_entities, entity)

            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(profile_url, "social_profile_exists", self.name, f"Maigret found claimed profile on {platform}"),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(normalized_username, profile_url, "username_has_social_profile", self.base_confidence),
            )

            _add_metadata_entities(
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
                profile_url,
                ids_data,
                self.name,
            )

        return ParsedToolOutput(self.name, self.target_type, normalized_username, entities, evidence, relationships)


def _is_claimed(item: dict) -> bool:
    status = str(item.get("status") or item.get("status_code") or "").lower()
    return status in {"claimed", "found", "exists"} or item.get("claimed") is True or item.get("exists") is True


def _add_metadata_entities(entities, evidence, relationships, seen_entities, seen_evidence, seen_relationships, profile_url, ids_data, source):
    mappings = [
        ("bio_snippet", ids_data.get("bio") or ids_data.get("description")),
        ("declared_location", ids_data.get("location")),
        ("profile_image_url", ids_data.get("avatar") or ids_data.get("image")),
        ("external_link", ids_data.get("website") or ids_data.get("url")),
    ]
    for entity_type, raw_value in mappings:
        value = str(raw_value or "").strip()
        if not value:
            continue
        if entity_type in {"profile_image_url", "external_link"}:
            try:
                value = normalize_target("url", value)
            except ValueError:
                continue
        append_unique_entity(entities, seen_entities, NormalizedEntity(entity_type, value, source, 0.30))
        append_unique_evidence(
            evidence,
            seen_evidence,
            NormalizedEvidence(value, "public_profile_metadata", source, f"Public profile metadata from {profile_url}"),
        )
        append_unique_relationship(
            relationships,
            seen_relationships,
            NormalizedRelationship(profile_url, value, f"profile_has_{entity_type}", 0.30),
        )
```

- [ ] **Step 4: Register adapter and CLI choice**

Modify `backend/app/tools/__init__.py`:

```python
from app.tools.maigret import MaigretAdapter
```

Add `"maigret": MaigretAdapter,` to the `adapters` dict.

Modify `backend/app/agent_client.py`:

- Add `"maigret"` to `DEFAULT_CAPABILITIES`.
- Add `"maigret"` to the `run_tool.add_argument(... choices=[...])` list.
- Add `"maigret": 300,` to `_default_timeout()`.

- [ ] **Step 5: Run Maigret tests**

Run: `python -m pytest backend/tests/test_tool_adapters.py::MaigretAdapterTests -v`

Expected: tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/app/tools/maigret.py backend/app/tools/__init__.py backend/app/agent_client.py backend/tests/test_tool_adapters.py
git commit -m "feat: add maigret adapter"
```

## Task 5: Add socialscan Adapter

**Files:**
- Create: `backend/app/tools/socialscan.py`
- Modify: `backend/app/tools/__init__.py`
- Modify: `backend/app/agent_client.py`
- Test: `backend/tests/test_tool_adapters.py`

- [ ] **Step 1: Add failing socialscan tests**

Add import:

```python
from app.tools.socialscan import SocialScanAdapter
```

Add test class:

```python
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
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest backend/tests/test_tool_adapters.py::SocialScanAdapterTests -v`

Expected: import fails because adapter does not exist.

- [ ] **Step 3: Implement SocialScanAdapter**

Create `backend/app/tools/socialscan.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

from app.core.normalization import normalize_target
from app.tools.base import (
    NormalizedEntity,
    NormalizedEvidence,
    NormalizedRelationship,
    ParsedToolOutput,
    ToolCommand,
    append_unique_entity,
    append_unique_evidence,
    append_unique_relationship,
    read_json_artifact,
)


class SocialScanAdapter:
    name = "socialscan"
    base_confidence = 0.35

    def __init__(self, command: str | None = None):
        self.command = command or os.getenv("SOCIALSCAN_COMMAND", "socialscan")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type not in {"email", "username"}:
            raise ValueError("socialscan accepts email or username targets")
        return normalize_target(target_type, target_value)

    def build_command(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int = 120) -> ToolCommand:
        target = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / f"socialscan_{target_type}_{target.replace('@', '_at_')}.json"
        return ToolCommand(
            args=[self.command, "--json", target],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        target_type = "email" if "@" in target_value else "username"
        return self.parse_json(read_json_artifact(artifact_path), target_type=target_type, target_value=target_value)

    def parse_json(self, raw, target_type: str, target_value: str) -> ParsedToolOutput:
        normalized_target = self.validate_target(target_type, target_value)
        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        append_unique_entity(entities, seen_entities, NormalizedEntity(target_type, normalized_target, self.name, self.base_confidence))

        records = raw.get("results", raw) if isinstance(raw, dict) else raw
        if not isinstance(records, list):
            records = []

        for record in records:
            if not isinstance(record, dict):
                continue
            platform = str(record.get("platform") or record.get("site") or "").strip().lower()
            if not platform:
                continue
            account_key = f"{platform}:{normalized_target}"
            exists = record.get("exists")
            if exists is False or str(record.get("status", "")).lower() in {"not_found", "available", "missing"}:
                append_unique_evidence(
                    evidence,
                    seen_evidence,
                    NormalizedEvidence(account_key, "negative_result", self.name, str(record.get("message") or f"{platform} account not found")),
                )
                continue

            url = str(record.get("url") or record.get("profile_url") or "").strip()
            if not url:
                append_unique_entity(entities, seen_entities, NormalizedEntity("platform_account", account_key, self.name, self.base_confidence))
                append_unique_evidence(evidence, seen_evidence, NormalizedEvidence(account_key, "account_exists", self.name, f"socialscan found {platform} account signal"))
                continue
            try:
                profile_url = normalize_target("profile_url", url)
            except ValueError:
                continue
            append_unique_entity(entities, seen_entities, NormalizedEntity("profile_url", profile_url, self.name, self.base_confidence))
            append_unique_entity(entities, seen_entities, NormalizedEntity("platform_account", account_key, self.name, self.base_confidence))
            append_unique_evidence(evidence, seen_evidence, NormalizedEvidence(profile_url, "account_exists", self.name, f"socialscan found {platform} account signal"))
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(normalized_target, profile_url, f"{target_type}_linked_to_social_profile", self.base_confidence),
            )

        return ParsedToolOutput(self.name, target_type, normalized_target, entities, evidence, relationships)
```

- [ ] **Step 4: Register adapter and CLI choice**

Modify `backend/app/tools/__init__.py`:

```python
from app.tools.socialscan import SocialScanAdapter
```

Add `"socialscan": SocialScanAdapter,` to the `adapters` dict.

Modify `backend/app/agent_client.py`:

- Add `"socialscan"` to `DEFAULT_CAPABILITIES`.
- Add `"socialscan"` to the `run_tool` choices.
- Add `"socialscan": 120,` to `_default_timeout()`.

- [ ] **Step 5: Run socialscan tests**

Run: `python -m pytest backend/tests/test_tool_adapters.py::SocialScanAdapterTests -v`

Expected: tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/app/tools/socialscan.py backend/app/tools/__init__.py backend/app/agent_client.py backend/tests/test_tool_adapters.py
git commit -m "feat: add socialscan adapter"
```

## Task 6: Add Profile Parser Adapter

**Files:**
- Create: `backend/app/tools/profile_parser.py`
- Modify: `backend/app/tools/__init__.py`
- Modify: `backend/app/agent_client.py`
- Test: `backend/tests/test_tool_adapters.py`

- [ ] **Step 1: Add failing profile parser test**

Add import:

```python
from app.tools.profile_parser import ProfileParserAdapter
```

Add test class:

```python
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
```

- [ ] **Step 2: Run test and verify failure**

Run: `python -m pytest backend/tests/test_tool_adapters.py::ProfileParserAdapterTests -v`

Expected: import fails because adapter does not exist.

- [ ] **Step 3: Implement ProfileParserAdapter**

Create `backend/app/tools/profile_parser.py`:

```python
from __future__ import annotations

from html.parser import HTMLParser
import os
from pathlib import Path
import re

from app.core.normalization import normalize_target
from app.tools.base import (
    NormalizedEntity,
    NormalizedEvidence,
    NormalizedRelationship,
    ParsedToolOutput,
    ToolCommand,
    append_unique_entity,
    append_unique_evidence,
    append_unique_relationship,
)


INTEREST_KEYWORDS = ("fintech", "crypto", "runner", "builder", "trader", "import", "export")


class ProfileParserAdapter:
    name = "profile_parser"
    target_type = "profile_url"
    base_confidence = 0.25

    def __init__(self, command: str | None = None):
        self.command = command or os.getenv("PROFILE_PARSER_COMMAND", "profile-parser")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != self.target_type:
            raise ValueError("profile_parser only accepts profile_url targets")
        return normalize_target("profile_url", target_value)

    def build_command(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int = 60) -> ToolCommand:
        profile_url = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / "profile_parser_input.html"
        return ToolCommand(
            args=["PARSE_ARTIFACT", profile_url],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        return self.parse_html(artifact_path.read_text(encoding="utf-8"), profile_url=target_value)

    def parse_html(self, html: str, profile_url: str) -> ParsedToolOutput:
        normalized_url = normalize_target("profile_url", profile_url)
        parser = _ProfileHTMLParser()
        parser.feed(html)

        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        append_unique_entity(entities, seen_entities, NormalizedEntity("profile_url", normalized_url, self.name, self.base_confidence))

        bio = parser.meta.get("og:description") or parser.meta.get("description") or ""
        image = parser.meta.get("og:image") or parser.meta.get("twitter:image") or ""
        location = parser.location_text

        _add_value("bio_snippet", bio, normalized_url, entities, evidence, relationships, seen_entities, seen_evidence, seen_relationships)
        _add_url_value("profile_image_url", image, normalized_url, entities, evidence, relationships, seen_entities, seen_evidence, seen_relationships)
        _add_value("declared_location", location, normalized_url, entities, evidence, relationships, seen_entities, seen_evidence, seen_relationships, relationship_type="profile_declares_location")

        for link in parser.links:
            _add_url_value("external_link", link, normalized_url, entities, evidence, relationships, seen_entities, seen_evidence, seen_relationships)

        combined_text = " ".join([bio, parser.title, location]).lower()
        for keyword in INTEREST_KEYWORDS:
            if re.search(rf"\b{re.escape(keyword)}\b", combined_text):
                _add_value("interest_tag", keyword, normalized_url, entities, evidence, relationships, seen_entities, seen_evidence, seen_relationships, relationship_type="profile_mentions_interest")

        return ParsedToolOutput(self.name, self.target_type, normalized_url, entities, evidence, relationships)


class _ProfileHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta: dict[str, str] = {}
        self.links: list[str] = []
        self.title = ""
        self.location_text = ""
        self._in_title = False
        self._capture_location = False

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "meta":
            key = attr.get("property") or attr.get("name")
            content = attr.get("content")
            if key and content:
                self.meta[key] = content.strip()
        if tag == "a" and attr.get("href"):
            self.links.append(attr["href"].strip())
        if tag == "title":
            self._in_title = True
        if "location" in (attr.get("class") or "").lower():
            self._capture_location = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if self._capture_location and tag in {"span", "div", "p"}:
            self._capture_location = False

    def handle_data(self, data):
        value = data.strip()
        if not value:
            return
        if self._in_title:
            self.title = value
        if self._capture_location:
            self.location_text = value


def _add_value(entity_type, value, profile_url, entities, evidence, relationships, seen_entities, seen_evidence, seen_relationships, relationship_type=None):
    value = str(value or "").strip()
    if not value:
        return
    append_unique_entity(entities, seen_entities, NormalizedEntity(entity_type, value, "profile_parser", 0.25))
    append_unique_evidence(evidence, seen_evidence, NormalizedEvidence(value, "public_profile_metadata", "profile_parser", f"Public profile metadata from {profile_url}"))
    append_unique_relationship(relationships, seen_relationships, NormalizedRelationship(profile_url, value, relationship_type or f"profile_has_{entity_type}", 0.25))


def _add_url_value(entity_type, value, profile_url, entities, evidence, relationships, seen_entities, seen_evidence, seen_relationships):
    value = str(value or "").strip()
    if not value:
        return
    try:
        normalized = normalize_target("url", value)
    except ValueError:
        return
    _add_value(entity_type, normalized, profile_url, entities, evidence, relationships, seen_entities, seen_evidence, seen_relationships)
```

- [ ] **Step 4: Register adapter and CLI choice**

Modify `backend/app/tools/__init__.py`:

```python
from app.tools.profile_parser import ProfileParserAdapter
```

Add `"profile_parser": ProfileParserAdapter,` to the adapters dict.

Modify `backend/app/agent_client.py`:

- Add `"profile_parser"` to `DEFAULT_CAPABILITIES`.
- Add `"profile_parser"` to `run_tool` choices.
- Add `"profile_parser": 60,` to `_default_timeout()`.

- [ ] **Step 5: Run profile parser tests**

Run: `python -m pytest backend/tests/test_tool_adapters.py::ProfileParserAdapterTests -v`

Expected: tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/app/tools/profile_parser.py backend/app/tools/__init__.py backend/app/agent_client.py backend/tests/test_tool_adapters.py
git commit -m "feat: add public profile parser"
```

## Task 7: Add Social Risk Engine

**Files:**
- Create: `backend/app/core/social_risk.py`
- Test: `backend/tests/test_core.py`

- [ ] **Step 1: Add failing risk engine tests**

Add import:

```python
from app.core.social_risk import (
    SocialRiskEvidence,
    build_social_risk_report,
)
```

Add test class:

```python
class SocialRiskTests(unittest.TestCase):
    def test_builds_category_scores_and_top_signals(self):
        report = build_social_risk_report(
            entities=[
                {"type": "profile_url", "value": "https://github.com/admin", "source_tool": "maigret", "confidence": 0.4},
                {"type": "profile_url", "value": "https://x.com/admin", "source_tool": "sherlock", "confidence": 0.35},
                {"type": "declared_location", "value": "Singapore", "source_tool": "profile_parser", "confidence": 0.25},
                {"type": "bio_snippet", "value": "crypto betting operator", "source_tool": "profile_parser", "confidence": 0.25},
            ],
            evidence=[
                {"entity_value": "https://github.com/admin", "evidence_kind": "social_profile_exists", "source_tool": "maigret"},
                {"entity_value": "crypto betting operator", "evidence_kind": "public_profile_metadata", "source_tool": "profile_parser"},
            ],
            relationships=[
                {"from_value": "admin", "to_value": "https://github.com/admin", "relationship_type": "username_has_social_profile"},
                {"from_value": "admin", "to_value": "https://x.com/admin", "relationship_type": "username_has_social_profile"},
            ],
            declared_region="Hong Kong",
        )

        self.assertGreaterEqual(report["overall_risk_score"], 25)
        self.assertIn("business_content_risk", report["category_scores"])
        self.assertTrue(report["review_required"])
        self.assertTrue(any(signal["kind"] == "business_risk_keyword" for signal in report["top_risk_signals"]))
        self.assertTrue(any(signal["kind"] == "location_conflict" for signal in report["top_risk_signals"]))

    def test_weak_public_footprint_raises_uncertainty(self):
        report = build_social_risk_report(
            entities=[{"type": "email", "value": "admin@example.com", "source_tool": "socialscan", "confidence": 0.35}],
            evidence=[],
            relationships=[],
        )

        self.assertGreaterEqual(report["category_scores"]["evidence_uncertainty"], 50)
        self.assertTrue(any(signal["kind"] == "weak_public_footprint" for signal in report["top_risk_signals"]))
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest backend/tests/test_core.py::SocialRiskTests -v`

Expected: import fails because `social_risk.py` does not exist.

- [ ] **Step 3: Implement social risk engine**

Create `backend/app/core/social_risk.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass


HIGH_RISK_KEYWORDS = ("crypto", "betting", "casino", "gambling", "forex", "loan", "pharma")


@dataclass(frozen=True)
class SocialRiskEvidence:
    kind: str
    severity: str
    summary: str
    evidence_values: list[str]


def build_social_risk_report(
    entities: list[dict],
    evidence: list[dict],
    relationships: list[dict],
    declared_region: str = "",
) -> dict:
    signals = extract_risk_signals(entities, evidence, relationships, declared_region=declared_region)
    category_scores = score_categories(entities, evidence, relationships, signals)
    overall = round(
        category_scores["identity_consistency"] * 0.20
        + category_scores["contact_reputation"] * 0.20
        + category_scores["location_consistency"] * 0.20
        + category_scores["business_content_risk"] * 0.25
        + category_scores["evidence_uncertainty"] * 0.15
    )
    return {
        "overall_risk_score": overall,
        "overall_risk_level": _risk_level(overall),
        "category_scores": category_scores,
        "review_required": overall >= 25 or any(signal.severity in {"high", "critical"} for signal in signals),
        "top_risk_signals": [asdict(signal) for signal in signals[:5]],
        "public_profile_summary": _profile_summary(entities),
        "supporting_evidence": evidence,
    }


def extract_risk_signals(entities: list[dict], evidence: list[dict], relationships: list[dict], declared_region: str = "") -> list[SocialRiskEvidence]:
    signals: list[SocialRiskEvidence] = []
    profiles = [item["value"] for item in entities if item.get("type") == "profile_url"]
    bio_values = [item["value"] for item in entities if item.get("type") == "bio_snippet"]
    locations = [item["value"] for item in entities if item.get("type") == "declared_location"]

    if len(profiles) == 0:
        signals.append(SocialRiskEvidence("weak_public_footprint", "medium", "No public social profiles were found from the supplied identifiers.", []))
    elif len(profiles) == 1:
        signals.append(SocialRiskEvidence("low_evidence_strength", "low", "Only one public profile source supports the social footprint.", profiles))

    for bio in bio_values:
        lowered = bio.lower()
        hits = [keyword for keyword in HIGH_RISK_KEYWORDS if keyword in lowered]
        if hits:
            signals.append(
                SocialRiskEvidence(
                    "business_risk_keyword",
                    "high",
                    f"Public profile text contains configured risk keywords: {', '.join(hits)}.",
                    [bio],
                )
            )
            break

    if declared_region:
        normalized_declared = declared_region.strip().lower()
        conflicting = [location for location in locations if normalized_declared and normalized_declared not in location.lower()]
        if conflicting:
            signals.append(
                SocialRiskEvidence(
                    "location_conflict",
                    "medium",
                    "Public declared location differs from the customer-declared region.",
                    conflicting,
                )
            )

    linked_targets = {}
    for relationship in relationships:
        if relationship.get("relationship_type") in {"username_has_social_profile", "email_linked_to_social_profile"}:
            linked_targets.setdefault(relationship.get("from_value", ""), set()).add(relationship.get("to_value", ""))
    if any(len(values) >= 5 for values in linked_targets.values()):
        signals.append(SocialRiskEvidence("contact_identity_overlap", "medium", "One identifier links to many public profiles and needs review.", []))

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(signals, key=lambda signal: severity_order[signal.severity])


def score_categories(entities: list[dict], evidence: list[dict], relationships: list[dict], signals: list[SocialRiskEvidence]) -> dict:
    signal_kinds = {signal.kind for signal in signals}
    source_tools = {item.get("source_tool") for item in evidence if item.get("source_tool")}
    profile_count = sum(1 for item in entities if item.get("type") == "profile_url")

    return {
        "identity_consistency": _score_from_signals(signal_kinds, {"contact_identity_overlap": 55}, default=15),
        "contact_reputation": 65 if "weak_public_footprint" in signal_kinds else 20 if profile_count >= 2 else 35,
        "location_consistency": 60 if "location_conflict" in signal_kinds else 10,
        "business_content_risk": 75 if "business_risk_keyword" in signal_kinds else 10,
        "evidence_uncertainty": 70 if profile_count == 0 else 45 if len(source_tools) <= 1 else 20,
    }


def _score_from_signals(signal_kinds: set[str], weights: dict[str, int], default: int) -> int:
    score = default
    for kind, value in weights.items():
        if kind in signal_kinds:
            score = max(score, value)
    return score


def _risk_level(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _profile_summary(entities: list[dict]) -> dict:
    def values(entity_type: str) -> list[str]:
        seen = []
        for item in entities:
            if item.get("type") == entity_type and item.get("value") not in seen:
                seen.append(item.get("value"))
        return seen

    return {
        "profiles": values("profile_url"),
        "declared_locations": values("declared_location"),
        "likely_activity_regions": values("likely_activity_region"),
        "profile_image_urls": values("profile_image_url"),
        "bio_snippets": values("bio_snippet"),
        "interest_tags": values("interest_tag"),
        "age_claims": values("age_claim"),
    }
```

- [ ] **Step 4: Run risk tests**

Run: `python -m pytest backend/tests/test_core.py::SocialRiskTests -v`

Expected: tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/app/core/social_risk.py backend/tests/test_core.py
git commit -m "feat: add social risk scoring"
```

## Task 8: Add Agent CLI Risk Report Command

**Files:**
- Modify: `backend/app/agent_client.py`
- Test: `backend/tests/test_agent_client.py`

- [ ] **Step 1: Inspect current agent client tests**

Run: `sed -n '1,260p' backend/tests/test_agent_client.py`

Use the existing fake `post_json_fn` pattern in this file.

- [ ] **Step 2: Add failing CLI test**

Add a test that builds a risk report from JSON files:

```python
def test_risk_report_command_reads_investigation_artifact():
    with tempfile.TemporaryDirectory() as tmpdir:
        artifact = Path(tmpdir) / "investigation.json"
        artifact.write_text(
            json.dumps(
                {
                    "entities": [
                        {"type": "profile_url", "value": "https://github.com/admin", "source_tool": "maigret", "confidence": 0.4},
                        {"type": "bio_snippet", "value": "crypto betting operator", "source_tool": "profile_parser", "confidence": 0.25},
                    ],
                    "evidence": [
                        {"entity_value": "https://github.com/admin", "evidence_kind": "social_profile_exists", "source_tool": "maigret"}
                    ],
                    "relationships": [],
                }
            ),
            encoding="utf-8",
        )

        result = dispatch(
            argparse.Namespace(
                command="risk-report",
                input_file=str(artifact),
                declared_region="Hong Kong",
            ),
            token="",
            post_json_fn=lambda *_args: {},
        )

    self.assertIn("overall_risk_score", result)
    self.assertIn("category_scores", result)
```

If the file does not currently import `argparse`, `json`, `tempfile`, or `Path`, add those imports.

- [ ] **Step 3: Run test and verify failure**

Run: `python -m pytest backend/tests/test_agent_client.py -v`

Expected: fails because `risk-report` is not a parser command or dispatch branch.

- [ ] **Step 4: Add parser command**

In `build_parser()` in `backend/app/agent_client.py`, add:

```python
    risk_report = subparsers.add_parser("risk-report", help="根据调查详情 JSON 生成社媒风险评分")
    risk_report.add_argument("--input-file", required=True)
    risk_report.add_argument("--declared-region", default="")
```

Import risk report builder:

```python
from app.core.social_risk import build_social_risk_report
```

Add dispatch branch before unsupported command:

```python
    if args.command == "risk-report":
        payload = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
        return build_social_risk_report(
            entities=payload.get("entities", []),
            evidence=payload.get("evidence", []),
            relationships=payload.get("relationships", []),
            declared_region=args.declared_region,
        )
```

- [ ] **Step 5: Run agent client tests**

Run: `python -m pytest backend/tests/test_agent_client.py -v`

Expected: tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/app/agent_client.py backend/tests/test_agent_client.py
git commit -m "feat: add social risk report cli"
```

## Task 9: Run Full Backend Verification

**Files:**
- No code changes unless verification exposes failures.

- [ ] **Step 1: Run all backend tests**

Run: `python -m pytest backend/tests -v`

Expected: all tests pass.

- [ ] **Step 2: Run smoke checks for adapter dry runs with sample artifacts**

Create temporary sample artifacts under `/tmp` manually or reuse test fixtures if added during tasks.

Run examples:

```bash
python -m app.agent_client run-tool --tool maigret --target-type username --target admin --input-file /tmp/maigret.json --dry-run
python -m app.agent_client run-tool --tool socialscan --target-type email --target admin@example.com --input-file /tmp/socialscan.json --dry-run
python -m app.agent_client run-tool --tool profile_parser --target-type profile_url --target https://github.com/admin --input-file /tmp/profile.html --dry-run
```

Expected: each command prints JSON with `counts` and `posted` fields.

- [ ] **Step 3: Check docs for stale references**

Run: `rg -n "maigret|socialscan|profile_parser|risk-report" README.md docs backend/app backend/tests`

Expected: new tool names appear in implementation and relevant docs.

- [ ] **Step 4: Commit verification fixes if needed**

If any verification-only fixes are required:

```bash
git add <changed-files>
git commit -m "test: verify social risk enrichment"
```

## Self-Review Checklist

- Spec coverage: adapter additions, planner changes, risk categories, evidence-backed output, CLI report generation, and validation are covered.
- Safety boundaries: private scraping, deep crawling, face recognition, precise residence, and automatic blocking are not implemented.
- No live network required for tests: parser tests use JSON/HTML fixtures.
- Existing behavior preserved: existing seven tool adapters and Agent API remain compatible.
