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
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            finally:
                exc.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    unittest.main()
