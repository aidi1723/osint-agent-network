from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen


ROOT_DIR = Path(__file__).resolve().parents[1]


def evaluate_readiness(
    api_health: dict,
    system_status: dict,
    tool_health: dict,
    web_ok: bool,
    backup_timer_status: str,
) -> dict:
    tool_summary = tool_health.get("summary") or system_status.get("tools", {}).get("health", {})
    checks = {
        "api": "ok" if api_health.get("status") == "ok" else "fail",
        "database": "ok" if system_status.get("database", {}).get("status") == "ok" else "fail",
        "web": "ok" if web_ok else "fail",
        "backup_script": "ok" if system_status.get("scripts", {}).get("backup", {}).get("present") else "fail",
        "healthcheck_script": "ok" if system_status.get("scripts", {}).get("healthcheck", {}).get("present") else "fail",
        "verify_script": "ok" if system_status.get("scripts", {}).get("verify", {}).get("present") else "fail",
        "tool_health_endpoint": "ok" if int(tool_summary.get("total") or 0) > 0 else "fail",
        "backup_timer": "ok" if backup_timer_status in {"enabled", "active"} else "fail",
    }
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
        "warnings": [],
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

    api_health = _get_json(f"{api_url}/api/health")
    system_status = _get_json(f"{api_url}/api/system/status")
    tool_health = _get_json(f"{api_url}/api/tools/health")
    web_ok = _web_ok(web_url)
    timer_status = _backup_timer_status()
    result = evaluate_readiness(api_health, system_status, tool_health, web_ok, timer_status)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 1


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _get_json(url: str) -> dict:
    with urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


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
