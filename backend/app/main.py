from collections.abc import Mapping
from dataclasses import dataclass
from email.message import Message
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
from threading import Lock
from urllib.parse import parse_qs, urlparse

from app.core.agent_payload_validation import validate_agent_payload
from app.core.browser_auth import BrowserSessionManager
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


_browser_session_manager_lock = Lock()
_browser_session_manager: BrowserSessionManager | None = None
_browser_session_manager_config: tuple[str, bool, int] | None = None
REQUEST_BODY_READ_TIMEOUT_SECONDS = 5.0

HeaderInput = Mapping[str, str] | Message


class AuthorizationSource(Enum):
    NONE = "none"
    BEARER = "bearer"
    BROWSER_SESSION = "browser_session"


@dataclass(frozen=True)
class AuthorizationResult:
    status: int
    source: AuthorizationSource


class RequestJsonError(Exception):
    def __init__(self, payload: dict, status: int):
        super().__init__(str(payload.get("detail", "invalid request body")))
        self.payload = payload
        self.status = status


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "OSINTAgentNetwork/0.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        session_manager = browser_session_manager()
        if parsed.path == "/api/auth/session":
            payload = session_manager.session_payload(self.headers)
            payload["required"] = authentication_required_for_environment()
            self._json(payload)
            return

        read_tokens = _configured_read_bearer_tokens()
        require_token = authentication_required_for_environment()
        if parsed.path in {"/api/health", "/api/tools/health"}:
            authorization_status = 200
        else:
            authorization_status = browser_or_bearer_authorization(
                self.headers,
                expected_tokens=read_tokens,
                known_tokens=_configured_known_bearer_tokens(),
                require_token=require_token,
                session_manager=session_manager,
                allowed_origins=_get_allowed_origins(),
                mutation=False,
            )
        if authorization_status != 200:
            self._json({"detail": "unauthorized read request"}, status=authorization_status)
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
        session_manager = browser_session_manager()
        allowed_origins = _get_allowed_origins()

        if parsed.path == "/api/auth/login":
            payload = self._read_json()
            result = session_manager.login(payload.get("admin_token", ""))
            if result is None:
                self._json({"detail": "invalid credentials"}, status=401)
                return
            self._json(
                {"authenticated": True, "csrf_token": result.csrf_token},
                headers=(("Set-Cookie", result.set_cookie),),
            )
            return

        if parsed.path == "/api/auth/logout":
            browser_principal = session_manager.authorize_session(
                self.headers, allowed_origins, mutation=False
            )
            if browser_principal is None:
                self._json({"detail": "unauthorized management request"}, status=401)
                return
            if session_manager.authorize_session(
                self.headers, allowed_origins, mutation=True
            ) is None:
                self._json({"detail": "browser mutation protection failed"}, status=403)
                return
            expired_cookie = session_manager.logout(self.headers)
            self._json(
                {"authenticated": False},
                headers=(("Set-Cookie", expired_cookie),),
            )
            return

        if parsed.path.startswith("/api/agent/"):
            agent_token = os.getenv("AGENT_API_TOKEN", "")
            authorization_status = bearer_authorization_status(
                self.headers,
                allowed_tokens=(agent_token,) if agent_token else (),
                known_tokens=_configured_known_bearer_tokens(),
                require_token=authentication_required_for_environment(),
            )
            if authorization_status != 200:
                self._json(
                    {"detail": "unauthorized agent request"},
                    status=authorization_status,
                )
                return
        elif requires_write_authorization(parsed.path):
            expected_token = os.getenv("ADMIN_API_TOKEN", "") or os.getenv("AGENT_API_TOKEN", "")
            authorization = resolve_browser_or_bearer_authorization(
                self.headers,
                expected_tokens=(expected_token,) if expected_token else (),
                known_tokens=_configured_known_bearer_tokens(),
                require_token=authentication_required_for_environment(),
                session_manager=session_manager,
                allowed_origins=allowed_origins,
                mutation=True,
            )
            if authorization.status != 200:
                if authorization.status == 403:
                    detail = (
                        "browser mutation protection failed"
                        if authorization.source is AuthorizationSource.BROWSER_SESSION
                        else "forbidden management request"
                    )
                else:
                    detail = "unauthorized management request"
                self._json({"detail": detail}, status=authorization.status)
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
        if self.headers.get_all("Transfer-Encoding", []):
            raise RequestJsonError({"detail": "invalid request framing"}, 400)
        content_lengths = self.headers.get_all("Content-Length", [])
        if not content_lengths:
            return {}
        if len(content_lengths) != 1:
            raise RequestJsonError({"detail": "invalid content length"}, 400)
        raw_length = content_lengths[0]
        if (
            not isinstance(raw_length, str)
            or not raw_length
            or not raw_length.isascii()
            or not raw_length.isdecimal()
        ):
            raise RequestJsonError({"detail": "invalid content length"}, 400)
        try:
            length = int(raw_length)
        except ValueError:
            raise RequestJsonError({"detail": "invalid content length"}, 400) from None
        max_body = _configured_max_request_body_bytes()
        if length > max_body:
            raise RequestJsonError({"detail": "request body too large"}, 413)
        if length == 0:
            return {}
        previous_timeout = self.connection.gettimeout()
        try:
            self.connection.settimeout(REQUEST_BODY_READ_TIMEOUT_SECONDS)
            try:
                raw_body = self.rfile.read(length)
            except (TimeoutError, socket.timeout):
                raise RequestJsonError(
                    {"detail": "request body read timed out"}, 408
                ) from None
        finally:
            self.connection.settimeout(previous_timeout)
        if len(raw_body) != length:
            raise RequestJsonError({"detail": "incomplete request body"}, 400)
        try:
            body = raw_body.decode("utf-8")
        except UnicodeDecodeError:
            raise RequestJsonError(
                {"detail": "request body is not valid utf-8"}, 400
            ) from None
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise RequestJsonError({"detail": "invalid json body"}, 400)
        if not isinstance(payload, dict):
            raise RequestJsonError({"detail": "json body must be an object"}, 400)
        return payload

    def _validation_failed(self, errors: list[str]) -> bool:
        if not errors:
            return False
        self._json({"detail": "validation failed", "errors": errors}, status=400)
        return True

    def _json(
        self,
        payload: dict,
        status: int = 200,
        headers: tuple[tuple[str, str], ...] = (),
    ):
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_headers(
            status,
            "application/json; charset=utf-8",
            len(encoded),
            headers,
        )
        self.wfile.write(encoded)

    def _text(self, body: str, content_type: str, status: int = 200):
        encoded = body.encode("utf-8")
        self._send_headers(status, content_type, len(encoded))
        self.wfile.write(encoded)

    def _binary(self, body: bytes, content_type: str, status: int = 200):
        self._send_headers(status, content_type, len(body))
        self.wfile.write(body)

    def _send_headers(
        self,
        status: int,
        content_type: str,
        content_length: int,
        headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        origin_values = self.headers.get_all("Origin", [])
        origin = origin_values[0] if len(origin_values) == 1 else ""
        allowed_origins = _get_allowed_origins()
        if origin and origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-CSRF-Token",
        )
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()


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


def agent_request_authorized(headers: HeaderInput, expected_token: str, require_token: bool = False) -> bool:
    return request_authorized(headers, expected_token, require_token=require_token)


def request_authorized(headers: HeaderInput, expected_token: str, require_token: bool = False) -> bool:
    expected_tokens = (expected_token,) if expected_token else ()
    return request_authorized_for_tokens(
        headers, expected_tokens, require_token=require_token
    )


def request_authorized_for_tokens(
    headers: HeaderInput,
    expected_tokens: tuple[str, ...],
    require_token: bool = False,
) -> bool:
    return bearer_authorization_status(
        headers,
        allowed_tokens=expected_tokens,
        known_tokens=expected_tokens,
        require_token=require_token,
    ) == 200


def bearer_authorization_status(
    headers: HeaderInput,
    *,
    allowed_tokens: tuple[str, ...],
    known_tokens: tuple[str, ...],
    require_token: bool,
) -> int:
    configured_allowed = tuple(token for token in allowed_tokens if token)
    configured_known = tuple(token for token in known_tokens if token)
    authorization, authorization_present = _single_header_value(
        headers, "Authorization"
    )
    if authorization is None:
        if authorization_present:
            return 401
        return 401 if configured_allowed or require_token else 200
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return 401
    supplied_token = authorization[len(prefix):]
    if _token_matches_any(supplied_token, configured_allowed):
        return 200
    if _token_matches_any(supplied_token, configured_known):
        return 403
    return 401


def browser_or_bearer_authorization(
    headers: HeaderInput,
    *,
    expected_tokens: tuple[str, ...],
    known_tokens: tuple[str, ...],
    require_token: bool,
    session_manager: BrowserSessionManager,
    allowed_origins: tuple[str, ...],
    mutation: bool,
) -> int:
    return resolve_browser_or_bearer_authorization(
        headers,
        expected_tokens=expected_tokens,
        known_tokens=known_tokens,
        require_token=require_token,
        session_manager=session_manager,
        allowed_origins=allowed_origins,
        mutation=mutation,
    ).status


def resolve_browser_or_bearer_authorization(
    headers: HeaderInput,
    *,
    expected_tokens: tuple[str, ...],
    known_tokens: tuple[str, ...],
    require_token: bool,
    session_manager: BrowserSessionManager,
    allowed_origins: tuple[str, ...],
    mutation: bool,
) -> AuthorizationResult:
    bearer_status = bearer_authorization_status(
        headers,
        allowed_tokens=expected_tokens,
        known_tokens=known_tokens,
        require_token=True,
    )
    _authorization, authorization_present = _single_header_value(
        headers, "Authorization"
    )
    if bearer_status == 200:
        return AuthorizationResult(200, AuthorizationSource.BEARER)
    if authorization_present:
        return AuthorizationResult(bearer_status, AuthorizationSource.BEARER)

    browser_principal = session_manager.authorize_session(
        headers, allowed_origins, mutation=False
    )
    if browser_principal is not None:
        if mutation and session_manager.authorize_session(
            headers, allowed_origins, mutation=True
        ) is None:
            return AuthorizationResult(403, AuthorizationSource.BROWSER_SESSION)
        return AuthorizationResult(200, AuthorizationSource.BROWSER_SESSION)

    if not any(expected_tokens) and not require_token:
        return AuthorizationResult(200, AuthorizationSource.NONE)
    return AuthorizationResult(401, AuthorizationSource.NONE)


def read_request_authorized(path: str, headers: HeaderInput, expected_token: str, require_token: bool = False) -> bool:
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


def _get_allowed_origins() -> tuple[str, ...]:
    env_value = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if env_value:
        return tuple(
            origin.strip()
            for origin in env_value.split(",")
            if origin.strip() and origin.strip() != "*"
        )
    return ("http://127.0.0.1:3008", "http://localhost:3008")


def _configured_read_bearer_tokens() -> tuple[str, ...]:
    read_and_admin_tokens = tuple(
        token
        for token in (
            os.getenv("READ_API_TOKEN", ""),
            os.getenv("ADMIN_API_TOKEN", ""),
        )
        if token
    )
    if read_and_admin_tokens:
        return read_and_admin_tokens
    agent_token = os.getenv("AGENT_API_TOKEN", "")
    return (agent_token,) if agent_token else ()


def _configured_known_bearer_tokens() -> tuple[str, ...]:
    return tuple(
        token
        for token in (
            os.getenv("ADMIN_API_TOKEN", ""),
            os.getenv("READ_API_TOKEN", ""),
            os.getenv("AGENT_API_TOKEN", ""),
        )
        if token
    )


def _single_header_value(
    headers: HeaderInput, name: str
) -> tuple[str | None, bool]:
    if isinstance(headers, Message):
        values = headers.get_all(name, [])
    else:
        expected_name = name.casefold()
        values = [
            value
            for key, value in headers.items()
            if isinstance(key, str) and key.casefold() == expected_name
        ]
    if len(values) != 1 or not isinstance(values[0], str):
        return None, bool(values)
    return values[0], True


def _token_matches_any(supplied_token: str, expected_tokens: tuple[str, ...]) -> bool:
    supplied_digest = hashlib.sha256(
        supplied_token.encode("utf-8", errors="surrogatepass")
    ).digest()
    matches = [
        hmac.compare_digest(
            hashlib.sha256(
                expected_token.encode("utf-8", errors="surrogatepass")
            ).digest(),
            supplied_digest,
        )
        for expected_token in expected_tokens
    ]
    return any(matches)


def _configured_max_request_body_bytes() -> int:
    default = 10_485_760
    try:
        configured = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(default)))
    except ValueError:
        return default
    return configured if configured >= 0 else default


def browser_session_manager() -> BrowserSessionManager:
    global _browser_session_manager, _browser_session_manager_config

    admin_token = os.getenv("ADMIN_API_TOKEN", "")
    secure_cookie = _configured_cookie_secure()
    session_ttl_seconds = _configured_session_ttl_seconds()
    config = (admin_token, secure_cookie, session_ttl_seconds)
    with _browser_session_manager_lock:
        if _browser_session_manager is None or _browser_session_manager_config != config:
            _browser_session_manager = BrowserSessionManager(
                admin_token=admin_token,
                secure_cookie=secure_cookie,
                session_ttl_seconds=session_ttl_seconds,
            )
            _browser_session_manager_config = config
        return _browser_session_manager


def _configured_cookie_secure() -> bool:
    default = str(os.getenv("APP_ENV", "")).strip().lower() in {"prod", "production"}
    value = str(os.getenv("OSINT_COOKIE_SECURE", "")).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _configured_session_ttl_seconds() -> int:
    value = str(os.getenv("OSINT_SESSION_TTL_SECONDS", "")).strip()
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return BrowserSessionManager.DEFAULT_SESSION_TTL_SECONDS
    if parsed <= 0:
        return BrowserSessionManager.DEFAULT_SESSION_TTL_SECONDS
    return parsed


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
