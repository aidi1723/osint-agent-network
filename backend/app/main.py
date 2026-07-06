from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.core.agent_payload_validation import validate_agent_payload
from app.core.intel_gateway import build_intel_plan
from app.core.mcp_descriptor import build_mcp_descriptor, load_mcp_resource
from app.core.normalization import NormalizationError
from app.core.registry import default_tool_registry
from app.core.tool_health import build_tool_health_report
from app.core.upkuajing_customs import UpkuajingCustomsClient, UpkuajingCustomsError
from app.services.llm import LLMClient
from app.services.report_export import build_report_payload, render_report_html, render_report_markdown
from app.services.report_pdf import PDF_UNAVAILABLE_DETAIL, ReportPdfDependencyError, render_report_pdf
from app.services.job_queue import job_queue
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
        require_token = authentication_required_for_environment()
        if not read_request_authorized(parsed.path, dict(self.headers), read_token, require_token=require_token):
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

        if parsed.path.startswith("/api/investigations/") and "/intelligence" in parsed.path:
            # 情报聚合接口: GET /api/investigations/{id}/intelligence
            investigation_id = parsed.path.split("/")[3]
            item = store.get_investigation(investigation_id)
            if item is None:
                self._json({"detail": "investigation not found"}, status=404)
                return

            # 聚合联系方式、社媒、产品情报
            from app.core.contact_discovery import ContactDiscoveryAggregator
            from app.core.social_intelligence import SocialIntelligenceAggregator
            from app.core.product_intelligence import ProductIntelligenceAggregator

            entities = item.get('entities', [])
            evidence = item.get('evidence', [])
            relationships = item.get('relationships', [])

            # 联系方式聚合
            contact_agg = ContactDiscoveryAggregator()
            contact_result = contact_agg.aggregate_from_entities(entities, evidence)
            contacts = contact_agg.format_for_display(contact_result)

            # 社媒情报聚合
            social_agg = SocialIntelligenceAggregator()
            social_result = social_agg.aggregate_from_entities(entities, evidence, relationships)
            social = social_agg.format_for_display(social_result)

            # 产品情报聚合
            product_agg = ProductIntelligenceAggregator()
            product_result = product_agg.aggregate_from_data(entities, evidence)
            products = product_agg.format_for_display(product_result)

            self._json({
                "investigation_id": investigation_id,
                "contacts": contacts,
                "social": social,
                "products": products
            })
            return

        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/report.pdf"):
            investigation_id = parsed.path.split("/")[3]
            item = store.get_investigation(investigation_id)
            if item is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            try:
                self._binary(render_report_pdf(item), "application/pdf")
            except ReportPdfDependencyError:
                self._json({"detail": PDF_UNAVAILABLE_DETAIL}, status=503)
            return

        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/report"):
            investigation_id = parsed.path.split("/")[3]
            item = store.get_investigation(investigation_id)
            if item is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            self._json(build_report_payload(item))
            return

        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/report.md"):
            investigation_id = parsed.path.split("/")[3]
            item = store.get_investigation(investigation_id)
            if item is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            self._text(render_report_markdown(item), "text/markdown; charset=utf-8")
            return

        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/report.html"):
            investigation_id = parsed.path.split("/")[3]
            item = store.get_investigation(investigation_id)
            if item is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            self._text(render_report_html(item), "text/html; charset=utf-8")
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
            if not agent_request_authorized(
                dict(self.headers),
                os.getenv("AGENT_API_TOKEN", ""),
                require_token=authentication_required_for_environment(),
            ):
                self._json({"detail": "unauthorized agent request"}, status=401)
                return
        elif requires_write_authorization(parsed.path):
            expected_token = os.getenv("ADMIN_API_TOKEN", "") or os.getenv("AGENT_API_TOKEN", "")
            if not request_authorized(
                dict(self.headers),
                expected_token,
                require_token=authentication_required_for_environment(),
            ):
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
                    respect_tool_health=True,
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
                if store.get_investigation(investigation_id) is None:
                    raise ValueError(f"investigation not found: {investigation_id}")
                result = job_queue.enqueue(
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

        if parsed.path == "/api/customs/trade/list":
            try:
                payload = self._read_json()
                result = UpkuajingCustomsClient().trade_list(payload)
            except UpkuajingCustomsError as exc:
                self._json(exc.payload, status=exc.status)
                return
            self._json(result)
            return

        if parsed.path == "/api/customs/supply-chain":
            try:
                payload = self._read_json()
                company_name = payload.get("company", "")
                if not company_name:
                    self._json({"detail": "company field is required"}, status=400)
                    return

                from app.tools.customs_supply_chain import CustomsSupplyChainAdapter
                adapter = CustomsSupplyChainAdapter()

                # 查询上下游
                customers, customer_response = adapter.find_downstream_customers(company_name)
                suppliers, supplier_response = adapter.find_upstream_suppliers(company_name)

                result = {
                    "company": company_name,
                    "downstream": {
                        "customers": [
                            {
                                "name": c.name,
                                "country": c.country,
                                "trade_count": c.trade_count,
                                "products": c.products,
                                "first_trade": c.first_trade_date,
                                "last_trade": c.last_trade_date,
                            }
                            for c in customers
                        ],
                        "total_count": len(customers)
                    },
                    "upstream": {
                        "suppliers": [
                            {
                                "name": s.name,
                                "country": s.country,
                                "trade_count": s.trade_count,
                                "products": s.products,
                                "first_trade": s.first_trade_date,
                                "last_trade": s.last_trade_date,
                            }
                            for s in suppliers
                        ],
                        "total_count": len(suppliers)
                    }
                }
                self._json(result)
            except UpkuajingCustomsError as exc:
                self._json(exc.payload, status=exc.status)
            except Exception as exc:
                self._json({"detail": str(exc)}, status=500)
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

    def _text(self, body: str, content_type: str, status: int = 200):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        origin = self.headers.get("Origin", "")
        allowed_origins = _get_allowed_origins()
        if origin in allowed_origins or "*" in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin or allowed_origins[0])
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(encoded)

    def _binary(self, body: bytes, content_type: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        origin = self.headers.get("Origin", "")
        allowed_origins = _get_allowed_origins()
        if origin in allowed_origins or "*" in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin or allowed_origins[0])
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)


def run():
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8088"))
    missing_tokens = missing_required_auth_tokens()
    if missing_tokens:
        missing = ", ".join(missing_tokens)
        raise SystemExit(f"Refusing to start in production without required API tokens: {missing}")
    if not os.getenv("AGENT_API_TOKEN") and not os.getenv("ADMIN_API_TOKEN"):
        print("\n⚠️  WARNING: No AGENT_API_TOKEN or ADMIN_API_TOKEN configured.")
        print("   The API is running without authentication. Set tokens in .env for production use.\n")
    job_queue.ensure_running(store)
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print(f"OSINT Agent Network API listening on http://{host}:{port}")
    server.serve_forever()


def agent_request_authorized(headers: dict, expected_token: str, require_token: bool = False) -> bool:
    return request_authorized(headers, expected_token, require_token=require_token)


def request_authorized(headers: dict, expected_token: str, require_token: bool = False) -> bool:
    if not expected_token:
        return not require_token
    authorization = headers.get("Authorization") or headers.get("authorization") or ""
    return authorization == f"Bearer {expected_token}"


def read_request_authorized(path: str, headers: dict, expected_token: str, require_token: bool = False) -> bool:
    if path in {"/api/health"}:
        return True
    if path == "/api/tools/health":
        return True
    return request_authorized(headers, expected_token, require_token=require_token)


def authentication_required_for_environment(env: dict | None = None) -> bool:
    values = env if env is not None else os.environ
    explicit = str(values.get("OSINT_REQUIRE_AUTH", "")).strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    if explicit in {"0", "false", "no", "off"}:
        return False
    return str(values.get("APP_ENV", "")).strip().lower() in {"prod", "production"}


def missing_required_auth_tokens(env: dict | None = None) -> list[str]:
    values = env if env is not None else os.environ
    if not authentication_required_for_environment(values):
        return []
    required = ["ADMIN_API_TOKEN", "AGENT_API_TOKEN", "READ_API_TOKEN"]
    return [name for name in required if not str(values.get(name, "")).strip()]


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
    if path == "/api/customs/trade/list":
        return True
    if path == "/api/customs/supply-chain":
        return True
    if path.startswith("/api/investigations/"):
        return any(
            path.endswith(suffix)
            for suffix in ("/cancel", "/reopen", "/retry", "/run-jobs", "/archive", "/delete")
        )
    return False


def llm_status_payload() -> dict:
    return LLMClient().status()


def system_status_payload(store_obj=store, root_dir: str | None = None, worker_queue=None) -> dict:
    root = Path(root_dir or Path(__file__).resolve().parents[2])
    db_path = Path(getattr(store_obj, "db_path", os.getenv("OSINT_DB_PATH", "data/osint.sqlite")))
    if not db_path.is_absolute():
        db_path = root / db_path
    try:
        schema_versions = store_obj.schema_versions()
        counts = store_obj.system_counts()
        database = {
            "status": "ok",
            "path": str(db_path),
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
            "path": str(db_path),
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
            "outcome_metrics": _investigation_outcome_metrics(counts.get("investigations_by_status", {})),
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
        "worker": (worker_queue or job_queue).snapshot(store_obj),
        "scripts": scripts,
    }


def _investigation_outcome_metrics(by_status: dict) -> dict:
    success_total = by_status.get("COMPLETED", 0)
    blocked_total = by_status.get("BLOCKED", 0)
    failed_total = by_status.get("FAILED", 0) + by_status.get("PARTIAL_FAILED", 0)
    terminal_total = success_total + blocked_total + failed_total
    if not terminal_total:
        return {
            "terminal_total": 0,
            "success_total": 0,
            "blocked_total": 0,
            "failed_total": 0,
            "success_rate": 0.0,
            "blocked_rate": 0.0,
            "failed_rate": 0.0,
        }
    return {
        "terminal_total": terminal_total,
        "success_total": success_total,
        "blocked_total": blocked_total,
        "failed_total": failed_total,
        "success_rate": round(success_total / terminal_total, 4),
        "blocked_rate": round(blocked_total / terminal_total, 4),
        "failed_rate": round(failed_total / terminal_total, 4),
    }


def _script_status(root: Path, name: str) -> dict:
    path = root / "scripts" / name
    return {
        "path": str(path),
        "present": path.exists(),
        "executable": os.access(path, os.X_OK),
    }


if __name__ == "__main__":
    run()
