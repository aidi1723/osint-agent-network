from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tomllib


REQUIRED_LICENSE_ID = "GPL-3.0-only"
GPLV3_NORMALIZED_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"
JAVASCRIPT_SUFFIXES = frozenset({".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"})
JAVASCRIPT_AST_HELPER = Path(__file__).with_name("public_release_ast.mjs")
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
    r"(?:\.db|\.sqlite|\.sqlite3)(?:-(?:wal|shm|journal))?(?:\.gz)?$", re.IGNORECASE
)
RUNTIME_BACKUP_RE = re.compile(r"(?:\.bak|\.backup|\.old|~)$", re.IGNORECASE)
RUNTIME_LOG_RE = re.compile(r"\.log(?:\.\d+)?(?:\.gz)?$", re.IGNORECASE)
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
    r"(?<![A-Za-z0-9_-])Bearer\s+"
    r"(?![=:])(?P<value>\$?\{[A-Za-z_$][A-Za-z0-9_$]*"
    r"(?:\.[A-Za-z_$][A-Za-z0-9_$]*|\[['\"][A-Za-z_][A-Za-z0-9_]*['\"]\])*\}"
    r"|[^\s'\"`,;)\]}，。；：]+)",
    re.IGNORECASE,
)
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE
)
URL_USERINFO_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9+.-]*://"
    r"(?P<userinfo>[A-Za-z0-9._~!$&'()*+,;=:%-]+)@",
    re.IGNORECASE,
)
PLACEHOLDER_VALUES = frozenset(
    {
        "changeme",
        "credential",
        "example",
        "false",
        "fail",
        "placeholder",
        "ok",
        "off",
        "redacted",
        "replace-me",
        "token",
        "true",
        "...",
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
TEST_FIXTURE_CREDENTIAL_HASHES_BY_PATH: dict[str, frozenset[str]] = {
    "backend/tests/test_agent_auth.py": frozenset({
        "16175223c8ddce5ace0493c948569c211b03c4c6bb3d3e484434999448cffe01",
        "2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b",
        "3316348dbadfb7b11c7c2ea235949419e23f9fa898ad2c198f999617912a9925",
        "81f859a7853a6c6aa4c32e5be83bbd415a11ad99ff9fedae38281ee1d89e1e09",
        "8810ad581e59f2bc3928b261707a71308f7e139eb04820366dc4d5c18d980225",
        "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",
        "a39a67c5e6ddd5d607180e3c781bb0f62bdbfdfc66a897b603d4e670e1d41cbb",
        "cc000e626ba67bed4834794d42288b228f012823877440d2bc5a3787cc6ffce9",
        "f0fd6c09405cb6d3707d04067d8509cb924e62ae66fa02067c2bc467b0d721e4",
    }),
    "backend/tests/test_agent_client.py": frozenset({
        "0c390947fd354ea5bdf4231b34bc549d63aa67254ebc5f0d00d877c456d6c3bb",
        "307904106c9d0b5b2abeba51f4d1d94f3d77f8d8a52382cd4731db0a12612219",
        "6a011d29036329dbf8f931028a5261aacd372f52bfbc8a29d1735237248e484a",
        "b6d751546e93970143442c7294ba9559bed847676d2492b00c2fbc809bc16b94",
        "c91a3cc769f870fddc83082ba1274ed09441626dfe257c2c434684373a72e4ad",
        "d6836c01b5baf9e5a56115e086ae3875a208576b034511749985f0bb17b63742",
        "ef21d1c7da6d7e23deeae2c52c47c9b163813e48cddc992d48ff3000dc0bfbcf",
    }),
    "backend/tests/test_agent_identity_auth.py": frozenset({
        "16175223c8ddce5ace0493c948569c211b03c4c6bb3d3e484434999448cffe01",
        "648f312cf893d191028cba09f60f8ffe95624c9ef2d40a0c2f0db0e356e37e0f",
        "7de71b17706987178b1d84b2e9ce2ce40ed3f1a63a9d9a716071c3e2345eea77",
        "f0fd6c09405cb6d3707d04067d8509cb924e62ae66fa02067c2bc467b0d721e4",
    }),
    "backend/tests/test_agent_protocol.py": frozenset({
        "1fa13edd587a2bad97f18f9880c58ee74212d298e127d15e52127e1cbf123b0c",
    }),
    "backend/tests/test_browser_auth.py": frozenset({
        "0535db08797e7f1f47348a64480b933620fe87c6a965cab62787c9a62d68684d",
        "16175223c8ddce5ace0493c948569c211b03c4c6bb3d3e484434999448cffe01",
        "4530d17b2e02de0145531ae4b5b62e504e7612316ea27348e9b9fab63f178499",
        "7a74316cbd7bff4ff5254596c29c3985b4479d1491e7711e8a16860a5f69cd5d",
        "8810ad581e59f2bc3928b261707a71308f7e139eb04820366dc4d5c18d980225",
        "8b6f210d19b901c1f28182760db2450e6a3209354923cd8b09e649f09f17abe6",
        "bbd3bb4ec39b07f215d1c58c1faed306dcbf5caad8c538c6c1e1ad9c46001923",
        "d67e2e944994496c8d8ec76eed0cf9f09679448d584b532bebf941852a37f5ed",
        "f1d9cb4151761d2cb60eace21765b6c7b616bcce35f0ad74c95667c35c3466ff",
        "fb881b8333ba364435f8ec2b6a1dd6d0f81ecdbe7372da2829e5197643fa81a2",
    }),
    "backend/tests/test_customs_api_route.py": frozenset({
        "16175223c8ddce5ace0493c948569c211b03c4c6bb3d3e484434999448cffe01",
    }),
    "backend/tests/test_healthcheck_script.py": frozenset({
        "364c654dcb00148e3f3e82a87a1540a094e874a50ee97b9ea1f30547a8425ab9",
    }),
    "backend/tests/test_llm_client.py": frozenset({
        "6a34e9cf66e854e6e1b79ceebaac12897fd6845a57d2cf367ca33a74fdbc1afb",
        "e2d349dc4d34e58532d4e162998448e6d958ef1f3bfba65dd8ddcc513704e4c0",
    }),
    "backend/tests/test_production_readiness.py": frozenset({
        "3316348dbadfb7b11c7c2ea235949419e23f9fa898ad2c198f999617912a9925",
        "81f859a7853a6c6aa4c32e5be83bbd415a11ad99ff9fedae38281ee1d89e1e09",
        "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",
        "a39a67c5e6ddd5d607180e3c781bb0f62bdbfdfc66a897b603d4e670e1d41cbb",
        "f0fd6c09405cb6d3707d04067d8509cb924e62ae66fa02067c2bc467b0d721e4",
    }),
    "backend/tests/test_upkuajing_customs.py": frozenset({
        "2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b",
    }),
    "frontend/src/api.test.ts": frozenset({
        "3f6f36ef4d060436a9ebe8029c2ae4566c983c31afadb2ca5f6a25d0b56d43a1",
        "677c8e9c78d800b49c65f355300cdb087555c05bf8392e114fa973f767823ce8",
    }),
    "frontend/src/auth.test.ts": frozenset({
        "26143e7e04e9b21b16c199bec7536fb05325e5f9f9eb82a26b36e74819e7cb23",
        "3f6f36ef4d060436a9ebe8029c2ae4566c983c31afadb2ca5f6a25d0b56d43a1",
        "90dbafc65a833aca47d839c3e6b879ba420db258087347b34340ff6b4789a174",
        "ec585b7be286a5088d8687af4ce027f389cd098e2bb0dee876d5521fa4468f59",
    }),
    "frontend/src/main.test.tsx": frozenset({
        "6830e85a6f2b0f09b1d1883ccef2e6a419b3fe4d9b16fb6ce2c0f95a9b03db58",
        "90dbafc65a833aca47d839c3e6b879ba420db258087347b34340ff6b4789a174",
    }),
}

# Exact source fixtures and policy examples may describe forbidden values without
# making those values part of a release. Each SHA-256 digest covers the complete
# source line, so moved lines remain valid but changed or adjacent lines do not.
SELF_SCAN_ALLOWLIST: dict[tuple[str, str, str], int] = {
    entry: 1
    for entry in (
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
        ("docs/PUBLIC_REPOSITORY_MAINTENANCE.md", "PUBLIC_CREDENTIAL_VALUE", "fd6f58da3ae12e5d79c2a341e9d73e91a042cd788f381935b8a735df868b121c"),
        ("docs/SECURITY_AUDIT_REMEDIATION_2026-07-10.md", "PUBLIC_CREDENTIAL_VALUE", "e1dacf78e71b54522438fa232b515cd07143dfe8f3f28c3a3b6a52c83209907b"),
        ("docs/superpowers/plans/2026-07-06-evidence-shortfall-completion-policy.md", "PUBLIC_CREDENTIAL_VALUE", "d61b19d18fab16bb3f9fc002f75c53ecc18d7c3e808b6ee8f25a228418ce968d"),
        ("docs/superpowers/plans/2026-07-06-gap-to-tool-followup-planner.md", "PUBLIC_CREDENTIAL_VALUE", "92188f3b0089e838e73c6a34dab970f8ddd564365ff8c04f1a0a6d1cf0caf42d"),
        ("docs/superpowers/plans/2026-07-06-official-site-decision-maker-extraction.md", "PUBLIC_CREDENTIAL_VALUE", "70222fbddb4576f12eaa01d81bb0e8a95ce74497eac01e038d1f2477ed9f630d"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "3ea1c4216aef2f91510b17d8ad95edb3fcf300e5788231840625a15bafa21df5"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "4a363fc2abbc13211b4a7a8c1f04edd9e80906e7b80eb923c4e05d5081b2b45d"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "ed568beb23804a3ddbdc5c89bf2b3b039d3a2ff1663af85f7b61fdd5fc4da708"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "6796c01b999b73841ca5d49fd6457b06c451863bd60e85fc7b12e42447769774"),
        ("docs/superpowers/plans/2026-07-10-security-hardening.md", "PUBLIC_CREDENTIAL_VALUE", "a9175c2137bae7cc39dbf9c2549700ba50d648265a593d26dfdf407cfe63f61b"),
        ("docs/superpowers/specs/2026-07-06-gap-to-tool-followup-planner-design.md", "PUBLIC_CREDENTIAL_VALUE", "7f6349f52fa2e9d23b62dbd53046ad8e16d21d82b259aac0e1f9af06b51128c9"),
        ("docs/superpowers/specs/2026-07-06-real-sample-regression-pack-design.md", "PUBLIC_CREDENTIAL_VALUE", "16b40b8e09389d53ed423d34afbcab22f6a8d7484f78588b7b812628602804a9"),
        ("docs/superpowers/specs/2026-07-06-report-export-package-design.md", "PUBLIC_CREDENTIAL_VALUE", "f11c96aa46d33d933edcac8e0c16c34d6a52ed5443124cea59766c632da60e90"),
        ("docs/superpowers/specs/2026-07-10-security-hardening-design.md", "PUBLIC_CREDENTIAL_VALUE", "46a9eff617d13f00760b48d26333233d8a03ef555d545673136ae16759c1bd3a"),
        ("docs/superpowers/specs/2026-07-10-security-hardening-design.md", "PUBLIC_CREDENTIAL_VALUE", "eb81caeb2ebbf1dd6e43ab17c38758716f081f8121a32f431d56728986f2015d"),
        ("docs/superpowers/specs/2026-07-10-security-hardening-design.md", "PUBLIC_CREDENTIAL_VALUE", "b58a6ab80125bd1f347e185ba44671be04f3699a8a03b6859a60c2d61b272db6"),
        ("docs/superpowers/specs/2026-07-10-security-hardening-design.md", "PUBLIC_CREDENTIAL_VALUE", "1ba02141a5f15360c152d30ca4935a21bd9f786170041d024bd858d156434c07"),
        ("scripts/healthcheck.sh", "PUBLIC_CREDENTIAL_VALUE", "f80543686d8a036596e05da4ed5c9600922737b01101a19f24205ffdb0132c4e"),
    )
} | {
    (
        "backend/tests/test_safe_http.py",
        "PUBLIC_PRIVATE_NETWORK",
        "1b156e6d22d7404aca01425362dc330e4a94622d2fc70ad88eb314686291ca09",
    ): 2,
}


@dataclass(frozen=True)
class ReleaseFinding:
    rule_id: str
    path: str
    line: int
    summary: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True)
class JavaScriptAstFile:
    assignments: dict[int, list[tuple[str, str, str, bool]]]
    pure_string_literals: tuple[tuple[int, int], ...]
    error_line: int | None = None


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


def scan_public_text(
    relative_path: Path | str,
    text: str,
    *,
    javascript_ast: JavaScriptAstFile | None = None,
) -> list[ReleaseFinding]:
    path = _display_path(relative_path)
    suffix = Path(path).suffix.casefold()
    python_assignments = _python_credential_assignments(text) if suffix == ".py" else None
    if suffix in JAVASCRIPT_SUFFIXES and javascript_ast is None:
        javascript_ast = _javascript_ast_batch([(path, text)])[path]
    javascript_assignments = javascript_ast.assignments if javascript_ast else None
    findings: list[ReleaseFinding] = []
    allowlist_occurrences: dict[tuple[str, str, str], int] = {}
    evaluated_locations: set[tuple[str, int, str]] = set()
    userinfo_separator = ":"
    lines = text.splitlines()
    line_offsets = _line_offsets(text)
    pure_string_literals = (
        javascript_ast.pure_string_literals
        if javascript_ast is not None
        else _python_pure_string_literals(text) if suffix == ".py" else ()
    )
    if javascript_ast is not None and javascript_ast.error_line is not None:
        findings.append(
            ReleaseFinding(
                "PUBLIC_CREDENTIAL_SCAN",
                path,
                javascript_ast.error_line,
                "JavaScript credential scan could not parse this source file.",
            )
        )
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
                allowlist_occurrences,
                evaluated_locations,
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
                    allowlist_occurrences,
                    evaluated_locations,
                )
        if python_assignments is not None:
            assignments = python_assignments.get(line_number, [])
        elif javascript_assignments is not None:
            assignments = javascript_assignments.get(line_number, [])
        else:
            assignments = _credential_assignments(line)
        for assignment in assignments:
            key, separator, value = assignment[:3]
            if len(assignment) == 4 and assignment[3]:
                continue
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
                        allowlist_occurrences,
                        evaluated_locations,
                    )
                continue
            if separator not in {"=", ":"}:
                _append_finding(
                    findings,
                    path,
                    line_number,
                    "PUBLIC_CREDENTIAL_VALUE",
                    "Credential assignment must use an explicit placeholder.",
                    line,
                    allowlist_occurrences,
                    evaluated_locations,
                )
                continue
            if _test_fixture_credential(path, value):
                continue
            if _safe_source_credential_rhs(path, key, value):
                continue
            if not _placeholder_credential(value):
                _append_finding(
                    findings,
                    path,
                    line_number,
                    "PUBLIC_CREDENTIAL_VALUE",
                    "Credential assignment must use an explicit placeholder.",
                    line,
                    allowlist_occurrences,
                    evaluated_locations,
                )
        if PRIVATE_KEY_RE.search(line):
            _append_finding(
                findings,
                path,
                line_number,
                "PUBLIC_PRIVATE_KEY",
                "Private-key material is not allowed in a public release.",
                line,
                allowlist_occurrences,
                evaluated_locations,
            )
        for url_userinfo in URL_USERINFO_RE.finditer(line):
            _username, separator, password = url_userinfo.group("userinfo").partition(
                userinfo_separator
            )
            if separator and password and not _placeholder_credential(password):
                _append_finding(
                    findings,
                    path,
                    line_number,
                    "PUBLIC_URL_CREDENTIAL",
                    "URL user information is not allowed in a public release.",
                    line,
                    allowlist_occurrences,
                    evaluated_locations,
                )
        for authorization_match in BEARER_RE.finditer(line):
            value = authorization_match.group("value")
            absolute_start = line_offsets[line_number - 1] + authorization_match.start()
            absolute_end = line_offsets[line_number - 1] + authorization_match.end()
            if (
                _placeholder_credential(value)
                or _dynamic_bearer_reference(value)
                or _test_fixture_bearer(
                    path,
                    text,
                    absolute_start,
                    absolute_end,
                    value,
                    pure_string_literals,
                )
            ):
                continue
            _append_finding(
                findings,
                path,
                line_number,
                "PUBLIC_CREDENTIAL_VALUE",
                "Bearer credential must use an explicit placeholder.",
                line,
                allowlist_occurrences,
                evaluated_locations,
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


def _javascript_ast_batch(
    files: list[tuple[str, str]],
) -> dict[str, JavaScriptAstFile]:
    failed = {
        path: JavaScriptAstFile({}, (), 1)
        for path, _text in files
    }
    if not files:
        return failed
    payload = json.dumps(
        {"files": [{"path": path, "text": text} for path, text in files]}
    ).encode("utf-8")
    try:
        completed = subprocess.run(
            ["node", str(JAVASCRIPT_AST_HELPER)],
            check=False,
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return failed
    if completed.returncode != 0:
        return failed
    try:
        output = json.loads(completed.stdout.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return failed
    records = output.get("files") if isinstance(output, dict) else None
    if not isinstance(records, list):
        return failed

    results: dict[str, JavaScriptAstFile] = {}
    requested_texts = dict(files)
    requested_paths = set(requested_texts)
    for record in records:
        parsed = _javascript_ast_record(record, requested_texts)
        if parsed is None:
            continue
        path, ast_file = parsed
        if path in results:
            return failed
        results[path] = ast_file
    if results.keys() != requested_paths:
        return failed
    return results


def _javascript_ast_record(
    record: object, requested_texts: dict[str, str]
) -> tuple[str, JavaScriptAstFile] | None:
    if not isinstance(record, dict):
        return None
    path = record.get("path")
    if not isinstance(path, str) or path not in requested_texts:
        return None
    if record.get("ok") is not True:
        error_line = record.get("errorLine")
        return path, JavaScriptAstFile(
            {}, (), error_line if isinstance(error_line, int) and error_line > 0 else 1
        )
    raw_assignments = record.get("assignments")
    raw_literals = record.get("pureStringLiterals")
    if not isinstance(raw_assignments, list) or not isinstance(raw_literals, list):
        return None
    source_text = requested_texts[path]
    offset_map = _utf16_offset_map(source_text)
    assignments: dict[int, list[tuple[str, str, str, bool]]] = {}
    for assignment in raw_assignments:
        if not isinstance(assignment, dict):
            return None
        line = assignment.get("line")
        key = assignment.get("key")
        operator = assignment.get("operator")
        start = assignment.get("start")
        end = assignment.get("end")
        safe_initializer = assignment.get("safeInitializer")
        if (
            not isinstance(line, int)
            or line < 1
            or not isinstance(key, str)
            or not isinstance(operator, str)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or start not in offset_map
            or end not in offset_map
            or not isinstance(safe_initializer, bool)
        ):
            return None
        if _credential_key(key):
            value = source_text[offset_map[start] : offset_map[end]]
            assignments.setdefault(line, []).append(
                (key, operator, value, safe_initializer)
            )
    literals: list[tuple[int, int]] = []
    for literal in raw_literals:
        if not isinstance(literal, dict):
            return None
        start = literal.get("start")
        end = literal.get("end")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or start not in offset_map
            or end not in offset_map
        ):
            return None
        literals.append((offset_map[start], offset_map[end]))
    return path, JavaScriptAstFile(assignments, tuple(literals))


def _utf16_offset_map(text: str) -> dict[int, int]:
    offsets = {0: 0}
    utf16_offset = 0
    for index, character in enumerate(text, start=1):
        utf16_offset += 2 if ord(character) > 0xFFFF else 1
        offsets[utf16_offset] = index
    return offsets


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    offsets.extend(match.end() for match in re.finditer("\n", text))
    return offsets


def _python_pure_string_literals(text: str) -> tuple[tuple[int, int], ...]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ()
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    offsets = _line_offsets(text)
    literals = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _python_string_expression_is_pure(node, parents)
            and hasattr(node, "end_lineno")
            and hasattr(node, "end_col_offset")
        ):
            start = offsets[node.lineno - 1] + node.col_offset
            end = offsets[node.end_lineno - 1] + node.end_col_offset
            literals.append((start, end))
    return tuple(literals)


def _python_string_expression_is_pure(
    node: ast.Constant, parents: dict[ast.AST, ast.AST]
) -> bool:
    parent = parents.get(node)
    if parent is None or isinstance(parent, ast.Expr):
        return True
    if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.Return)):
        return getattr(parent, "value", None) is node
    if isinstance(parent, ast.keyword):
        return parent.value is node
    if isinstance(parent, ast.Call):
        return node in parent.args
    if isinstance(parent, ast.Compare):
        return parent.left is node or node in parent.comparators
    if isinstance(parent, (ast.List, ast.Set, ast.Tuple)):
        return node in parent.elts
    if isinstance(parent, ast.Dict):
        return node in parent.values
    return False


def _python_credential_assignments(
    text: str,
) -> dict[int, list[tuple[str, str, str]]] | None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None

    visitor = _PythonCredentialVisitor(text)
    visitor.visit(tree)
    return visitor.assignments


class _PythonCredentialVisitor(ast.NodeVisitor):
    def __init__(self, text: str):
        self.text = text
        self.assignments: dict[int, list[tuple[str, str, str]]] = {}

    def _add(self, key: str | None, value: ast.AST, line: int, separator: str = "=") -> None:
        if key is None or not _credential_key(key):
            return
        source = ast.get_source_segment(self.text, value)
        if source is not None:
            self.assignments.setdefault(line, []).append((key, separator, source))

    def _add_defaults(self, arguments: ast.arguments) -> None:
        positional = [*arguments.posonlyargs, *arguments.args]
        default_args = positional[len(positional) - len(arguments.defaults) :]
        for argument, default in zip(default_args, arguments.defaults):
            self._add(argument.arg, default, argument.lineno)
        for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults):
            if default is not None:
                self._add(argument.arg, default, argument.lineno)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            for key in _python_assignment_keys(target):
                self._add(key, node.value, target.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            for key in _python_assignment_keys(node.target):
                self._add(key, node.value, node.target.lineno)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        for key in _python_assignment_keys(node.target):
            self._add(key, node.value, node.target.lineno)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        for key in _python_assignment_keys(node.target):
            self._add(key, node.value, node.target.lineno, type(node.op).__name__)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add_defaults(node.args)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add_defaults(node.args)
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._add_defaults(node.args)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for keyword in node.keywords:
            self._add(keyword.arg, keyword.value, keyword.value.lineno)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key_node, value_node in zip(node.keys, node.values):
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                self._add(key_node.value, value_node, key_node.lineno)
        self.generic_visit(node)


def _python_assignment_keys(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Attribute):
        return [target.attr]
    if isinstance(target, ast.Subscript):
        key = target.slice
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            return [key.value]
    if isinstance(target, (ast.List, ast.Tuple)):
        return [key for item in target.elts for key in _python_assignment_keys(item)]
    return []


def _quoted_source_rhs(value: str) -> bool:
    return bool(re.match(r"^(?:[rubfRUBF]{0,3}['\"]|`)", value.strip()))


def _credential_key(key: str) -> bool:
    snake_key = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    normalized_keys = {
        candidate.casefold().replace("-", "_").replace(".", "_")
        for candidate in (key, snake_key)
    }
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
        "_access_key",
        "_access_key_id",
        "_api_key",
        "_authorization",
        "_cookie",
        "_credential",
        "_credentials",
        "_password",
        "_pat",
        "_passwd",
        "_private_key",
        "_secret",
        "_token",
    )
    if "gap_token" in normalized_keys:
        return False
    if "-" in key and "tough_cookie" in normalized_keys:
        return False
    return any(
        lowered in exact or lowered.endswith(suffixes)
        for lowered in normalized_keys
    )


def _safe_source_credential_rhs(path: str, key: str, value: str) -> bool:
    source_suffixes = {".cjs", ".go", ".java", ".js", ".jsx", ".mjs", ".py", ".rs", ".ts", ".tsx"}
    suffix = Path(path).suffix.casefold()
    if suffix not in source_suffixes:
        return False
    if suffix == ".py":
        expression = _parse_python_expression(value)
        return expression is not None and _safe_python_credential_expression(
            expression
        )
    if _placeholder_credential(value):
        return True

    raw = value.strip()
    while raw.endswith((",", ";")):
        raw = raw[:-1].rstrip()
    identifier = (
        r"[A-Za-z_$][A-Za-z0-9_$]*"
        r"(?:\.[A-Za-z_$][A-Za-z0-9_$]*|\[['\"][A-Za-z_][A-Za-z0-9_]*['\"]\])*"
    )
    bearer_scheme = "Bear" + "er"
    dynamic_bearer_patterns = (
        rf"f(['\"]){bearer_scheme} \{{{identifier}\}}\1",
        rf"`{bearer_scheme} \$\{{{identifier}\}}`",
        rf"(['\"]){bearer_scheme} \1\s*\+\s*{identifier}",
    )
    if any(re.fullmatch(pattern, raw) for pattern in dynamic_bearer_patterns):
        return True
    if re.fullmatch(
        r"['\"](?:ok|fail)['\"]\s+if\b.+\s+else\s+['\"](?:ok|fail)['\"]",
        raw,
    ):
        return True
    if _quoted_source_rhs(raw):
        return False

    identifier = r"[A-Za-z_$][A-Za-z0-9_$]*"
    string_key = r"['\"][A-Za-z_][A-Za-z0-9_]*['\"]"
    safe_patterns = (
        rf"{identifier}(?:\.{identifier})*",
        rf"os\.getenv\(\s*{string_key}(?:\s*,\s*['\"]['\"])?\s*\)",
        rf"os\.environ(?:\[\s*{string_key}\s*\]|\.get\(\s*{string_key}(?:\s*,\s*['\"]['\"])?\s*\))",
        rf"(?:process|import\.meta)\.env(?:\.{identifier}|\[\s*{string_key}\s*\])",
        r"secrets\.(?:token_bytes|token_hex|token_urlsafe)\(\s*\d*\s*\)",
        r"uuid\.uuid4\(\s*\)",
        r"crypto\.randomUUID\(\s*\)",
        r"crypto\.randomBytes\(\s*\d+\s*\)(?:\.toString\(\s*['\"](?:base64|base64url|hex)['\"]\s*\))?",
        rf"authenticatedCsrfToken\(\s*{identifier}(?:\.{identifier})*\s*\)",
    )
    if any(re.fullmatch(pattern, raw) for pattern in safe_patterns):
        return True
    return False


def _parse_python_expression(value: str) -> ast.AST | None:
    try:
        return ast.parse(f"({value})", mode="eval").body
    except SyntaxError:
        return None


def _safe_python_credential_expression(node: ast.AST) -> bool:
    environment_calls = {"os.environ.get", "os.getenv"}
    generator_calls = {
        "_allocate_agent_token",
        "generate_agent_token",
        "secrets.token_bytes",
        "secrets.token_hex",
        "secrets.token_urlsafe",
        "self._generate_unique_token",
        "uuid.uuid4",
    }
    accessor_calls = {
        "SimpleCookie",
        "Message",
        "_active_tokens_locked",
        "_configured_cookie_secure",
        "_configured_known_bearer_tokens",
        "_env_true",
        "_single_header_value",
        "authentication_required_for_environment",
        "cookie_from_set_cookie",
        "cookie_header",
        "generate_agent_token",
        "header_value",
        "json_payload",
        "logged_in_manager",
        "manager.logout",
        "request.headers.get",
        "resolve_browser_or_bearer_authorization",
        "self._active_tokens_locked",
        "self._header",
        "self.login",
        "self._set_cookie",
        "session_manager.logout",
        "group",
        "partition",
    }
    selector_strings = {
        "ADMIN_API_TOKEN",
        "Authorization",
        "Cookie",
        "OSINT_ALLOW_LEGACY_AGENT_TOKEN",
        "Set-Cookie",
        "admin_token",
        "cookie",
        "csrf_token",
        "userinfo",
        ":",
    }

    def direct_reference(expression: ast.AST) -> bool:
        if isinstance(expression, ast.Name):
            return True
        if isinstance(expression, ast.Attribute):
            return direct_reference(expression.value)
        if isinstance(expression, ast.Subscript):
            return direct_reference(expression.value)
        return False

    def safe_argument(expression: ast.AST) -> bool:
        if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
            return expression.value in selector_strings or _placeholder_credential(
                expression.value
            )
        if isinstance(expression, ast.Dict):
            return all(
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value in selector_strings
                and safe(value)
                for key, value in zip(expression.keys, expression.values)
            )
        return safe(expression)

    def safe_call(expression: ast.Call) -> bool:
        name = _python_qualified_name(expression.func)
        receiver = expression.func.value if isinstance(expression.func, ast.Attribute) else None
        receiver_safe = receiver is None or safe(receiver)
        if name in environment_calls or name.endswith(".get"):
            if not receiver_safe or not 1 <= len(expression.args) <= 2 or expression.keywords:
                return False
            lookup_key = expression.args[0]
            if not isinstance(lookup_key, ast.Constant) or not isinstance(
                lookup_key.value, str
            ):
                return False
            return len(expression.args) == 1 or safe(expression.args[1])
        if name in generator_calls:
            return receiver_safe and all(safe(item) for item in expression.args) and all(
                keyword.arg is not None and safe(keyword.value)
                for keyword in expression.keywords
            )
        if name in accessor_calls or name.endswith((".group", ".partition")):
            return receiver_safe and all(safe_argument(item) for item in expression.args) and all(
                keyword.arg is not None and safe_argument(keyword.value)
                for keyword in expression.keywords
            )
        if name.endswith((".items", ".keys", ".values")):
            return receiver_safe and not expression.args and not expression.keywords
        return False

    def safe_dynamic_bearer(expression: ast.JoinedStr) -> bool:
        if len(expression.values) != 2:
            return False
        prefix, reference = expression.values
        return (
            isinstance(prefix, ast.Constant)
            and prefix.value == "Bearer "
            and isinstance(reference, ast.FormattedValue)
            and reference.conversion == -1
            and reference.format_spec is None
            and direct_reference(reference.value)
        )

    def safe(expression: ast.AST) -> bool:
        if isinstance(expression, ast.Constant):
            if isinstance(expression.value, str):
                return _placeholder_credential(expression.value)
            return expression.value is None or isinstance(
                expression.value, (bool, int, float)
            )
        if direct_reference(expression):
            return True
        if isinstance(expression, ast.Subscript):
            return safe(expression.value)
        if isinstance(expression, ast.BoolOp):
            return all(safe(item) for item in expression.values)
        if isinstance(expression, ast.IfExp):
            return safe(expression.body) and safe(expression.orelse)
        if isinstance(expression, ast.Compare):
            return safe(expression.left) and all(
                safe(item) for item in expression.comparators
            )
        if isinstance(expression, ast.JoinedStr):
            return safe_dynamic_bearer(expression)
        if isinstance(expression, ast.UnaryOp):
            return safe(expression.operand)
        if isinstance(expression, (ast.List, ast.Set, ast.Tuple)):
            return all(safe(item) for item in expression.elts)
        if isinstance(expression, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
            return safe(expression.elt) and all(
                safe(generator.iter)
                and all(safe(condition) for condition in generator.ifs)
                for generator in expression.generators
            )
        if isinstance(expression, ast.Call):
            return safe_call(expression)
        return False

    return safe(node)


def _python_qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _python_qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


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
    allowlist_occurrences: dict[tuple[str, str, str], int],
    evaluated_locations: set[tuple[str, int, str]],
) -> None:
    location = (path, line, rule_id)
    if location in evaluated_locations:
        return
    evaluated_locations.add(location)
    signature = hashlib.sha256(source_line.encode("utf-8")).hexdigest()
    allowlist_key = (path, rule_id, signature)
    occurrence = allowlist_occurrences.get(allowlist_key, 0) + 1
    allowlist_occurrences[allowlist_key] = occurrence
    if occurrence <= SELF_SCAN_ALLOWLIST.get(allowlist_key, 0):
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


def _test_fixture_credential(path: str, value: str) -> bool:
    allowed_hashes = TEST_FIXTURE_CREDENTIAL_HASHES_BY_PATH.get(path)
    if not allowed_hashes:
        return False
    expression = _parse_python_expression(value)
    if not isinstance(expression, ast.Constant) or not isinstance(expression.value, str):
        return False
    normalized = expression.value.strip()
    if normalized.casefold().startswith("bearer "):
        normalized = normalized[7:].strip()
    signature = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return signature in allowed_hashes


def _test_fixture_bearer(
    path: str,
    text: str,
    occurrence_start: int,
    occurrence_end: int,
    value: str,
    pure_string_literals: tuple[tuple[int, int], ...],
) -> bool:
    allowed_hashes = TEST_FIXTURE_CREDENTIAL_HASHES_BY_PATH.get(path)
    if not allowed_hashes:
        return False
    signature = hashlib.sha256(value.strip().encode("utf-8")).hexdigest()
    if signature not in allowed_hashes:
        return False
    for start, end in pure_string_literals:
        if start <= occurrence_start and occurrence_end <= end:
            literal = text[start:end]
            return re.fullmatch(
                rf"(?:[rubRUB]{{0,3}})?(?P<quote>['\"])Bearer\s+{re.escape(value)}(?P=quote)",
                literal,
                re.IGNORECASE,
            ) is not None
    return False


def _dynamic_bearer_reference(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"\$?\{[A-Za-z_$][A-Za-z0-9_$]*"
            r"(?:\.[A-Za-z_$][A-Za-z0-9_$]*|\[['\"][A-Za-z_][A-Za-z0-9_]*['\"]\])*\}",
            value.strip(),
        )
    )


def _normalize_credential_value(value: str) -> str:
    normalized = value.strip()
    if normalized.endswith("\\"):
        normalized = normalized[:-1].rstrip()
    while normalized.endswith((",", ";")):
        normalized = normalized[:-1].rstrip()
    normalized = normalized.rstrip("，。；：")
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

    source_entries: list[tuple[Path, str]] = []
    for relative_path in tracked_files(root):
        runtime_finding = _runtime_artifact_finding(relative_path)
        if runtime_finding is not None:
            findings.append(runtime_finding)
            continue
        text = _repository_entry_text(root, relative_path)
        if text is not None:
            source_entries.append((relative_path, text))

    javascript_files = [
        (_display_path(relative_path), text)
        for relative_path, text in source_entries
        if relative_path.suffix.casefold() in JAVASCRIPT_SUFFIXES
    ]
    javascript_ast = _javascript_ast_batch(javascript_files)
    for relative_path, text in source_entries:
        path = _display_path(relative_path)
        findings.extend(
            scan_public_text(
                relative_path,
                text,
                javascript_ast=javascript_ast.get(path),
            )
        )

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
    lower_name = relative_path.name.lower()
    dotenv_template = lower_name in {".env.example", ".env.sample", ".env.template"}
    dotenv_runtime = not dotenv_template and (
        lower_name == ".env" or lower_name.startswith(".env.")
    )
    forbidden = relative_path.name != ".gitkeep" and (
        bool(RUNTIME_DATABASE_RE.search(relative_path.name))
        or bool(RUNTIME_BACKUP_RE.search(relative_path.name))
        or bool(RUNTIME_LOG_RE.search(relative_path.name))
        or any(lower_path.startswith(prefix) for prefix in RUNTIME_PATH_PREFIXES)
        or dotenv_runtime
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
