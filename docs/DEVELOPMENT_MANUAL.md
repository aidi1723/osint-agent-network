# OSINT Agent Network Development Manual

Version: 0.1
Date: 2026-05-19
Deployment target: `/opt/osint-agent-network` on `<production-host>`

> Current implementation note, 2026-07-07: this manual preserves the original
> architecture plan and target shape. The current running implementation uses a
> lightweight Python `http.server` API, SQLite store, SQLite-backed recoverable
> background worker queue, React + TypeScript + Vite frontend, local
> role-agent orchestration, external Agent write-back, gap-to-tool follow-up
> planning, completion policy, and source-backed cross-verification. For
> runbooks and current protocol details, use `README.md`,
> `docs/STAGE_CLOSURE_2026-07-07.md`, `docs/PROJECT_PACKAGE.md`,
> `docs/AGENT_PROTOCOL.md`, `docs/ORCHESTRATION_MODEL.md`, and
> `docs/GRAPH_TEMPLATE.md` as the source of truth.

## 1. Product Positioning

OSINT Agent Network is a high-recall intelligence workbench for authorized, self-operated research. Its goal is to collect as much relevant public-source intelligence as possible, normalize outputs from heterogeneous OSINT tools, and cross-verify entities across sources before presenting evidence chains to an operator.

The system is not a thin wrapper around seven tools. It is a tool orchestration, evidence normalization, recursive enrichment, and confidence-scoring platform.

Primary goals:

- Maximize discovery breadth across domains, usernames, emails, phones, subdomains, IPs, and platform footprints.
- Preserve raw evidence while feeding only normalized, trimmed observations to the agent layer.
- Run long tasks asynchronously with status, logs, partial results, cancellation, and retry controls.
- Support recursive enrichment with configurable depth, entity budget, and tool budget.
- Cross-verify entities using weighted evidence rather than trusting a single tool output.
- Provide a web management interface for task creation, live status, findings review, evidence chains, tool health, and configuration.

Non-goals for the first implementation:

- No offensive exploitation, credential attacks, bypass logic, account takeover logic, or stealth evasion.
- No automatic purchase or harvesting of API credentials.
- No deep graph database dependency in MVP; relational tables plus derived graph JSON are enough.

## 2. Architecture Overview

The first version uses a monorepo-style project with backend, frontend, deployment, and tool adapter code in one folder.

Recommended stack:

- Backend: Python 3.11+, FastAPI, SQLAlchemy, Pydantic, SQLite for MVP.
- Background jobs: local worker loop with DB-backed task table for MVP; interface must allow future Redis/Celery migration.
- Frontend: React, TypeScript, Vite, Tailwind, shadcn/ui-style source-owned components.
- Deployment: Docker Compose on <production-host>.
- Tool execution: subprocess wrappers for CLI tools, HTTP clients for REST tools, Docker-compatible command paths.

Main runtime services:

- `api`: FastAPI app, REST endpoints, validation, orchestration.
- `worker`: background task runner that claims queued jobs and executes adapters.
- `web`: React admin console.
- `db`: SQLite file mounted under `data/` in MVP. Optional Postgres later.
- `tools`: local filesystem area for cloned tools, config, API keys, cookies, and generated reports.

High-level flow:

1. Operator creates a scan from the web UI or API.
2. API validates target and creates an `investigation`.
3. Planner selects initial tools based on target type and strategy profile.
4. Worker executes tool jobs.
5. Each adapter writes raw observations and normalized entities.
6. Enrichment planner derives new entities and queues follow-up jobs until budgets are exhausted.
7. Cross-verification engine scores entities and relationships.
8. UI displays findings, evidence, contradictions, and confidence.

## 3. Project Layout

```text
osint-agent-network/
  README.md
  DEVELOPMENT_MANUAL.md
  DESIGN.md
  docker-compose.yml
  .env.example
  backend/
    pyproject.toml
    app/
      main.py
      core/
        config.py
        security.py
        logging.py
        time.py
      db/
        base.py
        session.py
        models.py
        migrations/
      api/
        routes/
          health.py
          investigations.py
          jobs.py
          tools.py
          entities.py
          reports.py
      schemas/
        targets.py
        tools.py
        jobs.py
        entities.py
        reports.py
      services/
        planner.py
        worker.py
        verification.py
        normalization.py
        report_builder.py
      tools/
        base.py
        registry.py
        sherlock.py
        theharvester.py
        amass.py
        spiderfoot.py
        reconng.py
        ghunt.py
        phoneinfoga.py
      tests/
  frontend/
    package.json
    src/
      app/
      components/
      pages/
      lib/
      styles/
  deploy/
    tools/
    scripts/
  data/
    .gitkeep
  reports/
    .gitkeep
```

## 4. Core Domain Model

### 4.1 Investigation

An investigation is the top-level unit of work.

Fields:

- `id`: UUID.
- `name`: human-readable name.
- `seed_type`: `domain`, `subdomain`, `ip`, `email`, `username`, `phone`.
- `seed_value`: normalized input value.
- `strategy`: `quick`, `standard`, `deep`, `maximum`.
- `status`: `QUEUED`, `RUNNING`, `STREAMING`, `COMPLETED`, `PARTIAL_FAILED`, `BLOCKED`, `TIMED_OUT`, `CANCELLED`.
- `max_depth`: default 3 for `standard`, 5 for `deep`, 7 for `maximum`.
- `max_entities`: default 500 for `standard`, 2500 for `deep`, 10000 for `maximum`.
- `max_jobs`: default 50 for `standard`, 250 for `deep`, 1000 for `maximum`.
- `created_at`, `updated_at`, `finished_at`.

### 4.2 Tool Job

A tool job is one concrete adapter execution.

Fields:

- `id`: UUID.
- `investigation_id`: UUID.
- `tool_name`: registered tool key.
- `target_type`: normalized target type.
- `target_value`: normalized target value.
- `depth`: recursive depth.
- `status`: job status.
- `started_at`, `finished_at`.
- `timeout_seconds`.
- `exit_code`.
- `stdout_excerpt`, `stderr_excerpt`.
- `raw_artifact_path`.
- `error_message`.

### 4.3 Raw Observation

Raw observations preserve the original tool output or meaningful excerpts.

Fields:

- `id`: UUID.
- `investigation_id`.
- `job_id`.
- `tool_name`.
- `observation_type`: `json`, `jsonl`, `stdout`, `stderr`, `http_response`, `file`.
- `raw_json`: JSON blob when safe and compact.
- `artifact_path`: path for large raw files.
- `observed_at`.

### 4.4 Normalized Entity

Entities are deduplicated intelligence objects.

Types:

- Identity: `username`, `real_name`, `email`, `phone`.
- Asset: `domain`, `subdomain`, `ip`, `port`, `url`.
- Platform: `profile_url`, `social_account`, `app_footprint`.
- Organization: `company`, `brand`, `department`.
- Evidence-only: `snippet`, `certificate`, `dns_record`, `whois_record`.

Fields:

- `id`: UUID.
- `investigation_id`.
- `type`.
- `value`.
- `canonical_value`.
- `first_seen_at`, `last_seen_at`.
- `confidence_score`: 0.0 to 1.0.
- `verification_status`: `UNVERIFIED`, `WEAK`, `LIKELY`, `VERIFIED`, `CONTRADICTED`, `NEGATIVE`.
- `depth`.

### 4.5 Evidence

Evidence links a tool observation to an entity or relationship.

Fields:

- `id`.
- `entity_id`.
- `job_id`.
- `source_tool`.
- `collection_method`.
- `evidence_kind`: `direct_hit`, `dns_resolution`, `certificate_transparency`, `search_result`, `profile_exists`, `google_account_signal`, `phone_metadata`, `negative_result`.
- `evidence_url`.
- `snippet`.
- `confidence_delta`.
- `freshness_days`.
- `observed_at`.

### 4.6 Relationship

Relationships power graph and evidence-chain views.

Examples:

- `email_has_username`: `admin@example.com` -> `admin`.
- `domain_has_subdomain`: `example.com` -> `vpn.example.com`.
- `username_has_profile`: `admin` -> `https://github.com/admin`.
- `phone_mentions_username`: `+63917...` -> `somehandle`.
- `profile_same_identity_as`: profile A -> profile B.

Fields:

- `id`.
- `from_entity_id`.
- `to_entity_id`.
- `relationship_type`.
- `confidence_score`.
- `supporting_evidence_count`.
- `created_at`.

## 5. Tool Registry

Each tool must be registered with capability metadata. The planner cannot call tools that are not registered.

Example:

```json
{
  "name": "sherlock",
  "display_name": "Sherlock",
  "enabled": true,
  "execution_mode": "sync_cli",
  "accepts": ["username"],
  "produces": ["profile_url", "social_account"],
  "requires_credentials": false,
  "credential_keys": [],
  "default_timeout_seconds": 120,
  "max_timeout_seconds": 300,
  "supports_streaming": false,
  "base_confidence": 0.45,
  "high_recall_cost": "medium",
  "noise_risk": "medium"
}
```

Registry requirements:

- Store static defaults in code.
- Allow runtime enable/disable and path overrides through DB or `.env`.
- Expose `/api/tools` for UI display.
- Expose `/api/tools/{name}/health` to test executable, credentials, and basic version availability.

## 6. Tool Adapter Standards

All adapters implement the same interface:

```python
class ToolAdapter:
    name: str

    def validate_target(self, target_type: str, value: str) -> None:
        ...

    def healthcheck(self) -> ToolHealth:
        ...

    def build_command(self, job: ToolJob) -> ToolCommand:
        ...

    def parse_results(self, job: ToolJob, artifacts: ToolArtifacts) -> ParsedToolResult:
        ...
```

Rules:

- Never interpolate untrusted input into shell strings.
- Prefer argument arrays over `shell=True`.
- Create a per-job working directory under `data/jobs/{job_id}`.
- Capture stdout/stderr and truncate excerpts for DB storage.
- Store full raw output as artifacts.
- Parse only after the process exits unless the adapter declares streaming support.
- For JSONL tools like Amass, support incremental parsing while the file grows.
- Mark partial results as valid even if the tool exits non-zero after producing useful artifacts.

## 7. Tool-Specific Calling Standards

### 7.1 Sherlock

Purpose:

- Discover public profiles for a username across many platforms.

Input:

- `target_type`: `username`.
- Username must be stripped, lower-risk normalized, and must not include spaces, slashes, shell metacharacters, or URL syntax.

Call pattern:

```bash
python3 -m sherlock_project USERNAME --json OUTPUT.json --timeout 5
```

If the installed package exposes a script instead of module execution, allow path override:

```bash
python3 /opt/osint/sherlock/sherlock_project USERNAME --json OUTPUT.json --timeout 5
```

Parsing:

- Load JSON output.
- Keep only claimed or found accounts.
- Emit:
  - `username` entity.
  - `profile_url` entity per found platform.
  - `username_has_profile` relationship.
  - evidence kind `profile_exists`.
- The built-in CLI adapter supports parsing a saved JSON artifact or running the local command:

```bash
python3 -m app.agent_client run-tool \
  --tool sherlock \
  --target-type username \
  --target USERNAME \
  --task-id TASK_ID \
  --agent-id AGENT_ID \
  --workdir data/jobs/TASK_ID/sherlock_USERNAME
```

Noise handling:

- Sherlock confirms existence, not identity ownership.
- Base confidence should remain moderate until cross-verified with email, GHunt, profile text, avatar, or repeated username reuse.

### 7.2 theHarvester

Purpose:

- Collect emails, hosts, subdomains, URLs, and public references from search engines and OSINT sources.

Input:

- `target_type`: `domain`.
- Source list: default `all` for high recall; allow profile override such as `baidu,bing,crtsh,duckduckgo`.

Call pattern:

```bash
python3 theHarvester.py -d example.com -l 500 -b all -f report
```

Expected artifact:

- `report.json` or equivalent generated JSON under the job directory.

Parsing:

- Extract `hosts` as `subdomain` or `domain` entities.
- Extract `emails` as `email` entities.
- Extract URLs as `url` entities.
- Derive usernames from email local parts.
- Create:
  - `domain_has_subdomain`.
  - `domain_exposes_email`.
  - `email_has_username`.
- The built-in CLI adapter supports parsing saved JSON reports and writing normalized output back to the Agent API:

```bash
python3 -m app.agent_client run-tool \
  --tool theharvester \
  --target-type domain \
  --target example.com \
  --task-id TASK_ID \
  --agent-id AGENT_ID \
  --input-file data/jobs/TASK_ID/theharvester_report.json
```

High-recall mode:

- Increase limit to 1000 or 5000 depending on strategy.
- Allow multiple source batches when a single `all` run is unreliable.

### 7.3 OWASP Amass

Purpose:

- Deep subdomain and DNS asset discovery.

Input:

- `target_type`: `domain`.

Call pattern:

```bash
amass enum -d example.com -json amass_out.json
```

MVP should use passive mode for quick profile and full enum for deep or maximum profile:

```bash
amass enum -passive -d example.com -json amass_out.json
```

Streaming:

- Treat output as JSONL.
- Tail the file while process is running.
- Insert entities incrementally.

Parsing:

- Extract names as `subdomain`.
- Extract addresses as `ip`.
- Link each discovered name to the root domain using `domain_has_subdomain`.
- Link each discovered address using `subdomain_resolves_to_ip`.
- The built-in CLI adapter accepts saved JSONL artifacts or runs local Amass:

```bash
python3 -m app.agent_client run-tool \
  --tool amass \
  --target-type domain \
  --target example.com \
  --task-id TASK_ID \
  --agent-id AGENT_ID \
  --workdir data/jobs/TASK_ID/amass_example.com \
  --timeout 1200
```
- Extract resolved DNS evidence when present.
- Create `domain_has_subdomain` and `subdomain_resolves_to_ip` relationships.

Timeout:

- Quick: 10 minutes.
- Standard: 20 minutes.
- Deep: 60 minutes.
- Maximum: configurable, default 120 minutes.

### 7.4 SpiderFoot

Purpose:

- Broad automated correlation and enrichment across many OSINT modules.

Input:

- `target_type`: `domain`, `ip`, `email`, or `username`.
- Scan profile: `passive`, `footprint`, `investigate`, `all`.

Call pattern:

- Preferred: REST API.
- Create scan, poll status, fetch JSON results.

Expected flow:

1. `POST /api/v1/scan/new` with scan name, target, and scan type.
2. Store returned `scan_id`.
3. Poll scan status.
4. Fetch JSON results when finished.
5. Normalize only high-value event types into entities.

MVP:

- Implement adapter skeleton and healthcheck.
- Enable only when SpiderFoot endpoint is configured.
- The built-in CLI adapter can run the REST scan when `SPIDERFOOT_BASE_URL` is configured, or parse a saved JSON artifact:

```bash
python3 -m app.agent_client run-tool \
  --tool spiderfoot \
  --target-type domain \
  --target example.com \
  --task-id TASK_ID \
  --agent-id AGENT_ID \
  --workdir data/jobs/TASK_ID/spiderfoot_example.com
```

Noise handling:

- SpiderFoot can produce extremely large output.
- Store raw output as file artifact.
- Feed agent only top entity candidates and evidence summaries.

### 7.5 Recon-ng

Purpose:

- Workspace-based OSINT workflows and module chaining.

Input:

- Usually `domain`, `company`, or `email`.

Call pattern:

```bash
recon-ng -r recon.rc
```

Adapter behavior:

- Generate resource scripts from safe templates.
- Never allow arbitrary user-supplied recon-ng commands.
- Export reports to JSON or read workspace DB after execution.

MVP:

- Implement resource-script generator and adapter skeleton.
- Keep disabled until templates are confirmed.
- The built-in CLI adapter now generates a safe resource script from templates and parses exported JSON:

```bash
python3 -m app.agent_client run-tool \
  --tool reconng \
  --target-type domain \
  --target example.com \
  --task-id TASK_ID \
  --agent-id AGENT_ID \
  --workdir data/jobs/TASK_ID/reconng_example.com
```

### 7.6 GHunt

Purpose:

- Google-account-related public footprint enrichment for Gmail addresses and related identifiers.

Input:

- `target_type`: `email`.
- Must be Gmail or Google-account-compatible email when using email mode.

Preflight:

```bash
ghunt check
```

Call pattern:

```bash
ghunt email target@gmail.com --json output.json
```

Rules:

- If credentials are invalid, mark job `BLOCKED_NO_CREDENTIALS`.
- Do not try to obtain or refresh cookies automatically in MVP.
- Store credential state in tool health.
- The built-in CLI adapter reads `GHUNT_COMMAND` and expects GHunt credentials to be managed outside this project:

```bash
python3 -m app.agent_client run-tool \
  --tool ghunt \
  --target-type email \
  --target target@gmail.com \
  --task-id TASK_ID \
  --agent-id AGENT_ID \
  --workdir data/jobs/TASK_ID/ghunt_target
```

Parsing:

- Extract Google account existence signals.
- Extract public profile, YouTube, Maps, profile name, avatar URL, and related public metadata when present.
- Emit negative evidence if GHunt clearly reports nonexistence.

### 7.7 PhoneInfoga

Purpose:

- Phone number validation, formatting, public footprint links, and metadata.

Input:

- `target_type`: `phone`.
- Normalize to E.164 before calling.

Call pattern:

```http
GET http://localhost:5000/api/v1/number/{formatted_number}
```

Parsing:

- Emit `phone`.
- Emit country, carrier, timezone as evidence or metadata.
- Emit discovered footprint URLs as `url` or `profile_url`.
- Extract candidate usernames or organization names from snippets when available.

MVP:

- Implement adapter skeleton and healthcheck.
- Enable when local PhoneInfoga endpoint is configured.
- The built-in CLI adapter reads `PHONEINFOGA_BASE_URL` and optional `PHONEINFOGA_API_KEY` from the Agent environment:

```bash
python3 -m app.agent_client run-tool \
  --tool phoneinfoga \
  --target-type phone \
  --target +639171234567 \
  --task-id TASK_ID \
  --agent-id AGENT_ID \
  --workdir data/jobs/TASK_ID/phoneinfoga_target
```

## 8. Strategy Profiles

The planner uses strategy profiles to balance speed and recall.

### quick

- Max depth: 1.
- Max jobs: 10.
- Max entities: 100.
- Tools:
  - username -> Sherlock.
  - domain -> theHarvester passive sources.
  - phone -> PhoneInfoga if configured.

### standard

- Max depth: 3.
- Max jobs: 50.
- Max entities: 500.
- Tools:
  - domain -> theHarvester + Amass passive.
  - email -> GHunt if configured + derive username -> Sherlock.
  - username -> Sherlock.
  - phone -> PhoneInfoga -> candidate username -> Sherlock.

### deep

- Max depth: 5.
- Max jobs: 250.
- Max entities: 2500.
- Tools:
  - domain -> theHarvester all + Amass full + SpiderFoot passive/footprint if configured.
  - email -> GHunt + Sherlock on local part + domain enrichment.
  - username -> Sherlock + SpiderFoot if configured.
  - phone -> PhoneInfoga + recursive URL and username extraction.

### maximum

- Max depth: 7.
- Max jobs: 1000.
- Max entities: 10000.
- Tools:
  - all eligible tools for the target type.
  - allow repeated source batches and retries.
  - keep contradictions and weak evidence instead of pruning aggressively.

## 9. Recursive Enrichment Rules

The system should generate follow-up jobs from discovered entities. Current implementation note, 2026-05-20: follow-up planning is handled by `backend/app/core/inference.py` through `plan_progressive_jobs`. Generated jobs include `depends_on=inferred_from:<entity_type>:<entity_value>` so the operator can trace why the next step exists.

Rules:

- domain / official website -> run theHarvester, Amass, SpiderFoot, Recon-ng when configured.
- subdomain -> optionally run DNS resolution and HTTP title fetch later.
- email -> run socialscan, derive username/domain, run SpiderFoot/Recon-ng when configured, run GHunt only with cookie configuration.
- username -> run Sherlock, Maigret, socialscan, SpiderFoot if configured.
- phone -> run PhoneInfoga, extract candidate URLs for profile parsing.
- profile_url / high-value external_link -> run Profile Parser and extract linked domains.
- news_article / news URL -> parse article metadata and extract business events, buying signals, risk signals.
- organization / company -> run Company News and role-based enterprise/contact/social/supply-chain/purchase-intent jobs.
- ip -> SpiderFoot and later passive DNS adapters.

Deduplication:

- Use canonical values:
  - domains lowercased and punycode-normalized.
  - emails lowercased.
  - phones E.164.
  - URLs normalized without tracking parameters.
  - usernames lowercased for matching, but preserve display casing.

Cycle prevention:

- Do not queue the same `tool + target_type + canonical_value` twice in the same investigation.
- Stop branch if depth exceeds strategy limit.
- Stop branch if job or entity budget is exhausted.
- Stop branch if entity receives strong negative evidence.

Mature-result behavior:

- Weak entities are retained.
- Weak entities can still trigger a low-cost follow-up if budget remains, but follow-up results stay in review until verified.
- Contradicted entities stay visible with lower confidence rather than being deleted.
- Main graph slots require an A-grade source, or two independent B/C-grade sources, or one B/C source plus a strong relationship context and no contradiction.

## 10. Cross-Verification Engine

Current implementation note, 2026-05-20: verification now includes helper functions for Admiralty Code and estimative language in `backend/app/core/verification.py`. The code can convert source reliability and credibility into `A-1` through `F-6`, then map confidence into Chinese probability language for BLUF reports.

### 10.1 Confidence Formula

Each entity score is calculated from evidence, not hard-coded tool trust.

Recommended formula:

```text
confidence =
  clamp(
    base_entity_prior
    + source_agreement_score
    + evidence_quality_score
    + freshness_score
    + relationship_support_score
    - contradiction_penalty
    - stale_penalty,
    0,
    1
  )
```

### 10.2 Tool Base Weights

Default base weights:

- Amass subdomain hit: 0.50.
- theHarvester host/email hit: 0.35.
- SpiderFoot correlated hit: 0.30.
- Sherlock profile existence: 0.35.
- GHunt positive Google signal: 0.55.
- PhoneInfoga valid phone metadata: 0.45.
- Recon-ng module hit: 0.35.

### 10.3 Evidence Quality Weights

Additive modifiers:

- DNS resolves currently: +0.25.
- Certificate transparency record: +0.20.
- Multiple independent tools agree: +0.15 per additional independent tool, capped at +0.30.
- Search result snippet contains exact target: +0.15.
- Profile page URL matches exact username: +0.10.
- Email local part matches username: +0.10.
- Same avatar/name/bio across two platforms: +0.25.
- Recent observation under 30 days: +0.10.

Penalties:

- DNS NXDOMAIN or no current resolution for asset: -0.20.
- Tool output indicates nonexistent/deleted account: -0.45.
- Username is common or generic: -0.15.
- Search snippet is stale or ambiguous: -0.10.
- Only one noisy source with no supporting evidence: -0.20.

### 10.4 Verification Status Thresholds

- `VERIFIED`: score >= 0.80.
- `LIKELY`: score >= 0.60 and < 0.80.
- `WEAK`: score >= 0.35 and < 0.60.
- `UNVERIFIED`: score > 0 and < 0.35.
- `NEGATIVE`: strong negative evidence and score below 0.20.
- `CONTRADICTED`: positive and negative evidence both exist.

### 10.5 Scenario A: Enterprise Asset Verification

Inputs:

- Domain seed.
- Outputs from theHarvester, Amass, and SpiderFoot.

Workflow:

1. Run Amass for subdomain discovery.
2. Run theHarvester for host/email discovery.
3. Run SpiderFoot if configured for broad correlation.
4. Merge all subdomain candidates.
5. Score each candidate using:

```text
asset_confidence =
  AmassHit * 0.50
  + HarvesterHit * 0.30
  + SpiderFootHit * 0.20
  + DNSResolve * 0.25
  + CTRecord * 0.20
  - NXDomain * 0.20
```

6. Mark assets >= 0.80 as `VERIFIED`, >= 0.60 as `LIKELY`, and retain lower scores for review.

### 10.6 Scenario B: Email to Digital Identity Verification

Workflow:

1. theHarvester extracts `admin@example.com`.
2. Normalize email and derive username `admin`.
3. Queue Sherlock on `admin`.
4. If Google-compatible or Gmail, queue GHunt.
5. Link:
   - email -> username.
   - username -> platform profiles.
   - email -> Google account signals.
6. Increase confidence when profile names, bios, avatars, or handles are consistent.

MVP semantic similarity:

- Use deterministic heuristics first:
  - exact username match.
  - display name token overlap.
  - same avatar URL hash if available.
  - same organization/domain mention.
- Leave LLM semantic profile comparison as a later optional service.

### 10.7 Scenario C: Phone to Identity Verification

Workflow:

1. Normalize phone to E.164.
2. Run PhoneInfoga.
3. Extract footprint URLs, snippets, organization names, and candidate usernames.
4. Queue Sherlock for candidate usernames.
5. Link phone -> snippet/url -> candidate username -> social profile.
6. Score higher when exact phone appears alongside the same username or organization across multiple pages.

## 11. API Design

### 11.1 Health

- `GET /api/health`: service status.
- `GET /api/tools`: registered tools and enabled state.
- `GET /api/tools/{name}/health`: executable/API/credential check.

### 11.2 Investigations

- `POST /api/investigations`: create investigation.
- `GET /api/investigations`: list investigations.
- `GET /api/investigations/{id}`: detail.
- `POST /api/investigations/{id}/cancel`: cancel queued/running work.
- `POST /api/investigations/{id}/resume`: resume if partial.
- `GET /api/investigations/{id}/timeline`: job and evidence timeline.

Create payload:

```json
{
  "name": "example.com deep scan",
  "seed_type": "domain",
  "seed_value": "example.com",
  "strategy": "deep",
  "enabled_tools": ["theharvester", "amass", "sherlock", "ghunt"],
  "max_depth": 5,
  "max_jobs": 250,
  "max_entities": 2500
}
```

### 11.3 Jobs

- `GET /api/jobs?investigation_id=...`: list jobs.
- `GET /api/jobs/{id}`: job detail.
- `POST /api/jobs/{id}/cancel`: cancel job.
- `GET /api/jobs/{id}/logs`: stdout/stderr excerpts and artifact links.

### 11.4 Entities

- `GET /api/investigations/{id}/entities`: filterable entity list.
- `GET /api/entities/{id}`: entity detail, evidence, relationships.
- `GET /api/investigations/{id}/graph`: graph JSON for UI.

### 11.5 Reports

- `GET /api/investigations/{id}/report`: redacted structured report JSON.
- `GET /api/investigations/{id}/report.md`: redacted Markdown report.
- `GET /api/investigations/{id}/report.html`: redacted self-contained HTML report for external handoff.
- `GET /api/investigations/{id}/report.pdf`: redacted printable PDF report. Returns `503` with JSON detail when PDF support is unavailable because `reportlab` is not installed.

## 12. Web Management Interface

Design direction:

- Dense, quiet, technical console.
- No marketing hero page.
- First screen is the dashboard and investigation table.
- Dark mode preferred for long analysis sessions, with high-contrast status colors.
- Use compact cards only for repeated summaries; avoid decorative section cards.

Required pages:

1. Dashboard
   - active investigations.
   - recent findings.
   - tool health.
   - queue depth.
2. New Investigation
   - seed type and value.
   - strategy selector.
   - tool toggles.
   - budget fields.
3. Investigation Detail
   - status header.
   - job timeline.
   - entity tabs: assets, identities, platforms, evidence.
   - confidence filters.
   - graph view.
4. Entity Detail
   - normalized value.
   - confidence and verification state.
   - supporting evidence.
   - relationships.
   - raw observation links.
5. Tools
   - enabled state.
   - healthcheck result.
   - path/API endpoint configuration hints.
   - credential status.
6. Reports
   - Markdown preview.
   - JSON export.

Important UI states:

- Empty investigations.
- Tool missing executable.
- Credentials invalid.
- Partial failure with useful results.
- Long-running streaming job.
- Cancelled investigation.

## 13. Configuration

`.env` keys:

```env
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8080
DATABASE_URL=sqlite:///./data/osint.db
JOB_WORKDIR=./data/jobs
ARTIFACT_DIR=./data/artifacts

OSINT_LLM_BASE_URL=http://192.0.2.10:6780/v1
OSINT_LLM_API_KEY=
OSINT_LLM_MODEL=gpt-5.4
OSINT_LLM_TIMEOUT=30

SHERLOCK_COMMAND=python3
SHERLOCK_MODULE=sherlock_project
THEHARVESTER_PATH=/opt/osint/theHarvester/theHarvester.py
AMASS_COMMAND=amass

SPIDERFOOT_BASE_URL=
SPIDERFOOT_API_KEY=
PHONEINFOGA_BASE_URL=http://phoneinfoga:5000
GHUNT_COMMAND=ghunt
RECONNG_COMMAND=recon-ng
```

Rules:

- Missing optional tool configuration disables that tool but does not break the app.
- Tool health page must show why a tool is disabled.
- Secrets must never be printed in logs.

## 14. Deployment on <production-host>

Target folder:

```text
/opt/osint-agent-network
```

Initial setup:

```bash
mkdir -p /opt/osint-agent-network
cd /opt/osint-agent-network
docker-compose up -d --build
```

Ports:

- Web UI: `http://<production-host>:3008`
- API: `http://<production-host>:8088`

MVP can run backend and worker directly with Python before Docker is complete.

## 15. Development Phases

### Phase 1: Skeleton and Manual

- Create project folder.
- Add this manual.
- Add `README.md`, `DESIGN.md`, `.env.example`, and base compose file.

### Phase 2: Backend Core

- FastAPI app.
- SQLAlchemy models.
- Investigation/job/entity/evidence APIs.
- Worker loop.
- Tool registry.
- Normalization utilities.

### Phase 3: First Adapters

- Sherlock adapter.
- theHarvester adapter.
- Amass adapter with JSONL parsing.
- Healthcheck for all three.

### Phase 4: Cross-Verification

- Confidence scoring.
- Relationship creation.
- Recursive planner.
- Budget enforcement.

### Phase 5: Web UI

- Dashboard.
- New investigation form.
- Investigation detail.
- Entity list/detail.
- Tool health page.

### Phase 6: Remaining Adapter Skeletons

- SpiderFoot REST adapter.
- GHunt adapter with credential preflight.
- PhoneInfoga REST adapter.
- Recon-ng resource-script adapter.

## 16. Testing Requirements

Backend tests:

- Target normalization.
- Tool registry selection.
- Adapter command construction.
- Parser fixtures for Sherlock, theHarvester, and Amass.
- Confidence scoring.
- Recursive planner deduplication and budget enforcement.
- API create/list/detail flows.

Frontend tests:

- New investigation form validation.
- Investigation list rendering.
- Entity confidence filters.
- Tool health state rendering.

Manual verification:

- Create a username scan with Sherlock disabled and confirm blocked state.
- Create a domain scan in quick mode and confirm theHarvester job is queued.
- Feed parser fixtures and confirm entities/relationships are created.
- Run Amass parser against JSONL sample and confirm streaming-safe parsing.

## 17. Operational Rules

- Every job must be cancellable.
- Every long-running job must write heartbeat updates.
- Every parser must tolerate malformed partial output.
- Every investigation must produce a report even if partially failed.
- Raw artifacts are retained by default.
- UI must distinguish tool failure from no findings.
- Confidence must be explainable from evidence rows.

## 18. First Implementation Cut

The first working cut should include:

- FastAPI health endpoint.
- SQLite models and DB initialization.
- Investigation creation/list/detail.
- Job queue table.
- Worker that can execute a mock adapter.
- Tool registry with Sherlock/theHarvester/Amass metadata.
- Parser and normalizer test fixtures.
- React dashboard shell and investigation creation form.

After this cut is stable, replace the mock adapter with real Sherlock, then theHarvester, then Amass.
