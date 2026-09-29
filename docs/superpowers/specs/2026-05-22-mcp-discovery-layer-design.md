# MCP Discovery Layer Design

Version: 1.0
Updated: 2026-05-22
Status: Ready for implementation planning

## 1. Purpose

This phase adds a minimal MCP-style discovery layer for 皇城司. It exposes read-only capability descriptions, resources, and prompt templates so external runtimes can discover how to call the existing Tool Gateway and understand the Agent / Skill governance layer.

This is not a full MCP JSON-RPC server. It is a safe bridge toward MCP-compatible operation while keeping write operations behind the existing Agent API.

## 2. MCP Concepts Applied

The MCP model organizes server capabilities into:

- Tools: model-callable actions with input schemas.
- Resources: read-only contextual data.
- Prompts: user-invoked reusable workflow templates.

This phase maps 皇城司 capabilities into those concepts without adding remote write execution.

## 3. Scope

### In Scope

- Add a Python descriptor builder.
- Add read-only API endpoints:
  - `GET /api/mcp/descriptor`
  - `GET /api/mcp/resources/agent-manifest`
  - `GET /api/mcp/resources/intel-schema`
- Describe three tools:
  - `hcs_plan_tools`
  - `hcs_tool_health`
  - `hcs_agent_manifest`
- Describe three resources:
  - `hcs://agent-manifest`
  - `hcs://intel-schema`
  - `hcs://tool-health`
- Describe three prompts:
  - `hcs_sparse_lead_triage`
  - `hcs_company_due_diligence`
  - `hcs_cross_verification_review`

### Out of Scope

- No JSON-RPC MCP server.
- No stdio MCP transport.
- No SSE MCP transport.
- No remote write tools.
- No agent task completion via MCP.
- No UI changes.

## 4. Architecture

Add `backend/app/core/mcp_descriptor.py` with:

```python
def build_mcp_descriptor(root: Path | None = None) -> dict:
    ...

def load_mcp_resource(name: str, root: Path | None = None) -> dict:
    ...
```

The descriptor is deterministic and generated from static project files where appropriate.

`/api/mcp/descriptor` returns the descriptor. Resource endpoints return parsed JSON resources.

## 5. Descriptor Shape

Descriptor root:

```json
{
  "service": "osint-agent-network",
  "version": "0.1",
  "mcp_style": "discovery-only",
  "capabilities": {
    "tools": [...],
    "resources": [...],
    "prompts": [...]
  }
}
```

Each tool includes:

- `name`
- `description`
- `input_schema`
- `readonly`

All tools in this phase are readonly.

## 6. Resource Behavior

`agent-manifest` loads `agent-manifest.json`.

`intel-schema` loads `backend/app/core/intel_schema.json`.

Unknown resources return `404`.

## 7. Testing

Add tests for:

- Descriptor contains tools, resources, and prompts.
- `hcs_plan_tools` declares `target_type`, `target_value`, and `strategy`.
- API endpoint `/api/mcp/descriptor` returns descriptor.
- API endpoint `/api/mcp/resources/agent-manifest` returns manifest with agents.
- API endpoint `/api/mcp/resources/intel-schema` returns schema with entities and evidence sections.
- Unknown MCP resource returns `404`.

## 8. Success Criteria

- `PYTHONPATH=backend python3 -m unittest backend.tests.test_mcp_descriptor` passes.
- `bash scripts/verify.sh` passes.
- README clearly says this is MCP-style discovery, not a full MCP server.
