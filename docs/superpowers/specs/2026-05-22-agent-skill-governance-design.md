# Agent Skill Governance Design

Version: 1.0
Updated: 2026-05-22
Status: Ready for implementation planning

## 1. Purpose

This phase adds a file-based governance layer for the existing OSINT Agent Network roles. It adapts the strongest engineering ideas from Anthropic's financial-services reference repository: canonical agent prompts, reusable skills, manifest-based wiring, and automated drift checks.

The goal is to make role behavior explicit and testable without changing the current runtime path. Existing API, Worker, Tool Gateway, SQLite schema, UI, and role-agent execution behavior remain unchanged in this phase.

## 2. Current Baseline

The project already has:

- Role-based investigation jobs in the Worker and API.
- Agent behavior described in `docs/AGENT_PROTOCOL.md` and `docs/ORCHESTRATION_MODEL.md`.
- A deterministic Intel Tool Gateway.
- Evidence ledger, fact pool, cross-verification matrix, ACH, I&W, PIR/EEI, BLUF, and quality gate modules.
- Tool adapters with normalized `entities`, `evidence`, and `relationships` output.

The gap is that agent role rules are spread across long-form documentation and Python code. They are not yet packaged as small, reusable, independently checkable agent and skill files.

## 3. Product Scope

### In Scope

- Add canonical role prompt files under `agents/`.
- Add reusable workflow skill files under `skills/`.
- Add a root `agent-manifest.json` that declares role agents, skill dependencies, allowed tool families, and output contracts.
- Add `scripts/check_agents.py` to validate the file-based governance layer.
- Add backend tests for manifest validation behavior.
- Update docs to explain that this is a governance layer and does not alter current execution.

### Out of Scope

- No changes to API routes.
- No changes to Worker scheduling.
- No changes to local role-agent execution.
- No MCP server implementation.
- No front-end UI changes.
- No write-time JSON Schema enforcement on `/api/agent/*`.
- No permission isolation between reader, verifier, and reporter agents yet.

## 4. Architecture

The governance layer is static and file-based:

```text
agents/
  enterprise-intel-agent.md
  social-intel-agent.md
  contact-discovery-agent.md
  cross-verification-agent.md
  analysis-judgement-agent.md

skills/
  constrained-search/SKILL.md
  evidence-promotion/SKILL.md
  cross-verification/SKILL.md
  bluf-reporting/SKILL.md

agent-manifest.json
scripts/check_agents.py
backend/tests/test_agent_manifest.py
```

The existing runtime remains the source of execution. The new files become the source of truth for what each role is supposed to do, what skills it may use, and what output contract it must satisfy.

## 5. Agent Files

Each `agents/*.md` file has YAML frontmatter:

```yaml
---
name: enterprise_intel_agent
description: Collects public-source company identity, website, contact, location, registration, and business-scope evidence.
skills:
  - constrained-search
  - evidence-promotion
output_contract: entities,evidence,relationships,facts
---
```

The body must include:

- Role purpose.
- Inputs it may trust.
- Required workflow.
- Guardrails.
- Required write-back fields.
- Explicit non-goals.

The first phase covers these roles:

- `enterprise_intel_agent`
- `social_intel_agent`
- `contact_discovery_agent`
- `cross_verification_agent`
- `analysis_judgement_agent`

These five roles cover the highest-risk behavior: identity, social/profile matching, contact linkage, fact promotion, and final report language.

## 6. Skill Files

Each `skills/*/SKILL.md` file has YAML frontmatter:

```yaml
---
name: constrained-search
description: Build public-source queries from confirmed anchors and prevent broad same-name results from becoming facts.
---
```

The first phase adds four skills:

- `constrained-search`: turns confirmed anchors into bounded queries and rejects broad same-name noise.
- `evidence-promotion`: explains when observations can become candidate, assessed, or accepted facts.
- `cross-verification`: compares source families, contradictions, Admiralty Code, and fact status.
- `bluf-reporting`: formats evidence-bound conclusions, gaps, ACH/I&W, and directed collection.

Skill files do not add executable code. They make repeatable analyst behavior readable and reusable by external agents, Codex sessions, and future MCP or managed-agent wrappers.

## 7. Manifest

`agent-manifest.json` declares:

- `version`
- `agents`
- `skills`
- `output_contracts`
- `allowed_tool_families`

Example shape:

```json
{
  "version": "0.1",
  "agents": [
    {
      "name": "enterprise_intel_agent",
      "path": "agents/enterprise-intel-agent.md",
      "skills": ["constrained-search", "evidence-promotion"],
      "allowed_tool_families": ["official", "registry", "directory", "news", "tool"],
      "output_contract": "entities,evidence,relationships,facts"
    }
  ],
  "skills": [
    {
      "name": "constrained-search",
      "path": "skills/constrained-search/SKILL.md"
    }
  ]
}
```

The manifest is deliberately small. It should be easy to read in review and easy to validate in CI or local verification.

## 8. Validation Script

`scripts/check_agents.py` validates:

- `agent-manifest.json` parses as JSON.
- Every declared agent path exists.
- Every declared skill path exists.
- Agent frontmatter includes `name`, `description`, `skills`, and `output_contract`.
- Skill frontmatter includes `name` and `description`.
- Manifest skill references match actual skill names.
- Agent frontmatter skill references exist in the manifest.
- Manifest output contracts use known contract tokens.
- Manifest allowed tool families use known source/tool family names.

The script exits `0` when valid and non-zero with readable errors when invalid.

## 9. Testing

Add `backend/tests/test_agent_manifest.py` with focused tests:

- Valid repository manifest passes validation.
- Missing agent file produces a validation error.
- Missing skill file produces a validation error.
- Agent referencing an unknown skill produces a validation error.
- Invalid output contract token produces a validation error.

The tests should import validation functions directly from `scripts/check_agents.py` or a small helper module if needed. The command-line script remains a thin wrapper around testable functions.

## 10. Documentation

Update the project documentation with a short section explaining:

- The governance layer is static and does not change runtime execution.
- Existing docs remain useful but role-specific behavior should move into `agents/` and `skills/` over time.
- `scripts/check_agents.py` should be run before packaging or deployment.

## 11. Success Criteria

- The new agent and skill files exist and reflect current project rules.
- `agent-manifest.json` references all first-phase files correctly.
- `python3 scripts/check_agents.py` passes.
- `PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_manifest` passes.
- Existing runtime behavior is unchanged.

## 12. Future Phases

This phase prepares, but does not implement:

- Write-back schema enforcement for `/api/agent/*`.
- Reader/verifier/reporter permission separation.
- MCP wrappers around the Intel Tool Gateway.
- Agent manifest display in the UI.
- Agent packaging for external runtimes.
