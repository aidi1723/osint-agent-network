from __future__ import annotations

import json
from pathlib import Path


def build_mcp_descriptor(root: Path | None = None) -> dict:
    root = _root(root)
    return {
        "service": "osint-agent-network",
        "version": "0.1",
        "mcp_style": "discovery-only",
        "capabilities": {
            "tools": _tools(),
            "resources": _resources(),
            "prompts": _prompts(),
        },
        "notes": [
            "This is an MCP-style discovery layer, not a full MCP JSON-RPC server.",
            "All exposed tools are read-only or planning-only in this phase.",
            f"Project root: {root}",
        ],
    }


def load_mcp_resource(name: str, root: Path | None = None) -> dict | None:
    root = _root(root)
    paths = {
        "agent-manifest": root / "agent-manifest.json",
        "intel-schema": root / "backend" / "app" / "core" / "intel_schema.json",
    }
    path = paths.get(name)
    if path is None or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _tools() -> list[dict]:
    return [
        {
            "name": "hcs_plan_tools",
            "description": "Plan appropriate 皇城司 OSINT tool routes for a target without executing them.",
            "readonly": True,
            "input_schema": {
                "type": "object",
                "required": ["target_type", "target_value", "strategy"],
                "additionalProperties": False,
                "properties": {
                    "target_type": {
                        "type": "string",
                        "enum": [
                            "company",
                            "sparse_lead",
                            "domain",
                            "subdomain",
                            "email",
                            "username",
                            "phone",
                            "ip",
                            "url",
                            "profile_url",
                        ],
                    },
                    "target_value": {"type": "string", "minLength": 1},
                    "strategy": {"type": "string", "enum": ["quick", "standard", "deep", "maximum"]},
                },
            },
            "http": {
                "method": "GET",
                "path": "/api/tools/plan?target_type={target_type}&target={target_value}&strategy={strategy}",
            },
        },
        {
            "name": "hcs_tool_health",
            "description": "Read registered OSINT tool health and configuration readiness.",
            "readonly": True,
            "input_schema": {"type": "object", "additionalProperties": False, "properties": {}},
            "http": {"method": "GET", "path": "/api/tools/health"},
        },
        {
            "name": "hcs_agent_manifest",
            "description": "Read the Agent / Skill governance manifest.",
            "readonly": True,
            "input_schema": {"type": "object", "additionalProperties": False, "properties": {}},
            "http": {"method": "GET", "path": "/api/mcp/resources/agent-manifest"},
        },
    ]


def _resources() -> list[dict]:
    return [
        {
            "uri": "hcs://agent-manifest",
            "name": "Agent Manifest",
            "description": "Static Agent / Skill governance manifest.",
            "mimeType": "application/json",
            "http": {"method": "GET", "path": "/api/mcp/resources/agent-manifest"},
        },
        {
            "uri": "hcs://intel-schema",
            "name": "Intel Schema",
            "description": "Core intelligence object schema and reporting rules.",
            "mimeType": "application/json",
            "http": {"method": "GET", "path": "/api/mcp/resources/intel-schema"},
        },
        {
            "uri": "hcs://tool-health",
            "name": "Tool Health",
            "description": "Tool health is available through the read-only hcs_tool_health tool.",
            "mimeType": "application/json",
            "http": {"method": "GET", "path": "/api/tools/health"},
        },
    ]


def _prompts() -> list[dict]:
    return [
        {
            "name": "hcs_sparse_lead_triage",
            "description": "Triage a sparse Alibaba or CRM lead using anchors, identity-match separation, ACH, and BLUF.",
            "arguments": ["lead_fields", "operator_context"],
        },
        {
            "name": "hcs_company_due_diligence",
            "description": "Run company due diligence with constrained search, evidence ledger, fact promotion, and directed collection.",
            "arguments": ["company_name", "country_region", "product_context"],
        },
        {
            "name": "hcs_cross_verification_review",
            "description": "Review candidate facts for source diversity, contradictions, Admiralty Code, and report readiness.",
            "arguments": ["investigation_summary", "candidate_facts"],
        },
    ]


def _root(root: Path | None) -> Path:
    if root is not None:
        return root
    return Path(__file__).resolve().parents[3]
