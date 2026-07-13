"""Opt-in acceptance runner for authorized, real investigation cohorts.

The default path validates a manifest without making HTTP requests. Network
execution is deliberately explicit because synthetic regression results cannot
establish real-world completion or generalization.
"""

from __future__ import annotations

import argparse
from collections import Counter
import ipaddress
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


SUPPORTED_SEED_TYPES = {"domain", "company", "sparse_lead"}
TERMINAL_STATUSES = {
    "ARCHIVED",
    "BLOCKED",
    "CANCELLED",
    "COMPLETED",
    "FAILED",
    "NEEDS_REVIEW",
    "PARTIAL_FAILED",
}
CONFLICT_STATUSES = {"CONFLICT", "CONFLICTED", "CONTRADICTED", "HIGH_RISK_CONFLICT"}
IDENTITY_FIELD_KEYS = {"company_identity", "decision_maker", "identity"}
VALID_REVIEWED_CONFLICT_OUTCOMES = {"false_conflict", "true_conflict"}
DEFAULT_MAX_POLLS = 12
DEFAULT_TIMEOUT_SECONDS = 30


class _NoRedirectHandler(HTTPRedirectHandler):
    """Turn redirects into HTTP errors so validated credentials stay in scope."""

    def _reject_redirect(self, req, fp, code, msg, headers):
        raise HTTPError(
            req.full_url,
            code,
            f"redirect rejected for validated base URL: {msg}",
            headers,
            fp,
        )

    http_error_301 = _reject_redirect
    http_error_302 = _reject_redirect
    http_error_303 = _reject_redirect
    http_error_307 = _reject_redirect
    http_error_308 = _reject_redirect


# Keep the request boundary patchable in tests while preventing redirect hops.
urlopen = build_opener(_NoRedirectHandler()).open


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Read a JSON manifest without making a network request."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"could not read manifest: {path}") from exc
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("manifest must contain valid JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    return manifest


def validate_manifest(manifest: object) -> dict[str, Any]:
    """Validate the small, intentionally strict real-acceptance schema."""
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    if type(manifest.get("version")) is not int or manifest.get("version") != 1:
        raise ValueError("manifest version must be 1")

    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest cases must be a nonempty list")

    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        prefix = f"case {index}"
        if not isinstance(case, dict):
            raise ValueError(f"{prefix} must be an object")

        case_id = _required_nonempty_string(case, "id", prefix)
        if case_id in seen_ids:
            raise ValueError(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)

        _required_nonempty_string(case, "name", prefix)
        seed_type = case.get("seed_type")
        if not isinstance(seed_type, str) or seed_type not in SUPPORTED_SEED_TYPES:
            raise ValueError(f"{prefix} has unsupported seed_type: {seed_type!r}")
        _required_nonempty_string(case, "seed_value", prefix)

        if type(case.get("real_target")) is not bool:
            raise ValueError(f"{prefix} real_target must be boolean")

        minimum_evidence = case.get("minimum_evidence")
        if not isinstance(minimum_evidence, list) or not minimum_evidence:
            raise ValueError(f"{prefix} minimum_evidence must be a nonempty list")
        for evidence_index, evidence_key in enumerate(minimum_evidence):
            if not isinstance(evidence_key, str) or not evidence_key.strip():
                raise ValueError(
                    f"{prefix} minimum_evidence[{evidence_index}] must be a nonempty string"
                )

    return manifest


def run_acceptance_manifest(
    manifest: object,
    *,
    execute: bool = False,
    base_url: str | None = None,
    token_env: str | None = None,
    max_polls: int = DEFAULT_MAX_POLLS,
    poll_interval: float = 0.0,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Validate or execute an authorized cohort without mutation retries."""
    validated_manifest = validate_manifest(manifest)
    cases = validated_manifest["cases"]

    if not execute:
        return _dry_run_result(len(cases))

    if not all(case["real_target"] is True for case in cases):
        raise ValueError("--execute requires every case to set real_target: true")
    normalized_base_url = _validate_base_url(base_url)
    token = _resolve_bearer_token(token_env)
    _validate_polling(max_polls, poll_interval, timeout_seconds)

    case_results = [
        _execute_case(
            case,
            base_url=normalized_base_url,
            token=token,
            max_polls=max_polls,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
        )
        for case in cases
    ]
    return _execution_result(case_results)


def _required_nonempty_string(case: dict[str, Any], field_name: str, prefix: str) -> str:
    value = case.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{prefix} {field_name} must be a nonempty string")
    return value


def _dry_run_result(case_count: int) -> dict[str, Any]:
    return {
        "suite_kind": "real_acceptance",
        "network_accessed": False,
        "executed": False,
        "benchmark_established": False,
        "result_kind": "dry_run_not_a_benchmark",
        "message": "Manifest validated without network access; this dry run cannot establish a benchmark.",
        "case_count": case_count,
        "status_counts": {},
        "completion_rate": None,
        "manual_intervention_rate": None,
        "evidence_floor_rate": None,
        "identity_conflict_rate": None,
        "reviewed_false_conflict_rate": None,
        "cases": [],
    }


def _validate_base_url(base_url: str | None) -> str:
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("--execute requires a base URL")
    parsed = urlparse(base_url.strip())
    if not parsed.scheme or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("base URL must include a scheme and hostname without credentials")
    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError("base URL must not contain params, query, or fragment")
    if parsed.scheme == "https":
        return base_url.strip().rstrip("/")
    if parsed.scheme == "http" and _is_local_http_host(parsed.hostname):
        return base_url.strip().rstrip("/")
    raise ValueError("base URL must use HTTPS or local HTTP on localhost/loopback")


def _is_local_http_host(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _resolve_bearer_token(token_env: str | None) -> str:
    if not isinstance(token_env, str) or not token_env.strip():
        raise ValueError("--execute requires --token-env")
    token = os.getenv(token_env)
    if not isinstance(token, str) or not token.strip():
        raise ValueError(f"token is missing from environment variable: {token_env}")
    return token.strip()


def _validate_polling(max_polls: int, poll_interval: float, timeout_seconds: int) -> None:
    if type(max_polls) is not int or max_polls < 1:
        raise ValueError("max_polls must be a positive integer")
    if (
        not isinstance(poll_interval, (int, float))
        or isinstance(poll_interval, bool)
        or not math.isfinite(poll_interval)
        or poll_interval < 0
    ):
        raise ValueError("poll_interval must be a finite nonnegative number")
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise ValueError("timeout_seconds must be a positive integer")


def _execute_case(
    case: dict[str, Any],
    *,
    base_url: str,
    token: str,
    max_polls: int,
    poll_interval: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "case_id": case["id"],
        "seed_type": case["seed_type"],
        "status": "UNREACHABLE",
        "completed": False,
        "manual_intervention_required": True,
        "evidence_floor_met": False,
        "identity_conflict": False,
        "reviewed_conflict_outcomes": [],
        "poll_count": 0,
    }
    create_payload = {
        "name": case["name"],
        "seed_type": case["seed_type"],
        "seed_value": case["seed_value"],
    }

    try:
        created = _request_json(
            "POST",
            f"{base_url}/api/investigations",
            create_payload,
            token=token,
            timeout_seconds=timeout_seconds,
        )
    except (HTTPError, URLError, OSError, ValueError) as exc:
        result["error"] = _error_message(exc)
        return result

    investigation_id = created.get("id")
    if not isinstance(investigation_id, str) or not investigation_id.strip():
        result["status"] = "INVALID_CREATE_RESPONSE"
        result["error"] = "create response did not contain a nonempty investigation id"
        return result
    investigation_id = investigation_id.strip()
    result["investigation_id"] = investigation_id

    try:
        run_response = _request_json(
            "POST",
            f"{base_url}/api/investigations/{quote(investigation_id, safe='')}/run-jobs",
            {},
            token=token,
            timeout_seconds=timeout_seconds,
        )
    except (HTTPError, URLError, OSError, ValueError) as exc:
        result["error"] = _error_message(exc)
        return result

    if run_response.get("accepted") is False:
        result["status"] = "RUN_NOT_ACCEPTED"
        result["error"] = "run-jobs was not accepted"
        return result

    detail_url = f"{base_url}/api/investigations/{quote(investigation_id, safe='')}"
    detail: dict[str, Any] | None = None
    for poll_index in range(max_polls):
        try:
            detail = _request_json(
                "GET",
                detail_url,
                None,
                token=token,
                timeout_seconds=timeout_seconds,
            )
        except (HTTPError, URLError, OSError, ValueError) as exc:
            result["error"] = _error_message(exc)
            return result

        result["poll_count"] = poll_index + 1
        status = _detail_status(detail)
        result["status"] = status
        if status in TERMINAL_STATUSES:
            break
        if poll_index + 1 < max_polls and poll_interval:
            time.sleep(poll_interval)

    if detail is None:
        return result
    result["completed"] = _is_completed(detail, result["status"])
    result["manual_intervention_required"] = _needs_manual_intervention(detail, result["completed"])
    result["evidence_floor_met"] = _evidence_floor_met(detail, case["minimum_evidence"])
    result["identity_conflict"] = _has_identity_conflict(detail)
    result["reviewed_conflict_outcomes"] = _reviewed_conflict_outcomes(detail)
    return result


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    *,
    token: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=timeout_seconds) as response:
        body = response.read()
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("API response must be a JSON object") from exc
    if not isinstance(decoded, dict):
        raise ValueError("API response must be a JSON object")
    return decoded


def _detail_status(detail: dict[str, Any]) -> str:
    status = str(detail.get("status") or "PENDING").strip().upper()
    return status or "PENDING"


def _is_completed(detail: dict[str, Any], status: str) -> bool:
    if status != "COMPLETED":
        return False
    policy = _completion_policy(detail)
    return policy.get("completion_mode") not in {
        "blocked_by_environment",
        "continue_collection",
        "failed",
        "ready_for_human_decision",
    }


def _needs_manual_intervention(detail: dict[str, Any], completed: bool) -> bool:
    policy = _completion_policy(detail)
    if policy.get("manual_decision_required") is True:
        return True
    return not completed


def _evidence_floor_met(detail: dict[str, Any], minimum_evidence: list[str]) -> bool:
    evidence_floor = _completion_policy(detail).get("evidence_floor")
    if not isinstance(evidence_floor, dict):
        return False
    return all(evidence_floor.get(item) is True for item in minimum_evidence)


def _has_identity_conflict(detail: dict[str, Any]) -> bool:
    rows = detail.get("cross_verification_matrix")
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict):
            continue
        field_key = str(row.get("field_key") or row.get("entity_type") or "").strip().lower()
        status = str(row.get("status") or "").strip().upper()
        if field_key in IDENTITY_FIELD_KEYS and status in CONFLICT_STATUSES:
            return True
    return False


def _reviewed_conflict_outcomes(detail: dict[str, Any]) -> list[str]:
    rows = detail.get("cross_verification_matrix")
    if not isinstance(rows, list):
        return []
    outcomes = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        outcome = str(row.get("reviewed_conflict_outcome") or "").strip().lower()
        if outcome in VALID_REVIEWED_CONFLICT_OUTCOMES:
            outcomes.append(outcome)
    return outcomes


def _completion_policy(detail: dict[str, Any]) -> dict[str, Any]:
    policy = detail.get("completion_policy")
    return policy if isinstance(policy, dict) else {}


def _error_message(exc: Exception) -> str:
    text = str(exc).strip()
    if isinstance(exc, HTTPError):
        exc.close()
    return text or exc.__class__.__name__


def _execution_result(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(result["status"] for result in case_results)
    case_count = len(case_results)
    benchmark_established = SUPPORTED_SEED_TYPES.issubset(
        {result["seed_type"] for result in case_results}
    )
    reviewed_outcomes = [
        outcome
        for result in case_results
        for outcome in result["reviewed_conflict_outcomes"]
    ]
    reviewed_false_conflict_rate = (
        None
        if not reviewed_outcomes
        else _rate(sum(outcome == "false_conflict" for outcome in reviewed_outcomes), len(reviewed_outcomes))
    )
    return {
        "suite_kind": "real_acceptance",
        "network_accessed": True,
        "executed": True,
        "benchmark_established": benchmark_established,
        "result_kind": (
            "real_acceptance_benchmark_observation"
            if benchmark_established
            else "real_acceptance_observation_not_a_benchmark"
        ),
        "message": (
            "Execution produced a comparable real acceptance benchmark observation; it does not establish generalization or perfect outcomes."
            if benchmark_established
            else "Execution produced an acceptance observation without all required real cohort types; it is not a benchmark."
        ),
        "case_count": case_count,
        "status_counts": dict(sorted(status_counts.items())),
        "completion_rate": _rate(sum(result["completed"] for result in case_results), case_count),
        "manual_intervention_rate": _rate(
            sum(result["manual_intervention_required"] for result in case_results), case_count
        ),
        "evidence_floor_rate": _rate(sum(result["evidence_floor_met"] for result in case_results), case_count),
        "identity_conflict_rate": _rate(sum(result["identity_conflict"] for result in case_results), case_count),
        "reviewed_false_conflict_rate": reviewed_false_conflict_rate,
        "cases": case_results,
    }


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate or explicitly execute real acceptance cohorts.")
    parser.add_argument("--manifest", required=True, help="Path to a version 1 acceptance manifest JSON file.")
    parser.add_argument("--execute", action="store_true", help="Allow the guarded HTTP create/run/poll flow.")
    parser.add_argument("--base-url", help="HTTPS API base URL, or local HTTP for localhost/loopback only.")
    parser.add_argument("--token-env", help="Environment variable containing the bearer token used only with --execute.")
    parser.add_argument("--max-polls", type=int, default=DEFAULT_MAX_POLLS, help="Bounded detail GET attempts per case.")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Seconds between pending polls in execute mode.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Timeout for each individual HTTP request.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        result = run_acceptance_manifest(
            manifest,
            execute=args.execute,
            base_url=args.base_url,
            token_env=args.token_env,
            max_polls=args.max_polls,
            poll_interval=args.poll_interval,
            timeout_seconds=args.timeout_seconds,
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.execute:
        return 0
    return 0 if result["completion_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
