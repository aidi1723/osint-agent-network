# Anthropic Financial Services Reference Handoff

Updated: 2026-05-22

## Summary

This handoff records the completed four-phase adaptation of engineering patterns from Anthropic's `financial-services` reference repository into 皇城司 / OSINT Agent Network.

The work intentionally borrowed architecture and governance patterns rather than financial-domain workflows:

- File-based agent and skill governance.
- Deterministic manifest validation.
- Structured write-back validation.
- Reader / verifier / reporter responsibility isolation.
- MCP-style discovery for external runtimes.

The implementation does not convert the project into a SaaS product, does not add intrusive collection, and does not expose remote write tools through MCP.

## Phase Status

| Phase | Status | Result |
| --- | --- | --- |
| 1. Agent / Skill static governance | Complete | Added file-based role prompts, reusable skills, manifest, and validator. |
| 2. Agent write-back validation | Complete | Added API-boundary validation for structured Agent writes. |
| 3. Reader / verifier / reporter isolation | Complete | Added local role-agent responsibility boundaries through a permissioned store wrapper. |
| 4. MCP / external runtime discovery layer | Complete | Added read-only MCP-style descriptor and resource endpoints. |

## Phase 1: Agent / Skill Static Governance

Added:

- `agent-manifest.json`
- `agent_manifest_validator.py`
- `scripts/check_agents.py`
- `agents/enterprise-intel-agent.md`
- `agents/social-intel-agent.md`
- `agents/contact-discovery-agent.md`
- `agents/cross-verification-agent.md`
- `agents/analysis-judgement-agent.md`
- `skills/constrained-search/SKILL.md`
- `skills/evidence-promotion/SKILL.md`
- `skills/cross-verification/SKILL.md`
- `skills/bluf-reporting/SKILL.md`
- `backend/tests/test_agent_manifest.py`

Purpose:

- Move role behavior from scattered long-form docs into small, reusable files.
- Make Agent / Skill references checkable before packaging or deployment.
- Establish a governance source that external agents and future runtime adapters can read.

Verification:

```bash
python3 scripts/check_agents.py
PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_manifest
```

## Phase 2: Agent Write-Back Validation

Added:

- `backend/app/core/agent_payload_validation.py`

Modified:

- `backend/app/main.py`
- `backend/tests/test_agent_protocol.py`
- `README.md`

Validated API write paths:

- `/api/agent/entities`
- `/api/agent/evidence`
- `/api/agent/evidence-records`
- `/api/agent/facts`
- `/api/agent/relationships`

Behavior:

- Invalid payloads return `400`.
- Response shape:

```json
{
  "detail": "validation failed",
  "errors": ["field message"]
}
```

Purpose:

- Prevent malformed or under-evidenced Agent output from entering the store.
- Require confidence / credibility bounds.
- Require confirmed or likely facts to include evidence IDs and Admiralty Code.

Verification:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_protocol
```

## Phase 3: Reader / Verifier / Reporter Isolation

Added:

- `backend/app/core/agent_permissions.py`

Modified:

- `backend/app/services/role_agents.py`
- `backend/tests/test_role_agents.py`
- `README.md`

Responsibility tiers:

- `reader`: may write entities, evidence, evidence records, and relationships.
- `verifier`: may write facts, hypotheses, and hypothesis scores.
- `reporter`: may complete tasks and write reports.

Purpose:

- Convert local role-agent safety boundaries from convention into code.
- Prevent collection roles from writing final facts.
- Prevent verification roles from publishing reports.
- Prevent reporting roles from collecting new evidence.

Boundary:

- This is application-level responsibility isolation.
- It is not OS-level sandboxing.
- It does not yet apply to external HTTP Agent tokens.

Verification:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_role_agents
```

## Phase 4: MCP-Style Discovery Layer

Added:

- `backend/app/core/mcp_descriptor.py`
- `backend/tests/test_mcp_descriptor.py`

Modified:

- `backend/app/main.py`
- `README.md`

New read-only endpoints:

- `GET /api/mcp/descriptor`
- `GET /api/mcp/resources/agent-manifest`
- `GET /api/mcp/resources/intel-schema`

Descriptor exposes:

- Tools:
  - `hcs_plan_tools`
  - `hcs_tool_health`
  - `hcs_agent_manifest`
- Resources:
  - `hcs://agent-manifest`
  - `hcs://intel-schema`
  - `hcs://tool-health`
- Prompts:
  - `hcs_sparse_lead_triage`
  - `hcs_company_due_diligence`
  - `hcs_cross_verification_review`

Purpose:

- Let external runtimes discover 皇城司 capabilities using MCP concepts.
- Keep the initial integration read-only and planning-only.
- Avoid exposing remote write tools before token scopes, approval flow, and audit logging are designed.

Boundary:

- This is not a full MCP JSON-RPC server.
- This does not implement stdio, SSE, or streamable HTTP MCP transport.
- This does not expose remote write tools.

Verification:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_mcp_descriptor
```

## Design And Plan Documents

Created:

- `docs/superpowers/specs/2026-05-22-agent-skill-governance-design.md`
- `docs/superpowers/plans/2026-05-22-agent-skill-governance.md`
- `docs/superpowers/specs/2026-05-22-agent-writeback-validation-design.md`
- `docs/superpowers/plans/2026-05-22-agent-writeback-validation.md`
- `docs/superpowers/specs/2026-05-22-role-agent-permission-isolation-design.md`
- `docs/superpowers/plans/2026-05-22-role-agent-permission-isolation.md`
- `docs/superpowers/specs/2026-05-22-mcp-discovery-layer-design.md`
- `docs/superpowers/plans/2026-05-22-mcp-discovery-layer.md`

## Final Verification

Use these commands for final acceptance:

```bash
python3 scripts/check_agents.py
PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_manifest
PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_protocol
PYTHONPATH=backend python3 -m unittest backend.tests.test_role_agents
PYTHONPATH=backend python3 -m unittest backend.tests.test_mcp_descriptor
bash scripts/verify.sh
```

The most recent full verification completed with:

- 96 backend tests passing.
- Regression smoke cases passing.
- Frontend UI copy and helper checks passing.
- `npm run build` passing.

## Operational Notes

- The project directory used for this work is `/path/to/osint-agent-network`.
- The directory is not currently a git repository, so no commit or branch merge was created.
- Runtime behavior for existing tool planning, worker execution, and UI remains compatible with the existing verification suite.
- New API write validation may reject malformed external Agent payloads that were previously accepted.

## Recommended Next Work

The four-phase adaptation is complete. Reasonable future work, if needed:

1. Add scoped tokens for external HTTP Agents, separate from current shared Agent token behavior.
2. Add audit events for rejected write-back payloads.
3. Promote the MCP-style discovery layer into a real MCP server only after choosing transport and approval policy.
4. Add UI visibility for Agent role tier, manifest version, and validation status.
5. Add packaging checks that include `scripts/check_agents.py` and MCP descriptor validation.
