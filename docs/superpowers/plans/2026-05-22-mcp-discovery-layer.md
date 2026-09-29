# MCP Discovery Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only MCP-style discovery layer for 皇城司 capabilities.

**Architecture:** Implement a deterministic descriptor builder in `backend/app/core/mcp_descriptor.py` and expose read-only HTTP endpoints from `backend/app/main.py`. No write tools, JSON-RPC MCP transport, or external task execution are added.

**Tech Stack:** Python standard library, existing `http.server` API, existing `unittest` HTTP test harness.

---

## File Structure

- Create `backend/app/core/mcp_descriptor.py`: descriptor and resource loading.
- Create `backend/tests/test_mcp_descriptor.py`: descriptor and HTTP endpoint tests.
- Modify `backend/app/main.py`: add MCP discovery endpoints.
- Modify `README.md`: document MCP-style discovery layer.

---

### Task 1: Write Failing MCP Descriptor Tests

**Files:**
- Create `backend/tests/test_mcp_descriptor.py`

- [ ] **Step 1: Add tests**

Create:

```python
import json
import unittest
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

from app.core.mcp_descriptor import build_mcp_descriptor
from app.main import ApiHandler


class McpDescriptorTests(unittest.TestCase):
    def test_descriptor_contains_tools_resources_and_prompts(self):
        descriptor = build_mcp_descriptor()

        capabilities = descriptor["capabilities"]
        self.assertIn("tools", capabilities)
        self.assertIn("resources", capabilities)
        self.assertIn("prompts", capabilities)
        self.assertIn("hcs_plan_tools", {tool["name"] for tool in capabilities["tools"]})
        self.assertIn("hcs://agent-manifest", {resource["uri"] for resource in capabilities["resources"]})
        self.assertIn("hcs_sparse_lead_triage", {prompt["name"] for prompt in capabilities["prompts"]})

    def test_plan_tools_schema_declares_required_inputs(self):
        descriptor = build_mcp_descriptor()
        plan_tool = next(tool for tool in descriptor["capabilities"]["tools"] if tool["name"] == "hcs_plan_tools")

        schema = plan_tool["input_schema"]

        self.assertEqual(schema["type"], "object")
        self.assertEqual(set(schema["required"]), {"target_type", "target_value", "strategy"})
        self.assertIn("target_type", schema["properties"])
        self.assertIn("target_value", schema["properties"])
        self.assertIn("strategy", schema["properties"])
        self.assertTrue(plan_tool["readonly"])

    def test_descriptor_endpoint_returns_mcp_style_payload(self):
        status, payload = _get_json("/api/mcp/descriptor")

        self.assertEqual(status, 200)
        self.assertEqual(payload["service"], "osint-agent-network")
        self.assertEqual(payload["mcp_style"], "discovery-only")
        self.assertIn("tools", payload["capabilities"])

    def test_agent_manifest_resource_endpoint_returns_manifest(self):
        status, payload = _get_json("/api/mcp/resources/agent-manifest")

        self.assertEqual(status, 200)
        self.assertIn("agents", payload)
        self.assertTrue(payload["agents"])

    def test_intel_schema_resource_endpoint_returns_schema(self):
        status, payload = _get_json("/api/mcp/resources/intel-schema")

        self.assertEqual(status, 200)
        self.assertIn("entities", payload)
        self.assertIn("evidence", payload)

    def test_unknown_resource_endpoint_returns_404(self):
        status, payload = _get_json("/api/mcp/resources/unknown")

        self.assertEqual(status, 404)
        self.assertEqual(payload["detail"], "mcp resource not found")


def _get_json(path: str) -> tuple[int, dict]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        try:
            with urlopen(f"{base_url}{path}", timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_mcp_descriptor
```

Expected: import failure for `app.core.mcp_descriptor`.

---

### Task 2: Implement Descriptor Builder

**Files:**
- Create `backend/app/core/mcp_descriptor.py`

- [ ] **Step 1: Add descriptor module**

Create:

```python
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
                        "enum": ["company", "sparse_lead", "domain", "subdomain", "email", "username", "phone", "ip", "url", "profile_url"],
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
```

- [ ] **Step 2: Run descriptor unit tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_mcp_descriptor
```

Expected: descriptor tests pass for direct builder, HTTP endpoint tests still fail with 404.

---

### Task 3: Add Read-Only API Endpoints

**Files:**
- Modify `backend/app/main.py`

- [ ] **Step 1: Import descriptor helpers**

Add:

```python
from app.core.mcp_descriptor import build_mcp_descriptor, load_mcp_resource
```

- [ ] **Step 2: Add GET routes**

In `do_GET`, after `/api/tools/plan` or before `/api/llm/status`, add:

```python
        if parsed.path == "/api/mcp/descriptor":
            self._json(build_mcp_descriptor())
            return

        if parsed.path.startswith("/api/mcp/resources/"):
            name = parsed.path.rsplit("/", 1)[-1]
            resource = load_mcp_resource(name)
            if resource is None:
                self._json({"detail": "mcp resource not found"}, status=404)
                return
            self._json(resource)
            return
```

- [ ] **Step 3: Run MCP tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_mcp_descriptor
```

Expected: all tests pass.

---

### Task 4: Documentation Update

**Files:**
- Modify `README.md`

- [ ] **Step 1: Add MCP discovery note**

In the `Agent / Skill 治理层` section, add:

```markdown
项目还提供 MCP-style discovery layer：`/api/mcp/descriptor` 会暴露只读工具、资源和提示词描述，`/api/mcp/resources/agent-manifest` 与 `/api/mcp/resources/intel-schema` 可供外部运行时读取治理层和情报 schema。它不是完整 MCP JSON-RPC server，当前不开放远程写入工具。
```

- [ ] **Step 2: Verify README note**

Run:

```bash
rg -n "MCP-style discovery layer|/api/mcp/descriptor|JSON-RPC" README.md
```

Expected: note is present.

---

### Task 5: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run MCP tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_mcp_descriptor
```

Expected: all tests pass.

- [ ] **Step 2: Run full verification**

Run:

```bash
bash scripts/verify.sh
```

Expected: full verification passes.

---

## Self-Review

- Scope stays discovery-only.
- No write tools are exposed.
- Descriptor follows MCP concepts while avoiding unsupported server claims.
- Existing Tool Gateway remains the execution source of truth.
