from __future__ import annotations

import json
from pathlib import Path


_GITIGNORE_RULES = (
    ".env",
    "data/*.sqlite",
    "data/jobs/",
    "data/screenshots/",
    "data/snapshots/",
    "data/samples/",
)

_SENSITIVE_PREFIXES = (
    "data/jobs/",
    "data/screenshots/",
    "data/snapshots/",
    "data/samples/",
)


def release_findings(root: Path, tracked: list[str] | None = None) -> list[str]:
    findings: list[str] = []
    findings.extend(_port_findings(root / "docker-compose.yml"))
    findings.extend(_license_findings(root))
    findings.extend(_ignore_findings(root))
    findings.extend(_tracked_findings(tracked or []))
    return findings


def _port_findings(path: Path) -> list[str]:
    if not path.exists():
        return ["docker-compose.yml is missing"]
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip().strip("\"'")
        if ":" not in value or not any(character.isdigit() for character in value):
            continue
        host = value.split(":", 1)[0]
        if host not in {"127.0.0.1", "localhost", "::1"}:
            return ["docker compose publishes a port on all interfaces"]
    return []


def _license_findings(root: Path) -> list[str]:
    eula_path = root / "EULA.md"
    if not eula_path.exists():
        return ["EULA.md is missing"]
    eula = eula_path.read_text(encoding="utf-8").lower()
    proprietary = "licensed, not sold" in eula and "redistribute" in eula
    package_path = root / "frontend" / "package.json"
    if not package_path.exists():
        return ["frontend/package.json is missing"]
    license_name = str(json.loads(package_path.read_text(encoding="utf-8")).get("license") or "")
    if proprietary and license_name.upper().startswith("GPL"):
        return ["frontend package license conflicts with the proprietary EULA"]
    return []


def _ignore_findings(root: Path) -> list[str]:
    findings: list[str] = []
    dockerignore = _text(root / ".dockerignore")
    if "\ndata/\n" not in f"\n{dockerignore}\n" and not dockerignore.startswith("data/\n"):
        findings.append("docker build context can include investigation data")
    gitignore = _text(root / ".gitignore")
    missing = [rule for rule in _GITIGNORE_RULES if rule not in gitignore]
    if missing:
        findings.append("gitignore is missing investigation data rules: " + ", ".join(missing))
    return findings


def _tracked_findings(tracked: list[str]) -> list[str]:
    findings: list[str] = []
    for path in tracked:
        normalized = path.replace("\\", "/")
        if _is_sensitive(normalized):
            findings.append(f"tracked sensitive path: {normalized}")
    return findings


def _is_sensitive(path: str) -> bool:
    if path == ".env":
        return True
    if path.startswith(".env.") and not path.endswith(".example"):
        return True
    if path.startswith(_SENSITIVE_PREFIXES):
        return True
    return path.startswith("data/") and ".sqlite" in path


def _text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
