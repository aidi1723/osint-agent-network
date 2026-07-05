from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT_DIR = Path(__file__).resolve().parents[1]


def evaluate_readiness(
    api_health: dict,
    system_status: dict,
    tool_health: dict,
    web_ok: bool,
    backup_timer_status: str,
    auth_config: dict | None = None,
) -> dict:
    tool_summary = tool_health.get("summary") or system_status.get("tools", {}).get("health", {})
    auth_config = auth_config or {"required": False, "missing": []}
    checks = {
        "api": "ok" if api_health.get("status") == "ok" else "fail",
        "database": "ok" if system_status.get("database", {}).get("status") == "ok" else "fail",
        "web": "ok" if web_ok else "fail",
        "auth_tokens": "ok" if not auth_config.get("required") or not auth_config.get("missing") else "fail",
        "backup_script": "ok" if system_status.get("scripts", {}).get("backup", {}).get("present") else "fail",
        "healthcheck_script": "ok" if system_status.get("scripts", {}).get("healthcheck", {}).get("present") else "fail",
        "verify_script": "ok" if system_status.get("scripts", {}).get("verify", {}).get("present") else "fail",
        "tool_health_endpoint": "ok" if int(tool_summary.get("total") or 0) > 0 else "fail",
        "backup_timer": "ok" if backup_timer_status in {"enabled", "active", "unknown-local"} else "fail",
    }
    warnings = []
    if auth_config.get("required") and auth_config.get("missing"):
        warnings.append(f"missing_auth_tokens={','.join(auth_config['missing'])}")
    info = []
    attention = int(tool_summary.get("attention_required") or 0)
    ready_tools = int(tool_summary.get("ready") or 0)
    total_tools = int(tool_summary.get("total") or 0)
    if attention:
        info.append(f"tool_attention={attention}")
    if total_tools and ready_tools == 0:
        checks["tool_health_endpoint"] = "fail"
    failed = [name for name, status in checks.items() if status != "ok"]
    return {
        "ready": not failed,
        "severity": "fail" if failed else "ok",
        "checks": checks,
        "warnings": warnings,
        "info": info,
        "tool_summary": {
            "total": total_tools,
            "ready": ready_tools,
            "attention_required": attention,
        },
    }


def main() -> int:
    _load_env(ROOT_DIR / ".env")
    app_port = os.getenv("APP_PORT", "8088")
    web_port = os.getenv("WEB_PORT", "3008")
    api_url = os.getenv("API_URL", f"http://127.0.0.1:{app_port}")
    web_url = os.getenv("WEB_URL", f"http://127.0.0.1:{web_port}")
    read_token = os.getenv("READ_API_TOKEN", "") or os.getenv("ADMIN_API_TOKEN", "") or os.getenv("AGENT_API_TOKEN", "")

    api_health = _get_json(f"{api_url}/api/health")
    system_status = _get_json(f"{api_url}/api/system/status", token=read_token)
    tool_health = _get_json(f"{api_url}/api/tools/health")
    web_ok = _web_ok(web_url)
    timer_status = _backup_timer_status()
    result = evaluate_readiness(
        api_health,
        system_status,
        tool_health,
        web_ok,
        timer_status,
        auth_config=auth_config_status(os.environ),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 1


def auth_config_status(env: dict | None = None) -> dict:
    values = env if env is not None else os.environ
    explicit = str(values.get("OSINT_REQUIRE_AUTH", "")).strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        required = True
    elif explicit in {"0", "false", "no", "off"}:
        required = False
    else:
        required = str(values.get("APP_ENV", "")).strip().lower() in {"prod", "production"}
    required_tokens = ["ADMIN_API_TOKEN", "AGENT_API_TOKEN", "READ_API_TOKEN"]
    missing = [name for name in required_tokens if required and not str(values.get(name, "")).strip()]
    return {"required": required, "missing": missing}


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _get_json(url: str, token: str = "") -> dict:
    request = Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        finally:
            exc.close()
        return {"status": "error", "error": f"HTTP {exc.code}: {body[:200]}"}
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": str(exc)}


def _web_ok(url: str) -> bool:
    try:
        with urlopen(url, timeout=10) as response:
            head = response.read(512).decode("utf-8", errors="ignore")
        return "<!doctype html>" in head.lower()
    except Exception:
        return False


def _backup_timer_status() -> str:
    systemctl = shutil_which("systemctl")
    if not systemctl:
        return "unknown-local"
    completed = subprocess.run(
        [systemctl, "--user", "is-enabled", "osint-agent-network-backup.timer"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    status = completed.stdout.strip()
    if completed.returncode == 0 and status:
        return status
    return "disabled"


def shutil_which(command: str) -> str:
    path = os.environ.get("PATH", "")
    for directory in path.split(os.pathsep):
        candidate = Path(directory) / command
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
