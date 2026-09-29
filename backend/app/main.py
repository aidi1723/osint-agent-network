from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.core.agent_payload_validation import validate_agent_payload
from app.core.agent_permissions import authorize_role_method
from app.core.intel_gateway import build_intel_plan
from app.core.mcp_descriptor import build_mcp_descriptor, load_mcp_resource
from app.core.normalization import NormalizationError
from app.core.registry import default_tool_registry
from app.core.tool_health import build_tool_health_report
from app.services.llm import LLMClient
from app.services.store import store
from app.services.worker import run_investigation_jobs


class RequestJsonError(Exception):
    def __init__(self, payload: dict, status: int):
        super().__init__(str(payload.get("detail", "invalid request body")))
        self.payload = payload
        self.status = status


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "OSINTAgentNetwork/0.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        read_token = os.getenv("READ_API_TOKEN", "") or os.getenv("ADMIN_API_TOKEN", "") or os.getenv("AGENT_API_TOKEN", "")
        if not read_request_authorized(parsed.path, dict(self.headers), read_token):
            self._json({"detail": "unauthorized read request"}, status=401)
            return

        if parsed.path == "/api/health":
            self._json({"status": "ok", "service": "osint-agent-network"})
            return

        if parsed.path == "/api/tools":
            registry = default_tool_registry()
            self._json({"tools": [tool.__dict__ for tool in registry.all()]})
            return

        if parsed.path == "/api/tools/health":
            self._json(build_tool_health_report())
            return

        if parsed.path == "/api/tools/plan":
            query = parse_qs(parsed.query)
            try:
                plan = build_intel_plan(
                    target_type=query.get("target_type", [""])[0],
                    target_value=query.get("target", [""])[0],
                    strategy_name=query.get("strategy", ["standard"])[0],
                    registry=default_tool_registry(),
                )
            except (KeyError, ValueError, NormalizationError) as exc:
                self._json({"detail": str(exc)}, status=400)
                return
            self._json(
                {
                    "target_type": plan.target_type,
                    "target_value": plan.target_value,
                    "strategy": plan.strategy_name,
                    "routes": [route.__dict__ for route in plan.routes],
                    "skipped_routes": [route.__dict__ for route in plan.skipped_routes],
                }
            )
            return

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

        if parsed.path == "/api/llm/status":
            self._json(llm_status_payload())
            return

        if parsed.path == "/api/system/status":
            self._json(system_status_payload())
            return

        if parsed.path == "/api/investigations":
            query = parse_qs(parsed.query)
            include_archived = query.get("include_archived", ["false"])[0].lower() == "true"
            self._json({"investigations": store.list_investigations(include_archived=include_archived)})
            return

        if parsed.path == "/api/agents":
            self._json({"agents": store.list_agents()})
            return

        if parsed.path.startswith("/api/investigations/"):
            investigation_id = parsed.path.rsplit("/", 1)[-1]
            item = store.get_investigation(investigation_id)
            if item is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            self._json(item)
            return

        self._json({"detail": "not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            self._handle_post(parsed)
        except RequestJsonError as exc:
            self._json(exc.payload, status=exc.status)

    def _handle_post(self, parsed):
        if parsed.path.startswith("/api/agent/"):
            if not agent_request_authorized(dict(self.headers), os.getenv("AGENT_API_TOKEN", "")):
                self._json({"detail": "unauthorized agent request"}, status=401)
                return
        elif requires_write_authorization(parsed.path):
            expected_token = os.getenv("ADMIN_API_TOKEN", "") or os.getenv("AGENT_API_TOKEN", "")
            if not request_authorized(dict(self.headers), expected_token):
                self._json({"detail": "unauthorized management request"}, status=401)
                return

        if parsed.path == "/api/investigations":
            try:
                payload = self._read_json()
                investigation = store.create_investigation(
                    name=payload["name"],
                    seed_type=payload["seed_type"],
                    seed_value=payload["seed_value"],
                    strategy_name=payload.get("strategy", "standard"),
                    metadata=payload.get("metadata", {}),
                )
            except (KeyError, ValueError, NormalizationError) as exc:
                self._json({"detail": str(exc)}, status=400)
                return

            self._json(investigation.__dict__, status=201)
            return

        if parsed.path == "/api/agents/register":
            try:
                payload = self._read_json()
                agent = store.register_agent(
                    agent_name=payload["agent_name"],
                    agent_type=payload["agent_type"],
                    capabilities=payload.get("capabilities", []),
                )
            except KeyError as exc:
                self._json({"detail": f"missing field: {exc.args[0]}"}, status=400)
                return
            self._json(agent.__dict__, status=201)
            return

        if parsed.path == "/api/agents/heartbeat":
            payload = self._read_json()
            agent = store.heartbeat_agent(payload.get("agent_id", ""))
            if agent is None:
                self._json({"detail": "agent not found"}, status=404)
                return
            self._json(agent)
            return

        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/cancel"):
            investigation_id = parsed.path.split("/")[-2]
            task = store.cancel_task(investigation_id)
            if task is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            self._json(task)
            return

        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/reopen"):
            investigation_id = parsed.path.split("/")[-2]
            task = store.reopen_task(investigation_id)
            if task is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            self._json(task)
            return

        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/retry"):
            investigation_id = parsed.path.split("/")[-2]
            task = store.retry_task(investigation_id)
            if task is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            self._json(task)
            return

        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/run-jobs"):
            investigation_id = parsed.path.split("/")[-2]
            try:
                payload = self._read_json()
                result = run_investigation_jobs(
                    store,
                    investigation_id,
                    max_jobs=payload.get("max_jobs"),
                )
            except ValueError as exc:
                self._json({"detail": str(exc)}, status=404)
                return
            self._json(result)
            return

        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/archive"):
            investigation_id = parsed.path.split("/")[-2]
            task = store.archive_task(investigation_id)
            if task is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            self._json(task)
            return

        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/delete"):
            investigation_id = parsed.path.split("/")[-2]
            deleted = store.delete_task(investigation_id)
            if not deleted:
                self._json({"detail": "investigation not found"}, status=404)
                return
            self._json({"deleted": True, "id": investigation_id})
            return

        if parsed.path == "/api/investigations/release-stale":
            payload = self._read_json()
            released = store.release_stale_claims(
                stale_after_seconds=int(payload.get("stale_after_seconds", 1800)),
            )
            self._json({"released": released})
            return

        if parsed.path == "/api/agent/tasks/claim":
            payload = self._read_json()
            task = store.claim_task(
                agent_id=payload.get("agent_id", ""),
                capabilities=payload.get("capabilities", []),
            )
            if task is None:
                self._json({"task": None, "message": "no matching open task"})
                return
            self._json({"task": task})
            return

        if parsed.path == "/api/agent/jobs/claim":
            payload = self._read_json()
            job = store.claim_job(
                agent_id=payload.get("agent_id", ""),
                capabilities=payload.get("capabilities", []),
            )
            if job is None:
                self._json({"job": None, "message": "no matching waiting job"})
                return
            self._json({"job": job})
            return

        if parsed.path == "/api/agent/events":
            payload = self._read_json()
            event = store.add_event(
                investigation_id=payload["task_id"],
                agent_id=payload["agent_id"],
                level=payload.get("level", "info"),
                message=payload["message"],
                metadata=payload.get("metadata", {}),
            )
            self._json(event, status=201)
            return

        if parsed.path == "/api/agent/entities":
            payload = self._read_json()
            if self._validation_failed(validate_agent_payload("entities", payload)):
                return
            if self._role_rejected(payload, "add_entity"):
                return
            created = [
                store.add_entity(
                    investigation_id=payload["task_id"],
                    entity_type=item["type"],
                    value=item["value"],
                    source_tool=item.get("source_tool", "agent"),
                    confidence=float(item.get("confidence", 0.0)),
                )
                for item in payload.get("entities", [])
            ]
            self._json({"entities": created}, status=201)
            return

        if parsed.path == "/api/agent/evidence":
            payload = self._read_json()
            if self._validation_failed(validate_agent_payload("evidence", payload)):
                return
            if self._role_rejected(payload, "add_evidence"):
                return
            evidence = store.add_evidence(
                investigation_id=payload["task_id"],
                entity_value=payload["entity_value"],
                evidence_kind=payload["evidence_kind"],
                source_tool=payload.get("source_tool", "agent"),
                snippet=payload.get("snippet", ""),
            )
            self._json(evidence, status=201)
            return

        if parsed.path == "/api/agent/evidence-records":
            try:
                payload = self._read_json()
                if self._validation_failed(validate_agent_payload("evidence_records", payload)):
                    return
                if self._role_rejected(payload, "add_evidence_record"):
                    return
                record = store.add_evidence_record(
                    investigation_id=payload["task_id"],
                    source_url=payload["source_url"],
                    source_type=payload["source_type"],
                    source_tool=payload.get("source_tool", "agent"),
                    snippet=payload.get("snippet", ""),
                    credibility=float(payload.get("credibility", 0.0)),
                )
            except (KeyError, ValueError) as exc:
                self._json({"detail": str(exc)}, status=400)
                return
            self._json(record, status=201)
            return

        if parsed.path == "/api/agent/facts":
            try:
                payload = self._read_json()
                if self._validation_failed(validate_agent_payload("facts", payload)):
                    return
                if self._role_rejected(payload, "add_fact"):
                    return
                fact = store.add_fact(
                    investigation_id=payload["task_id"],
                    statement=payload["statement"],
                    subject=payload["subject"],
                    predicate=payload["predicate"],
                    object_value=payload["object"],
                    status=payload.get("status", "NEEDS_REVIEW"),
                    confidence=float(payload.get("confidence", 0.0)),
                    admiralty_code=payload.get("admiralty_code", ""),
                    evidence_ids=payload.get("evidence_ids", []),
                )
            except (KeyError, ValueError) as exc:
                self._json({"detail": str(exc)}, status=400)
                return
            self._json(fact, status=201)
            return

        if parsed.path == "/api/agent/hypotheses":
            try:
                payload = self._read_json()
                if self._role_rejected(payload, "add_hypothesis"):
                    return
                hypothesis = store.add_hypothesis(
                    investigation_id=payload["task_id"],
                    hypothesis_id=payload["hypothesis_id"],
                    statement=payload["statement"],
                    group=payload.get("group", "default"),
                )
            except KeyError as exc:
                self._json({"detail": f"missing field: {exc.args[0]}"}, status=400)
                return
            self._json(hypothesis, status=201)
            return

        if parsed.path == "/api/agent/hypotheses/score":
            try:
                payload = self._read_json()
                if self._role_rejected(payload, "score_hypotheses"):
                    return
                result = store.score_hypotheses(
                    investigation_id=payload["task_id"],
                    evidence_items=payload.get("evidence_items", []),
                )
            except (KeyError, ValueError) as exc:
                self._json({"detail": str(exc)}, status=400)
                return
            self._json(result, status=201)
            return

        if parsed.path == "/api/agent/relationships":
            payload = self._read_json()
            if self._validation_failed(validate_agent_payload("relationships", payload)):
                return
            if self._role_rejected(payload, "add_relationship"):
                return
            relationship = store.add_relationship(
                investigation_id=payload["task_id"],
                from_value=payload["from"],
                to_value=payload["to"],
                relationship_type=payload["relationship_type"],
                confidence=float(payload.get("confidence", 0.0)),
            )
            self._json(relationship, status=201)
            return

        if parsed.path.startswith("/api/agent/tasks/") and parsed.path.endswith("/complete"):
            task_id = parsed.path.split("/")[-2]
            payload = self._read_json()
            if self._role_rejected(payload, "complete_task"):
                return
            task = store.complete_task(
                investigation_id=task_id,
                agent_id=payload["agent_id"],
                status=payload.get("status", "COMPLETED"),
                summary=payload.get("summary", ""),
                report_markdown=payload.get("report_markdown", ""),
                confidence=payload.get("confidence"),
            )
            if task is None:
                self._json({"detail": "task not found"}, status=404)
                return
            self._json(task)
            return

        self._json({"detail": "not found"}, status=404)

    def do_OPTIONS(self):
        self._json({})

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        max_body = int(os.getenv("MAX_REQUEST_BODY_BYTES", "10485760"))  # 10 MB
        if length > max_body:
            raise RequestJsonError({"detail": "request body too large"}, 413)
        body = self.rfile.read(length).decode("utf-8")
        if not body:
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise RequestJsonError({"detail": "invalid json body"}, 400)

    def _role_rejected(self, payload: dict, method: str) -> bool:
        error = authorize_role_method(str(payload.get("agent_role") or ""), method)
        if not error:
            return False
        self._json({"detail": error}, status=403)
        return True

    def _validation_failed(self, errors: list[str]) -> bool:
        if not errors:
            return False
        self._json({"detail": "validation failed", "errors": errors}, status=400)
        return True

    def _json(self, payload: dict, status: int = 200):
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        origin = self.headers.get("Origin", "")
        allowed_origins = _get_allowed_origins()
        if origin in allowed_origins or "*" in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin or allowed_origins[0])
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(encoded)


def run():
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8088"))
    bind_error = bind_authorization_error(
        host,
        os.getenv("AGENT_API_TOKEN", ""),
        os.getenv("ADMIN_API_TOKEN", ""),
    )
    if bind_error:
        raise SystemExit(bind_error)
    if not os.getenv("AGENT_API_TOKEN") and not os.getenv("ADMIN_API_TOKEN"):
        print("\n⚠️  WARNING: No AGENT_API_TOKEN or ADMIN_API_TOKEN configured.")
        print("   Loopback requests are open. Set tokens before exposing this API.\n")
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print(f"OSINT Agent Network API listening on http://{host}:{port}")
    server.serve_forever()


def agent_request_authorized(headers: dict, expected_token: str) -> bool:
    return request_authorized(headers, expected_token)


def request_authorized(headers: dict, expected_token: str) -> bool:
    if not expected_token:
        return True
    authorization = headers.get("Authorization") or headers.get("authorization") or ""
    return hmac.compare_digest(authorization, f"Bearer {expected_token}")


def read_request_authorized(path: str, headers: dict, expected_token: str) -> bool:
    if path in {"/api/health"}:
        return True
    return request_authorized(headers, expected_token)


def bind_authorization_error(host: str, agent_token: str, admin_token: str) -> str:
    normalized = host.strip().lower()
    if normalized in {"127.0.0.1", "localhost", "::1"}:
        return ""
    if agent_token or admin_token:
        return ""
    return (
        f"Refusing to bind {host} without AGENT_API_TOKEN or ADMIN_API_TOKEN. "
        "Use APP_HOST=127.0.0.1 for local development, or set a token before exposing the API."
    )


def _get_allowed_origins() -> list[str]:
    env_value = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if env_value:
        return [origin.strip() for origin in env_value.split(",") if origin.strip()]
    return ["http://127.0.0.1:3008", "http://localhost:3008"]


def requires_write_authorization(path: str) -> bool:
    if path == "/api/agents/register":
        return True
    if path == "/api/agents/heartbeat":
        return True
    if path == "/api/investigations":
        return True
    if path == "/api/investigations/release-stale":
        return True
    if path.startswith("/api/investigations/"):
        return any(
            path.endswith(suffix)
            for suffix in ("/cancel", "/reopen", "/retry", "/run-jobs", "/archive", "/delete")
        )
    return False


def llm_status_payload() -> dict:
    return LLMClient().status()


def system_status_payload(store_obj=store, root_dir: str | None = None) -> dict:
    root = Path(root_dir or Path(__file__).resolve().parents[2])
    db_path = Path(getattr(store_obj, "db_path", os.getenv("OSINT_DB_PATH", "data/osint.sqlite")))
    if not db_path.is_absolute():
        db_path = root / db_path
    try:
        schema_versions = store_obj.schema_versions()
        counts = store_obj.system_counts()
        database = {
            "status": "ok",
            "path": db_path.name,
            "exists": db_path.exists(),
            "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
            "schema_version_count": len(schema_versions),
            "latest_schema_version": schema_versions[-1]["version"] if schema_versions else "",
        }
    except Exception as exc:  # pragma: no cover - defensive status endpoint
        schema_versions = []
        counts = {"totals": {}, "investigations_by_status": {}, "jobs_by_status": {}}
        database = {
            "status": "error",
            "path": db_path.name,
            "exists": db_path.exists(),
            "size_bytes": 0,
            "schema_version_count": 0,
            "latest_schema_version": "",
            "error": str(exc),
        }

    registry = default_tool_registry()
    tool_health = build_tool_health_report(registry)
    scripts = {
        "backup": _script_status(root, "backup.sh"),
        "healthcheck": _script_status(root, "healthcheck.sh"),
        "verify": _script_status(root, "verify.sh"),
    }
    totals = counts.get("totals", {})
    return {
        "service": "osint-agent-network",
        "status": "ok" if database["status"] == "ok" else "degraded",
        "database": database,
        "schema_versions": schema_versions,
        "investigations": {
            "total": totals.get("investigations", 0),
            "by_status": counts.get("investigations_by_status", {}),
        },
        "jobs": {
            "total": totals.get("jobs", 0),
            "by_status": counts.get("jobs_by_status", {}),
        },
        "records": {
            "entities": totals.get("entities", 0),
            "evidence": totals.get("evidence", 0),
            "evidence_ledger": totals.get("evidence_ledger", 0),
            "facts": totals.get("facts", 0),
        },
        "tools": {
            "registered": len(registry.all()),
            "enabled_by_default": len([tool for tool in registry.all() if tool.enabled_by_default]),
            "health": tool_health["summary"],
        },
        "scripts": scripts,
    }


def _script_status(root: Path, name: str) -> dict:
    path = root / "scripts" / name
    return {
        "path": name,
        "present": path.exists(),
        "executable": os.access(path, os.X_OK),
    }


if __name__ == "__main__":
    run()
