from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tomllib


REQUIRED_LICENSE_ID = "GPL-3.0-only"
GPLV3_NORMALIZED_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"
GENERATED_DEPENDENCY_DIRS = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", ".tox", ".venv", "__pycache__", "node_modules", "venv"}
)
RUNTIME_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})
RUNTIME_PATH_PREFIXES = (
    "backups/",
    "data/artifacts/",
    "data/backups/",
    "data/jobs/",
    "data/screenshots/",
    "data/snapshots/",
    "frontend/dist/",
    "logs/",
    "reports/",
    "runtime/",
)
RUNTIME_DATABASE_RE = re.compile(
    r"(?:\.db|\.sqlite|\.sqlite3)(?:-(?:wal|shm|journal))?$", re.IGNORECASE
)
RUNTIME_BACKUP_RE = re.compile(r"(?:\.bak|\.backup|\.old|~)$", re.IGNORECASE)
RUNTIME_LOG_RE = re.compile(r"\.log(?:\.\d+)?$", re.IGNORECASE)
PRIVATE_NETWORK_RE = re.compile(
    r"(?<![0-9.])(?:10(?:\.[0-9]{1,3}){3}|172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2}|192\.168(?:\.[0-9]{1,3}){2})(?![0-9.])"
)
PERSONAL_PATH_RE = re.compile(
    r"(?<!\w)/(?P<home>home|users)/(?P<user>[\w.<>-]+)(?:/|(?=$))",
    re.IGNORECASE,
)
ASSIGNMENT_START_RE = re.compile(
    r"(?:^|[\s,{;])(?:export\s+)?(?P<quote>['\"]?)(?P<key>[A-Za-z_][\w.-]*)(?P=quote)\s*(?P<separator>=|:(?!-))\s*",
    re.IGNORECASE,
)
BEARER_RE = re.compile(
    r"(?<![A-Za-z0-9_-])Bearer\s+(?P<value>[^\s'\"`,;)\]}]+)", re.IGNORECASE
)
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE
)
URL_USERINFO_RE = re.compile(
    r"\bhttps?://(?P<username>[A-Za-z0-9._~-]+):(?P<password>[A-Za-z0-9._~-]+)@",
    re.IGNORECASE,
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
        "your_token_here",
    }
)
ANGLE_PLACEHOLDER_RE = re.compile(
    r"(?:<redacted>|<(?=[A-Za-z0-9_-]*(?:token|password|passwd|secret|api-key|authorization|cookie))[A-Za-z0-9_-]+>)",
    re.IGNORECASE,
)
GENERATED_TOKEN_RE = re.compile(
    r"\$\((?:openssl\s+rand\s+(?:-hex|-base64)\s+\d+|uuidgen)\)"
    r"(?:['\"]?\s*>>?\s*[^\s]+)?",
    re.IGNORECASE,
)

# Exact source fixtures and policy examples may describe forbidden values without
# making those values part of a release. Each SHA-256 digest covers the complete
# source line, so moved lines remain valid but changed or adjacent lines do not.
SELF_SCAN_ALLOWLIST: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("docs/N100_DEPLOYMENT_RUNBOOK.md", "PUBLIC_CREDENTIAL_VALUE", "58eee1816a7f98ea69283d327a1a435bb007e71d36f6e248f190f70fdca422c0"),
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
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "145998fab18dfdc17bab8148777f121cf95f00ae7ca47ff30a7431bb92547810"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "1b2874b8c012ce36ff1297bcd0f8d9f009c68b61567fee546e1805d2b88036ad"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "404b8f849a7c3dfaf4759b8bd19ead961884972c2ca460881af6047d6489e4b0"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "6d96b7b5b3b0a0186e8b32f982e362d32ef960966d523a7c69392e3ca15d399e"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "c07f7f5e0a1b9fcf8e5adb6668ba6e8eed00ccedb3b1f33be94ae53f441e5fbb"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "c70e0010fd4d2865f535b6fd7b8b6f4a1cdfe2b73a4a03836aa47dd3d606cf61"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "dbb54072756e8bcc2d35aab16cd24407ed026aacfeb670fc43bccfd732eb6c41"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "8e63ddaeaa11c75773763e2f8c9f1f048f620eb6b3241a822c82609c68b16e91"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "f6fd0a0bd7038033de901e8351cca8fb93ab5f664ddc6540c90b68e173cddc78"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "323b505f31ff017233ce2671724499baf90244b9aa0e03f52010ddc4a8a0534a"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "e18e93a10eb49a76f98110ae971e8d07b140d2307260a06318db20822efc8e17"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_PERSONAL_PATH", "f6ac32f009360730bb7bd76a61d4f3602153c415fb009e560fbad52f64b27521"),
        ("scripts/healthcheck.sh", "PUBLIC_CREDENTIAL_VALUE", "f80543686d8a036596e05da4ed5c9600922737b01101a19f24205ffdb0132c4e"),
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
    git_metadata = root / ".git"
    completed = None
    if not git_metadata.is_symlink() and (git_metadata.is_file() or git_metadata.is_dir()):
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
                relative = Path(raw_path.decode("utf-8", errors="surrogateescape"))
            except ValueError:
                continue
            if _safe_regular_file(root, relative, allow_symlink=True):
                paths.append(relative)
        return sorted(paths, key=_path_sort_key)

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
    return sorted(paths, key=_path_sort_key)


def _safe_regular_file(root: Path, relative: Path, allow_symlink: bool = False) -> bool:
    if relative.is_absolute() or ".." in relative.parts:
        return False
    candidate = root / relative
    try:
        if candidate.is_symlink():
            return allow_symlink
        if not candidate.is_file():
            return False
        candidate.resolve(strict=True).relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _path_sort_key(path: Path) -> bytes:
    return path.as_posix().encode("utf-8", errors="surrogateescape")


def _display_path(path: Path | str) -> str:
    raw_path = Path(path).as_posix().encode("utf-8", errors="surrogateescape")
    decoded = raw_path.decode("utf-8", errors="backslashreplace")
    return "".join(
        f"\\x{ord(character):02x}"
        if ord(character) < 32 or ord(character) == 127
        else character
        for character in decoded
    ).replace("\\x0a", "\\n").replace("\\x0d", "\\r").replace("\\x09", "\\t")


def scan_public_text(relative_path: Path | str, text: str) -> list[ReleaseFinding]:
    path = _display_path(relative_path)
    findings: list[ReleaseFinding] = []
    lines = text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        for match in PERSONAL_PATH_RE.finditer(line):
            if match.group(0).startswith("/home/osint") and match.group("user") == "osint":
                continue
            if _named_home_placeholder(match):
                continue
            if _ellipsized_home_placeholder(line, match):
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
        for key, separator, value in _credential_assignments(line):
            if separator == ":" and _block_scalar_indicator(value):
                block_value = _yaml_block_value(lines, line_number - 1)
                if block_value and not _placeholder_credential(block_value):
                    _append_finding(
                        findings,
                        path,
                        line_number,
                        "PUBLIC_CREDENTIAL_VALUE",
                        "Credential assignment must use an explicit placeholder.",
                        line,
                    )
                continue
            if _source_code_expression(path, value):
                continue
            if not _placeholder_credential(value):
                _append_finding(
                    findings,
                    path,
                    line_number,
                    "PUBLIC_CREDENTIAL_VALUE",
                    "Credential assignment must use an explicit placeholder.",
                    line,
                )
        if PRIVATE_KEY_RE.search(line):
            _append_finding(
                findings,
                path,
                line_number,
                "PUBLIC_PRIVATE_KEY",
                "Private-key material is not allowed in a public release.",
                line,
            )
        if URL_USERINFO_RE.search(line):
            _append_finding(
                findings,
                path,
                line_number,
                "PUBLIC_URL_CREDENTIAL",
                "URL user information is not allowed in a public release.",
                line,
            )
        bearer = BEARER_RE.search(line)
        if (
            bearer
            and not _source_bearer_expression(path, bearer.group("value"))
            and _bearer_candidate(bearer.group("value"))
            and not _placeholder_credential(bearer.group("value"))
        ):
            _append_finding(
                findings,
                path,
                line_number,
                "PUBLIC_CREDENTIAL_VALUE",
                "Bearer credential must use an explicit placeholder.",
                line,
            )
    return sorted(findings, key=_finding_key)


def _ellipsized_home_placeholder(line: str, match: re.Match[str]) -> bool:
    matched = match.group(0)
    if not matched.endswith("/"):
        return False
    remainder = line[match.end() :]
    return bool(re.match(r"^\.\.\.(?:$|[\s`'\"),.;:])", remainder))


def _named_home_placeholder(match: re.Match[str]) -> bool:
    user = match.group("user")
    return user.startswith("<") and user.endswith(">")


def _credential_assignments(line: str) -> list[tuple[str, str, str]]:
    matches = list(ASSIGNMENT_START_RE.finditer(line))
    assignments = []
    for index, match in enumerate(matches):
        key = match.group("key")
        if not _credential_key(key):
            continue
        if match.group("separator") == ":":
            prefix = line[: match.start()].strip()
            if prefix and not prefix.endswith(("{", ",")):
                continue
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        value = line[match.end() : value_end].strip()
        assignments.append((key, match.group("separator"), value))
    return assignments


def _credential_key(key: str) -> bool:
    lowered = key.casefold().replace("-", "_").replace(".", "_")
    exact = {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "passwd",
        "private_key",
        "secret",
        "token",
    }
    suffixes = (
        "_api_key",
        "_authorization",
        "_cookie",
        "_password",
        "_passwd",
        "_private_key",
        "_secret",
        "_token",
    )
    if "-" in key and lowered == "tough_cookie":
        return False
    return lowered in exact or lowered.endswith(suffixes)


def _source_code_expression(path: str, value: str) -> bool:
    source_suffixes = {".cjs", ".go", ".java", ".js", ".jsx", ".mjs", ".py", ".rs", ".ts", ".tsx"}
    return Path(path).suffix.casefold() in source_suffixes


def _source_bearer_expression(path: str, value: str) -> bool:
    source_suffixes = {".cjs", ".go", ".java", ".js", ".jsx", ".mjs", ".py", ".rs", ".ts", ".tsx"}
    return Path(path).suffix.casefold() in source_suffixes and "{" in value


def _bearer_candidate(value: str) -> bool:
    normalized = value.strip()
    if _placeholder_credential(normalized):
        return True
    return (
        normalized.startswith(("ghp_", "github_pat_", "sk-"))
        or normalized.count(".") == 2
        or (
            len(normalized) >= 20
            and any(character.isdigit() for character in normalized)
            and any(character in ".-_" for character in normalized)
        )
    )


def _block_scalar_indicator(value: str) -> bool:
    return _normalize_credential_value(value) in {"|", "|-", "|+", ">", ">-", ">+"}


def _yaml_block_value(lines: list[str], header_index: int) -> str:
    header = lines[header_index]
    header_indent = len(header) - len(header.lstrip())
    values = []
    for line in lines[header_index + 1 :]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= header_indent:
            break
        values.append(line.strip())
    return "\n".join(values)


def _append_finding(
    findings: list[ReleaseFinding],
    path: str,
    line: int,
    rule_id: str,
    summary: str,
    source_line: str,
) -> None:
    signature = hashlib.sha256(source_line.encode("utf-8")).hexdigest()
    if (path, rule_id, signature) in SELF_SCAN_ALLOWLIST:
        return
    if any(
        finding.path == path and finding.line == line and finding.rule_id == rule_id
        for finding in findings
    ):
        return
    findings.append(ReleaseFinding(rule_id, path, line, summary))


def _valid_ipv4(value: str) -> bool:
    try:
        return all(0 <= int(part) <= 255 for part in value.split("."))
    except ValueError:
        return False


def _placeholder_credential(value: str) -> bool:
    normalized = _normalize_credential_value(value)
    lowered = normalized.casefold()
    if not normalized:
        return True
    if re.fullmatch(r"\$(?:[A-Za-z_][A-Za-z0-9_]*|\{[A-Za-z_][A-Za-z0-9_]*\})", normalized):
        return True
    if ANGLE_PLACEHOLDER_RE.fullmatch(normalized):
        return True
    if re.fullmatch(
        r"\{(?=[A-Za-z0-9_]*(?:TOKEN|PASSWORD|PASSWD|SECRET|API_KEY|AUTHORIZATION|COOKIE))[A-Za-z_][A-Za-z0-9_]*\}",
        normalized,
        re.IGNORECASE,
    ):
        return True
    if GENERATED_TOKEN_RE.fullmatch(normalized):
        return True
    if lowered.startswith("bearer "):
        return _placeholder_credential(normalized[7:])
    return lowered in PLACEHOLDER_VALUES


def _normalize_credential_value(value: str) -> str:
    normalized = value.strip()
    if normalized.endswith("\\"):
        normalized = normalized[:-1].rstrip()
    while normalized.endswith((",", ";")):
        normalized = normalized[:-1].rstrip()
    if normalized.endswith("}") and not normalized.startswith("${"):
        without_brace = normalized[:-1].rstrip()
        if (
            len(without_brace) >= 2
            and without_brace[0] in {"'", '"'}
            and without_brace[-1] == without_brace[0]
        ):
            normalized = without_brace
    if (
        len(normalized) >= 2
        and normalized[0] in {"'", '"'}
        and normalized[-1] == normalized[0]
    ):
        normalized = normalized[1:-1].strip()
    return normalized


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
        text = _repository_entry_text(root, relative_path)
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
    path = _display_path(relative_path)
    lower_path = path.lower()
    forbidden = relative_path.name != ".gitkeep" and (
        bool(RUNTIME_DATABASE_RE.search(relative_path.name))
        or bool(RUNTIME_BACKUP_RE.search(relative_path.name))
        or bool(RUNTIME_LOG_RE.search(relative_path.name))
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
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
    if hashlib.sha256(normalized.encode("utf-8")).hexdigest() == GPLV3_NORMALIZED_SHA256:
        return REQUIRED_LICENSE_ID
    return ""


def _package_license(path: Path) -> str:
    if path.is_symlink():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("license") or "").strip()


def _backend_license(path: Path) -> str:
    if path.is_symlink():
        return ""
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    project = payload.get("project")
    if not isinstance(project, dict):
        return ""
    return str(project.get("license") or "").strip()


def _repository_entry_text(root: Path, relative_path: Path) -> str | None:
    path = root / relative_path
    try:
        if path.is_symlink():
            return path.readlink().as_posix()
    except (OSError, ValueError):
        return None
    return _strict_text(path)


def _strict_text(path: Path) -> str | None:
    try:
        if path.is_symlink():
            return None
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
