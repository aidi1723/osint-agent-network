from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Mapping

from app.core.registry import ToolRegistry, default_tool_registry


READY = "ready"
MISSING_CONFIG = "missing_config"
MISSING_EXECUTABLE = "missing_executable"
CREDENTIAL_BLOCKED = "credential_blocked"
DISABLED = "disabled"


TOOL_CONFIG = {
    "sherlock": {
        "command_env": "SHERLOCK_COMMAND",
        "default_command": "python3",
        "optional_env": ("SHERLOCK_MODULE", "SHERLOCK_PATH"),
    },
    "maigret": {
        "command_env": "MAIGRET_COMMAND",
        "default_command": "maigret",
    },
    "socialscan": {
        "command_env": "SOCIALSCAN_COMMAND",
        "default_command": "socialscan",
    },
    "theharvester": {
        "command_env": "THEHARVESTER_COMMAND",
        "default_command": "python3",
        "path_env": "THEHARVESTER_PATH",
        "default_path": "/opt/osint/theHarvester/theHarvester.py",
    },
    "amass": {
        "command_env": "AMASS_COMMAND",
        "default_command": "amass",
    },
    "ghunt": {
        "command_env": "GHUNT_COMMAND",
        "default_command": "ghunt",
        "credential_env": "GHUNT_COOKIE_PATH",
    },
    "reconng": {
        "command_env": "RECONNG_COMMAND",
        "default_command": "recon-ng",
    },
    "company_news": {
        "command_env": "COMPANY_NEWS_COMMAND",
        "default_command": "python3",
        "optional_env": ("COMPANY_NEWS_SOURCE",),
    },
    "profile_parser": {
        "internal": True,
    },
    "lead_anchor_extraction": {
        "internal": True,
    },
    "spiderfoot": {
        "base_url_env": "SPIDERFOOT_BASE_URL",
        "optional_env": ("SPIDERFOOT_API_KEY",),
    },
    "phoneinfoga": {
        "base_url_env": "PHONEINFOGA_BASE_URL",
        "default_base_url": "http://localhost:5000",
        "optional_env": ("PHONEINFOGA_API_KEY",),
    },
}


def build_tool_health_report(
    registry: ToolRegistry | None = None,
    env: Mapping[str, str] | None = None,
) -> dict:
    registry = registry or default_tool_registry()
    env_values = env if env is not None else os.environ
    tools = [_tool_status(tool, env_values) for tool in registry.all()]
    summary = {
        "total": len(tools),
        READY: 0,
        MISSING_CONFIG: 0,
        MISSING_EXECUTABLE: 0,
        CREDENTIAL_BLOCKED: 0,
        DISABLED: 0,
    }
    for item in tools:
        summary[item["status"]] = summary.get(item["status"], 0) + 1
    summary["runnable"] = summary[READY]
    summary["attention_required"] = (
        summary[MISSING_CONFIG] + summary[MISSING_EXECUTABLE] + summary[CREDENTIAL_BLOCKED]
    )
    return {"summary": summary, "tools": tools}


def _tool_status(tool, env: Mapping[str, str]) -> dict:
    config = TOOL_CONFIG.get(tool.name, {})
    checked = _env_checked(config)
    item = {
        "name": tool.name,
        "display_name": tool.display_name,
        "execution_mode": tool.execution_mode,
        "enabled_by_default": tool.enabled_by_default,
        "requires_credentials": tool.requires_credentials,
        "status": READY,
        "reason": "",
        "env_checked": checked,
        "command": "",
        "base_url": "",
    }
    if not tool.enabled_by_default:
        item["status"] = DISABLED
        item["reason"] = "disabled by registry"
        return item
    if config.get("internal") or tool.execution_mode == "artifact_parser":
        item["reason"] = "internal adapter"
        return item
    if "base_url_env" in config:
        base_url = _env_or_default(env, config["base_url_env"], config.get("default_base_url", ""))
        item["base_url"] = _redact(base_url)
        if not base_url:
            item["status"] = MISSING_CONFIG
            item["reason"] = f"{config['base_url_env']} is not configured"
            return item
        if tool.requires_credentials and config.get("credential_env") and not env.get(config["credential_env"]):
            item["status"] = CREDENTIAL_BLOCKED
            item["reason"] = f"{config['credential_env']} is not configured"
            return item
        item["reason"] = "on-demand endpoint configured"
        return item
    command = _env_or_default(env, config.get("command_env", ""), config.get("default_command", ""))
    item["command"] = command
    if not command:
        item["status"] = MISSING_CONFIG
        item["reason"] = f"{config.get('command_env', 'command')} is not configured"
        return item
    if not _command_exists(command):
        item["status"] = MISSING_EXECUTABLE
        item["reason"] = f"executable not found: {command}"
        return item
    path_env = config.get("path_env")
    if path_env:
        configured_path = _env_or_default(env, path_env, config.get("default_path", ""))
        if configured_path and configured_path.startswith("/") and not Path(configured_path).exists():
            item["status"] = MISSING_CONFIG
            item["reason"] = f"{path_env} does not exist: {configured_path}"
            return item
    credential_env = config.get("credential_env")
    if tool.requires_credentials and credential_env and not env.get(credential_env):
        item["status"] = CREDENTIAL_BLOCKED
        item["reason"] = f"{credential_env} is not configured"
        return item
    item["reason"] = "command available"
    return item


def _env_checked(config: dict) -> list[str]:
    values = []
    for key in ("command_env", "path_env", "base_url_env", "credential_env"):
        if config.get(key):
            values.append(str(config[key]))
    values.extend(str(item) for item in config.get("optional_env", ()))
    return values


def _env_or_default(env: Mapping[str, str], key: str, default: str) -> str:
    if key and key in env:
        return str(env.get(key) or "").strip()
    return default


def _command_exists(command: str) -> bool:
    if "/" in command:
        return Path(command).exists()
    return shutil.which(command) is not None


def _redact(value: str) -> str:
    if not value:
        return ""
    return value.split("?", 1)[0]
