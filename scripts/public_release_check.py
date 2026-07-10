from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tomllib


REQUIRED_LICENSE_ID = "GPL-3.0-only"
GPLV3_TEXT_MARKERS = (
    "GNU GENERAL PUBLIC LICENSE",
    "Version 3, 29 June 2007",
    "Everyone is permitted to copy and distribute verbatim copies",
    "END OF TERMS AND CONDITIONS",
)
GENERATED_DEPENDENCY_DIRS = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", ".tox", ".venv", "__pycache__", "node_modules", "venv"}
)
RUNTIME_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})
RUNTIME_PATH_PREFIXES = (
    "data/artifacts/",
    "data/jobs/",
    "data/screenshots/",
    "data/snapshots/",
    "frontend/dist/",
    "reports/",
)
PRIVATE_NETWORK_RE = re.compile(
    r"(?<![0-9.])(?:10(?:\.[0-9]{1,3}){3}|172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2}|192\.168(?:\.[0-9]{1,3}){2})(?![0-9.])"
)
PERSONAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])/(?P<home>home|Users)/(?P<user>[A-Za-z0-9._-]+)/"
)
CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?:^|[\s'\"`])(?P<name>(?:[A-Z][A-Z0-9_]*_(?:TOKEN|PASSWORD|PASSWD|SECRET|API_KEY|AUTHORIZATION|COOKIE)|TOKEN|PASSWORD|PASSWD|SECRET|API_KEY|AUTHORIZATION|COOKIE))\s*=\s*(?P<value>[^#]+?)\s*$"
)
PLACEHOLDER_VALUES = frozenset(
    {
        "changeme",
        "example",
        "false",
        "placeholder",
        "redacted",
        "replace-me",
        "token",
        "true",
        "xxx",
        "your-token",
    }
)

# Exact source fixtures and policy examples may describe forbidden values without
# making those values part of a release. Each SHA-256 digest covers the complete
# source line, so moved lines remain valid but changed or adjacent lines do not.
SELF_SCAN_ALLOWLIST: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("backend/tests/test_healthcheck_script.py", "PUBLIC_CREDENTIAL_VALUE", "4868556b195cb2dc9945a2cb9428269b76052da3030fd7370bc132e871803c00"),
        ("backend/tests/test_public_release_check.py", "PUBLIC_PERSONAL_PATH", "a4979e261bbb89eff270cd17c74d301765a0289894d39c5459683414436e8499"),
        ("backend/tests/test_public_release_check.py", "PUBLIC_PRIVATE_NETWORK", "bc1c869cfcaf049634a0f0ac114e0295ee701892afb7ce2817a483449dfd5a86"),
        ("backend/tests/test_public_release_check.py", "PUBLIC_PRIVATE_NETWORK", "5c8e4502e364ae27a4e70fd4593d9e3c7966953c46ce59f3df6ad1d3ab8dc2a2"),
        ("backend/tests/test_public_release_check.py", "PUBLIC_PRIVATE_NETWORK", "07281272aec8164806527f3103c3e868a6ab2314d844a0eda57d5a9b031eb1dc"),
        ("backend/tests/test_public_release_check.py", "PUBLIC_PRIVATE_NETWORK", "7c7f595bd95b0e752de46ed4ce9dbec2136abe4af26531553e21f10a17c6f9fe"),
        ("backend/tests/test_public_release_check.py", "PUBLIC_CREDENTIAL_VALUE", "a37ec874dd9f0a21ed88f37c90e27237713b71766e53fdb8a12ab5d4cd67a0bb"),
        ("backend/tests/test_public_release_check.py", "PUBLIC_PERSONAL_PATH", "7301613e71d19a59f35cd43234fc4879cec45f338bf2dce147616c39c9604158"),
        ("backend/tests/test_report_export.py", "PUBLIC_PERSONAL_PATH", "eaf2495d0d7da16fced50337c73544172b1ad9c13d91574f1290e45976013d24"),
        ("backend/tests/test_report_export.py", "PUBLIC_PERSONAL_PATH", "0b235e1705399d615707d3509b5e87c1dcb8bd82b37ed8f67f9c9cc094baa40c"),
        ("backend/tests/test_safe_http.py", "PUBLIC_PRIVATE_NETWORK", "d830cd3a19a2874a470fa5fb2e166aa00cccd114ca12e46bf7295ba6f3bcda2c"),
        ("backend/tests/test_safe_http.py", "PUBLIC_PRIVATE_NETWORK", "63167651a0bbdf98ad38a63c76a4e1d9279de2dacbfd981122773361f6e787b2"),
        ("backend/tests/test_safe_http.py", "PUBLIC_PRIVATE_NETWORK", "91d33de501e5d3c65ed0e2a400f08374e68dfed8bfca983b41c02c2d033ccf59"),
        ("backend/tests/test_safe_http.py", "PUBLIC_PRIVATE_NETWORK", "1b156e6d22d7404aca01425362dc330e4a94622d2fc70ad88eb314686291ca09"),
        ("backend/tests/test_safe_http.py", "PUBLIC_PRIVATE_NETWORK", "a4b650cca14d16e7fe029a0053b0c3e2628d23bdbc45bc99b8759d026aedc30f"),
        ("backend/tests/test_safe_http.py", "PUBLIC_PRIVATE_NETWORK", "0363f49ad96f76277d0253975250a5e895c2d8df384293169e248b357ee68eec"),
        ("backend/tests/test_safe_http.py", "PUBLIC_PRIVATE_NETWORK", "94c0e4dff572a92ed54d07cc2e4701f888c7c8d65923ed5f3b5e5478c4882137"),
        ("docs/SECURITY_AUDIT_REMEDIATION_2026-07-10.md", "PUBLIC_PERSONAL_PATH", "d5efced1878aa795c66a093f8363f93b88c7f4860f37d0ff0177c467b6ce0924"),
        ("docs/superpowers/plans/2026-07-06-report-export-package.md", "PUBLIC_PERSONAL_PATH", "eaf2495d0d7da16fced50337c73544172b1ad9c13d91574f1290e45976013d24"),
        ("docs/superpowers/plans/2026-07-06-report-export-package.md", "PUBLIC_PERSONAL_PATH", "0b235e1705399d615707d3509b5e87c1dcb8bd82b37ed8f67f9c9cc094baa40c"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PRIVATE_NETWORK", "a2e39a9bfb5cd0f505f42c0cba0ef8fa63847e48606c3a24ad0847e79cd88eab"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PRIVATE_NETWORK", "13922ce5c1ac13997c3c35e9be5355c5ecebdb09195cf3fb4b81e41911bf7329"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PRIVATE_NETWORK", "2f5dc7a0ea7794b1f1660fd8f330cca1215c9154e7eec51301738cdc48e5fff4"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "2ace95837706c5ee2bf9199b6108f5be28fb51d781939a1221483c72fef57354"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "eec3b2985ebb2a61e346a61cf359d9af83522124daa99dda22c57555918d9a6e"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PRIVATE_NETWORK", "eec3b2985ebb2a61e346a61cf359d9af83522124daa99dda22c57555918d9a6e"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "ffaae90d211e141c8a885984cb869e1638d16d678fc51ce43e9cfa9e79349776"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "f84e9d82d95f2d0086f8d2c93e66195536b28cc12290cf02dafadd55cb17c2ce"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "8e63ddaeaa11c75773763e2f8c9f1f048f620eb6b3241a822c82609c68b16e91"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "f6fd0a0bd7038033de901e8351cca8fb93ab5f664ddc6540c90b68e173cddc78"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "323b505f31ff017233ce2671724499baf90244b9aa0e03f52010ddc4a8a0534a"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "e18e93a10eb49a76f98110ae971e8d07b140d2307260a06318db20822efc8e17"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "f6ac32f009360730bb7bd76a61d4f3602153c415fb009e560fbad52f64b27521"),
    }
)


@dataclass(frozen=True)
class ReleaseFinding:
    rule_id: str
    path: str
    line: int
    summary: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


def tracked_files(root: Path) -> list[Path]:
    root = root.resolve()
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        completed = None
    if completed is not None and completed.returncode == 0:
        paths: list[Path] = []
        for raw_path in completed.stdout.split(b"\0"):
            if not raw_path:
                continue
            try:
                relative = Path(raw_path.decode("utf-8", errors="strict"))
            except UnicodeDecodeError:
                continue
            if _safe_regular_file(root, relative):
                paths.append(relative)
        return sorted(paths, key=lambda item: item.as_posix())

    paths = []
    for candidate in root.rglob("*"):
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        if any(part in GENERATED_DEPENDENCY_DIRS for part in relative.parts):
            continue
        if _safe_regular_file(root, relative):
            paths.append(relative)
    return sorted(paths, key=lambda item: item.as_posix())


def _safe_regular_file(root: Path, relative: Path) -> bool:
    if relative.is_absolute() or ".." in relative.parts:
        return False
    candidate = root / relative
    try:
        if candidate.is_symlink() or not candidate.is_file():
            return False
        candidate.resolve(strict=True).relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def scan_public_text(relative_path: Path | str, text: str) -> list[ReleaseFinding]:
    path = Path(relative_path).as_posix()
    findings: list[ReleaseFinding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in PERSONAL_PATH_RE.finditer(line):
            if match.group("home") == "home" and match.group("user") == "osint":
                continue
            remainder = line[match.end() :]
            if re.match(r"^\.\.\.(?:$|[\s`'\"),.;:])", remainder):
                continue
            _append_finding(
                findings,
                path,
                line_number,
                "PUBLIC_PERSONAL_PATH",
                "Personal home-directory path is not allowed in a public release.",
                line,
            )
        for match in PRIVATE_NETWORK_RE.finditer(line):
            if _valid_ipv4(match.group(0)):
                _append_finding(
                    findings,
                    path,
                    line_number,
                    "PUBLIC_PRIVATE_NETWORK",
                    "Private network address is not allowed in a public release.",
                    line,
                )
        for match in CREDENTIAL_ASSIGNMENT_RE.finditer(line):
            if not _placeholder_credential(match.group("value")):
                _append_finding(
                    findings,
                    path,
                    line_number,
                    "PUBLIC_CREDENTIAL_VALUE",
                    "Credential assignment must use an explicit placeholder.",
                    line,
                )
    return sorted(findings, key=_finding_key)


def _append_finding(
    findings: list[ReleaseFinding],
    path: str,
    line: int,
    rule_id: str,
    summary: str,
    source_line: str,
) -> None:
    signature = hashlib.sha256(source_line.encode("utf-8")).hexdigest()
    if (path, rule_id, signature) not in SELF_SCAN_ALLOWLIST:
        findings.append(ReleaseFinding(rule_id, path, line, summary))


def _valid_ipv4(value: str) -> bool:
    try:
        return all(0 <= int(part) <= 255 for part in value.split("."))
    except ValueError:
        return False


def _placeholder_credential(value: str) -> bool:
    normalized = value.strip().strip("'\"`,;").strip()
    lowered = normalized.lower()
    if not normalized:
        return True
    if re.search(r"<[^>]+>", normalized):
        return True
    if normalized.startswith("${") and normalized.endswith("}"):
        return True
    if normalized.startswith("{{") and normalized.endswith("}}"):
        return True
    if normalized.startswith("$") and re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", normalized):
        return True
    if normalized.startswith("$(") and normalized.endswith(")"):
        return True
    if "$(" in normalized and ")" in normalized:
        return True
    first_word = lowered.split(maxsplit=1)[0].strip("'\"`.,;:)")
    if first_word in PLACEHOLDER_VALUES:
        return True
    final_word = lowered.rsplit(maxsplit=1)[-1]
    if final_word.startswith("your_") and final_word.endswith("_here"):
        return True
    if "canary" in lowered:
        return True
    return lowered in PLACEHOLDER_VALUES


def evaluate_public_release(root: Path) -> dict:
    root = root.resolve()
    license_text = _read_text(root / "LICENSE")
    package_license = _package_license(root / "frontend" / "package.json")
    backend_license = _backend_license(root / "backend" / "pyproject.toml")
    detected_license = _detect_license_text(license_text)
    findings: list[ReleaseFinding] = []

    if detected_license != REQUIRED_LICENSE_ID:
        findings.append(
            ReleaseFinding("LICENSE_FILE", "LICENSE", 1, "LICENSE must contain the full GNU GPL v3 text.")
        )
    if package_license != REQUIRED_LICENSE_ID:
        findings.append(
            ReleaseFinding(
                "LICENSE_FRONTEND",
                "frontend/package.json",
                1,
                "Frontend package license must be GPL-3.0-only.",
            )
        )
    if backend_license != REQUIRED_LICENSE_ID:
        findings.append(
            ReleaseFinding(
                "LICENSE_BACKEND",
                "backend/pyproject.toml",
                1,
                "Backend package license must be GPL-3.0-only.",
            )
        )

    for relative_path in tracked_files(root):
        runtime_finding = _runtime_artifact_finding(relative_path)
        if runtime_finding is not None:
            findings.append(runtime_finding)
            continue
        text = _strict_text(root / relative_path)
        if text is not None:
            findings.extend(scan_public_text(relative_path, text))

    findings.sort(key=_finding_key)
    checks = {
        "license_file": "ok" if detected_license == REQUIRED_LICENSE_ID else "fail",
        "package_license": "ok" if package_license == REQUIRED_LICENSE_ID else "fail",
        "backend_license": "ok" if backend_license == REQUIRED_LICENSE_ID else "fail",
        "license_consistency": (
            "ok"
            if detected_license == package_license == backend_license == REQUIRED_LICENSE_ID
            else "fail"
        ),
        "public_text": "ok" if not any(item.rule_id.startswith("PUBLIC_") for item in findings) else "fail",
    }
    blockers = [
        f"[{item.rule_id}] {item.path}:{item.line} {item.summary}" for item in findings
    ]
    return {
        "ready": not findings,
        "checks": checks,
        "detected_license": detected_license,
        "package_license": package_license,
        "backend_license": backend_license,
        "findings": [item.to_dict() for item in findings],
        "blockers": blockers,
    }


def _runtime_artifact_finding(relative_path: Path) -> ReleaseFinding | None:
    path = relative_path.as_posix()
    lower_path = path.lower()
    suffix = relative_path.suffix.lower()
    forbidden = relative_path.name != ".gitkeep" and (
        suffix in RUNTIME_SUFFIXES
        or lower_path.endswith((".sqlite-shm", ".sqlite-wal"))
        or any(lower_path.startswith(prefix) for prefix in RUNTIME_PATH_PREFIXES)
        or lower_path in {".env", "frontend/.env.production"}
    )
    if not forbidden:
        return None
    return ReleaseFinding(
        "PUBLIC_RUNTIME_ARTIFACT",
        path,
        0,
        "Tracked runtime artifact is not allowed in a public release.",
    )


def _finding_key(finding: ReleaseFinding) -> tuple[str, int, str, str]:
    return (finding.path, finding.line, finding.rule_id, finding.summary)


def _detect_license_text(text: str) -> str:
    if all(marker in text for marker in GPLV3_TEXT_MARKERS):
        return REQUIRED_LICENSE_ID
    return ""


def _package_license(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    return str(payload.get("license") or "").strip()


def _backend_license(path: Path) -> str:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return ""
    return str(payload.get("project", {}).get("license") or "").strip()


def _strict_text(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return None
    return None if "\0" in text else text


def _read_text(path: Path) -> str:
    return _strict_text(path) or ""


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = evaluate_public_release(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
