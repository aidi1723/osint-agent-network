from __future__ import annotations

import json
import os
import time
from ipaddress import ip_address
from pathlib import Path
from urllib import request
from urllib.parse import urlencode

from app.core.normalization import normalize_target
from app.tools.base import (
    NormalizedEntity,
    NormalizedEvidence,
    NormalizedRelationship,
    ParsedToolOutput,
    ToolCommand,
    ToolRunResult,
    append_unique_entity,
    append_unique_evidence,
    append_unique_relationship,
    read_json_artifact,
    redacted_url,
    write_json_artifact,
)


class SpiderFootAdapter:
    name = "spiderfoot"
    base_confidence = 0.30

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        scan_type: str | None = None,
    ):
        self.base_url = (base_url or os.getenv("SPIDERFOOT_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("SPIDERFOOT_API_KEY", "")
        self.scan_type = scan_type or os.getenv("SPIDERFOOT_SCAN_TYPE", "passive")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type not in {"domain", "subdomain", "ip", "email", "username"}:
            raise ValueError("SpiderFoot accepts domain, subdomain, ip, email, or username targets")
        return normalize_target(target_type, target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 1800,
    ) -> ToolCommand:
        target = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        base = self.base_url or "SPIDERFOOT_BASE_URL"
        return ToolCommand(
            args=["SPIDERFOOT_REST", redacted_url(base), self.scan_type, target_type, target],
            cwd=workdir,
            expected_artifact=workdir / f"spiderfoot_{target_type}_{target}.json",
            timeout_seconds=timeout_seconds,
        )

    def run(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int) -> ToolRunResult:
        command = self.build_command(target_type, target_value, workdir, timeout_seconds)
        if not self.base_url:
            write_json_artifact(command.expected_artifact, [])
            return ToolRunResult(command, 1, "", "SPIDERFOOT_BASE_URL is not configured")
        target = self.validate_target(target_type, target_value)
        try:
            scan = self._request_json(
                "POST",
                "/startscan",
                {
                    "scanname": f"osint-agent-{target}",
                    "scantarget": target,
                    "modulelist": "",
                    "typelist": "",
                    "usecase": _spiderfoot_usecase(self.scan_type),
                },
                timeout_seconds,
            )
            scan_id = _scan_id_from_response(scan)
            if not scan_id:
                raise ValueError("SpiderFoot did not return scan_id")
            results = self._wait_for_results(scan_id, timeout_seconds)
            write_json_artifact(command.expected_artifact, results)
            return ToolRunResult(command, 0, f"SpiderFoot scan {scan_id} response saved", "")
        except Exception as exc:
            write_json_artifact(command.expected_artifact, [])
            return ToolRunResult(command, 1, "", str(exc))

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        raw = read_json_artifact(artifact_path)
        return self.parse_json(raw, target_type=_infer_target_type(target_value), target_value=target_value)

    def parse_json(self, raw, target_type: str, target_value: str) -> ParsedToolOutput:
        normalized_target = self.validate_target(target_type, target_value)
        records = raw.get("data", raw.get("results", [])) if isinstance(raw, dict) else raw
        if not isinstance(records, list):
            records = []
        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        append_unique_entity(
            entities,
            seen_entities,
            NormalizedEntity(target_type, normalized_target, self.name, self.base_confidence),
        )

        for record in records:
            mapped = _map_record(record, normalized_target)
            if mapped is None:
                continue
            entity_type, value = mapped
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity(entity_type, value, self.name, self.base_confidence),
            )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(value, "spiderfoot_event", self.name, _record_snippet(record)),
            )
            if value != normalized_target:
                append_unique_relationship(
                    relationships,
                    seen_relationships,
                    NormalizedRelationship(normalized_target, value, "target_has_finding", self.base_confidence),
                )

        return ParsedToolOutput(self.name, target_type, normalized_target, entities, evidence, relationships)

    def _request_json(self, method: str, path: str, payload: dict | None, timeout_seconds: int):
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = urlencode(payload).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        req = request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        with request.urlopen(req, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _wait_for_results(self, scan_id: str, timeout_seconds: int):
        deadline = time.monotonic() + max(5, timeout_seconds)
        status = []
        while time.monotonic() < deadline:
            status = self._request_json("GET", f"/scanstatus?id={scan_id}", None, 10)
            if isinstance(status, list) and len(status) >= 6 and str(status[5]).upper() in {"FINISHED", "ABORTED", "ERROR-FAILED"}:
                break
            time.sleep(2)
        results = self._request_json("GET", f"/scaneventresults?id={scan_id}&eventType=ALL", None, 30)
        return {"scan_id": scan_id, "status": status, "results": results}


def _infer_target_type(value: str) -> str:
    if "@" in value:
        return "email"
    try:
        normalize_target("domain", value)
        return "domain"
    except ValueError:
        return "username"


def _spiderfoot_usecase(scan_type: str) -> str:
    mapping = {
        "passive": "Footprint",
        "footprint": "Footprint",
        "investigate": "Investigate",
        "all": "All",
    }
    return mapping.get(scan_type.lower(), "Footprint")


def _scan_id_from_response(scan) -> str:
    if isinstance(scan, dict):
        return str(scan.get("scan_id") or scan.get("id") or "")
    if isinstance(scan, list) and len(scan) >= 2 and str(scan[0]).upper() == "SUCCESS":
        return str(scan[1])
    return ""


def _map_record(record, root_domain: str) -> tuple[str, str] | None:
    if not isinstance(record, dict):
        return None
    event_type = str(record.get("type") or record.get("event_type") or "").upper()
    value = str(record.get("data") or record.get("value") or "").strip()
    if not value and isinstance(record.get("row"), list):
        row = record["row"]
        event_type = str(row[1] if len(row) > 1 else "").upper()
        value = str(row[2] if len(row) > 2 else "").strip()
    if not value and isinstance(record, list):
        event_type = str(record[1] if len(record) > 1 else "").upper()
        value = str(record[2] if len(record) > 2 else "").strip()
    if not value:
        return None
    try:
        if event_type in {"EMAILADDR", "EMAIL_ADDRESS", "EMAIL"}:
            return "email", normalize_target("email", value)
        if event_type in {"INTERNET_NAME", "HOSTNAME", "DNS_NAME", "DOMAIN_NAME"}:
            host = normalize_target("domain", value)
            return ("domain" if host == root_domain else "subdomain"), host
        if event_type in {"IP_ADDRESS", "IPV4_ADDRESS", "IPV6_ADDRESS"}:
            return "ip", str(ip_address(value))
        if event_type in {"URL", "URL_WEB_CONTENT", "LINKED_URL_EXTERNAL"} and value.startswith("http"):
            return "url", value
        if event_type in {"USERNAME", "USERNAME_UNRESOLVED"}:
            return "username", normalize_target("username", value)
        if event_type in {"HUMAN_NAME", "PERSON_NAME"}:
            return "real_name", value
        if event_type in {"COMPANY_NAME", "AFFILIATE_COMPANY_NAME"}:
            return "company", value
    except ValueError:
        return None
    return None


def _record_snippet(record: dict) -> str:
    source = record.get("source") or record.get("module") or "SpiderFoot"
    event_type = record.get("type") or record.get("event_type") or "event"
    return f"{source} returned {event_type}"
