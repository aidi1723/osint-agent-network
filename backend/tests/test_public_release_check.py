import json
import hashlib
import os
import subprocess
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.public_release_check import (
    ReleaseFinding,
    evaluate_public_release,
    scan_public_text,
    tracked_files,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GPL_TEXT = (REPOSITORY_ROOT / "LICENSE").read_text(encoding="utf-8")


def write_release_fixture(root: Path, *, backend_license: str = "GPL-3.0-only") -> None:
    (root / "LICENSE").write_text(GPL_TEXT, encoding="utf-8")
    (root / "frontend").mkdir()
    (root / "frontend" / "package.json").write_text(
        json.dumps({"license": "GPL-3.0-only"}), encoding="utf-8"
    )
    (root / "backend").mkdir()
    (root / "backend" / "pyproject.toml").write_text(
        f'[project]\nname = "fixture"\nlicense = "{backend_license}"\n',
        encoding="utf-8",
    )


class PublicReleaseCheckTests(unittest.TestCase):
    def test_release_finding_is_immutable(self):
        finding = ReleaseFinding("PUBLIC_PATH", "notes.txt", 3, "Personal home path")

        with self.assertRaises(FrozenInstanceError):
            finding.line = 4

    def test_blocks_backend_license_mismatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root, backend_license="MIT")

            result = evaluate_public_release(root)

        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"]["backend_license"], "fail")
        self.assertEqual(result["backend_license"], "MIT")
        self.assertTrue(
            any(
                finding["rule_id"] == "LICENSE_BACKEND"
                and finding["path"] == "backend/pyproject.toml"
                for finding in result["findings"]
            )
        )

    def test_blocks_personal_home_paths_with_stable_locations(self):
        text = (
            "first\ncheckout=/home/" + "alice/project\ncache=/Users/" + "alice/project\n"
        )

        findings = scan_public_text(Path("notes/setup.txt"), text)

        self.assertEqual(
            [(item.rule_id, item.path, item.line) for item in findings],
            [
                ("PUBLIC_PERSONAL_PATH", "notes/setup.txt", 2),
                ("PUBLIC_PERSONAL_PATH", "notes/setup.txt", 3),
            ],
        )

    def test_blocks_all_private_lan_ranges_but_allows_documentation_network(self):
        text = "\n".join(
            [
                "docs=192.0.2.10",
                "first=10." + "23.4.5",
                "second=172." + "16.4.5",
                "third=172." + "31.255.254",
                "fourth=192." + "168.1.20",
            ]
        )

        findings = scan_public_text("deployment.txt", text)

        self.assertEqual(
            [(item.rule_id, item.line) for item in findings],
            [
                ("PUBLIC_PRIVATE_NETWORK", 2),
                ("PUBLIC_PRIVATE_NETWORK", 3),
                ("PUBLIC_PRIVATE_NETWORK", 4),
                ("PUBLIC_PRIVATE_NETWORK", 5),
            ],
        )

    def test_blocks_real_credential_assignments_without_reflecting_values(self):
        credential_value = "sk-live-" + "do-not-reflect-987654"
        text = "\n".join(["ADMIN_API_TOKEN", f"ADMIN_API_TOKEN={credential_value}"])

        findings = scan_public_text("config.env.example", text)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "PUBLIC_CREDENTIAL_VALUE")
        self.assertEqual(findings[0].line, 2)
        self.assertNotIn(credential_value, findings[0].summary)
        self.assertNotIn(credential_value, json.dumps(findings[0].to_dict()))

    def test_blocks_case_insensitive_shell_dotenv_and_toml_credentials(self):
        credential_value = "actual-" + "credential-123"
        text = "\n".join(
            [
                "export " + "password" + " = " + credential_value,
                "Db_PassWord" + "='" + credential_value + "'",
                "client_secret" + ' = "' + credential_value + '"',
                "user=public " + "api_token" + "=" + credential_value + " mode=test",
            ]
        )

        findings = scan_public_text("config/settings.toml", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(1, 5)],
        )
        self.assertNotIn(credential_value, json.dumps([finding.to_dict() for finding in findings]))

    def test_source_credentials_allow_only_narrow_dynamic_rhs_forms(self):
        key = "API_" + "KEY"
        hardcoded = "hardcoded-" + "python-value"
        text = "\n".join(
            [
                f'{key} = "{hardcoded}"',
                f'{key} = "hardcoded-" + "python-value"',
                f'{key} = f"prefix-{{user}}-{hardcoded}"',
                f'{key} = os.getenv("{key}")',
                f'{key} = os.environ["{key}"]',
                f'{key} = settings.api_key',
                f'{key} = secrets.token_urlsafe(32)',
            ]
        )

        findings = scan_public_text("app/config.py", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(1, 4)],
        )

    def test_javascript_credentials_block_literals_and_allow_direct_env_references(self):
        key = "CLIENT_" + "SECRET"
        hardcoded = "hardcoded-" + "javascript-value"
        text = "\n".join(
            [
                f'const {key} = "{hardcoded}";',
                f'const {key} = "hardcoded-" + "javascript-value";',
                f'const {key} = `prefix-${{user}}-{hardcoded}`;',
                f"const {key} = process.env.{key};",
                f'const {key} = process.env["{key}"];',
                f"const {key} = import.meta.env.VITE_{key};",
                f"const {key} = config.clientSecret;",
                f"const {key} = crypto.randomUUID();",
            ]
        )

        findings = scan_public_text("frontend/config.ts", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(1, 4)],
        )

    def test_python_source_scans_real_assignments_without_flagging_annotations(self):
        key = "API_" + "KEY"
        text = "\n".join(
            [
                'def request(token: str = "") -> dict:',
                '    payload = {"csrf_token": result.csrf_token}',
                "    token = load_runtime_token()",
                f"    {key} = load_runtime_token()",
                "    api_key = load_runtime_token()",
                '    api_key = os.getenv("PRIMARY_API_KEY") or os.getenv("FALLBACK_API_KEY") or ""',
                "    repeated_cookie = Message()",
                "    token = self._generate_unique_token(forbidden)",
                '    authorization = _single_header_value(headers, "Authorization")',
                "    cookie = logged_in_manager()",
                "    cookie = self.login(environment)",
                '    headers["Authorization"] = f"Bearer {token}"',
                '    headers["Authorization"] = f"Bearer {self.config.api_key}"',
                '    gap_token = f"gap:{gap_key}"',
                '    status = {"legacy_agent_token": "ok" if enabled else "fail"}',
                "    return payload",
            ]
        )

        findings = scan_public_text("app/request.py", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(3, 6)],
        )

    def test_python_ast_visitor_covers_assignment_defaults_and_call_keywords(self):
        value = "hardcoded-" + "visitor-value"
        literal = repr(value)
        text = "\n".join(
            [
                f"API_KEY = {literal}",
                f"api_key: str = {literal}",
                f"if (token := {literal}): pass",
                f"secret += {literal}",
                f"def sync(password={literal}, *, client_secret={literal}): pass",
                f"async def async_fn(token={literal}, *, api_key={literal}): pass",
                f"callback = lambda token={literal}, *, api_key={literal}: token",
                f"connect(api_key={literal})",
                f"@decorate(token={literal})",
                "def decorated(): pass",
                f"dict(API_KEY={literal})",
            ]
        )

        findings = scan_public_text("app/visitor_matrix.py", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(1, 10)]
            + [("PUBLIC_CREDENTIAL_VALUE", 11)],
        )

    def test_python_nested_credential_expressions_fail_closed(self):
        value = "hardcoded-" + "nested-value"
        literal = repr(value)
        text = "\n".join(
            [
                f'API_KEY = os.getenv("API_KEY", {literal})',
                f'API_KEY = os.getenv("API_KEY") or {literal}',
                f'API_KEY = {literal} if enabled else os.getenv("API_KEY")',
                f"API_KEY = prefix + {literal}",
                f'API_KEY = f"prefix-{{user}}-{value}"',
                f'API_KEY = "{{}}".format({literal})',
                f'API_KEY = "%s" % {literal}',
                f"token = self._generate_unique_token({literal})",
                f'config = {{"API_KEY": os.getenv("API_KEY") or {literal}}}',
            ]
        )

        findings = scan_public_text("app/nested.py", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(1, 10)],
        )

    def test_release_tree_blocks_python_complete_expression_bypasses(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            value = "hardcoded-" + "release-value"
            literal = repr(value)
            (root / "security.py").write_text(
                "\n".join(
                    [
                        f"connect(api_key={literal})",
                        f"callback = lambda token={literal}: token",
                        f'API_KEY = os.getenv("API_KEY", {literal})',
                        f'config = {{"API_KEY": os.getenv("API_KEY") or {literal}}}',
                    ]
                ),
                encoding="utf-8",
            )

            result = evaluate_public_release(root)

        findings = [
            finding
            for finding in result["findings"]
            if finding["rule_id"] == "PUBLIC_CREDENTIAL_VALUE"
        ]
        self.assertEqual(
            [(finding["path"], finding["line"]) for finding in findings],
            [("security.py", line) for line in range(1, 5)],
        )

    def test_python_credential_dicts_scan_literal_and_dynamic_values(self):
        key = "ADMIN_API_" + "TOKEN"
        hardcoded = "hardcoded-" + "dict-value"
        text = "\n".join(
            [
                f'config = {{"{key}": "{hardcoded}"}}',
                f'fixture = {{"{key}": fixture_value("admin")}}',
            ]
        )

        findings = scan_public_text("tests/config.py", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", 1), ("PUBLIC_CREDENTIAL_VALUE", 2)],
        )

    def test_exact_synthetic_credential_fixture_is_allowed_only_in_test_paths(self):
        key = "ADMIN_API_" + "TOKEN"
        fixture = "admin-" + "secret"
        source = f'{key} = "{fixture}"'

        self.assertEqual(
            scan_public_text("backend/tests/test_agent_auth.py", source), []
        )
        bearer_source = f'Authorization = "Bearer {fixture}"'
        self.assertEqual(
            scan_public_text("backend/tests/test_agent_auth.py", bearer_source), []
        )
        for path in ("backend/tests/test_auth.py", "backend/app/config.py"):
            with self.subTest(path=path):
                findings = scan_public_text(path, source)
                self.assertEqual(
                    [(finding.rule_id, finding.line) for finding in findings],
                    [("PUBLIC_CREDENTIAL_VALUE", 1)],
                )

    def test_fixture_hash_requires_one_complete_string_literal_expression(self):
        key = "ADMIN_API_" + "TOKEN"
        fixture = "admin-" + "secret"
        text = "\n".join(
            [
                f'{key} = "{fixture}" or fallback',
                f'{key} = "{{}}".format("{fixture}")',
                f'{key} = "%s" % "{fixture}"',
            ]
        )

        findings = scan_public_text("backend/tests/test_agent_auth.py", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(1, 4)],
        )

    def test_test_fixture_allowlist_rejects_realistic_modified_and_concatenated_values(self):
        key = "ADMIN_API_" + "TOKEN"
        realistic = "sk-live-" + "A9f3kLm2Qx7vNp4Zt8Yw6R"
        text = "\n".join(
            [
                f'{key} = "{realistic}"',
                f'{key} = "admin-secret-modified"',
                f'{key} = "admin-" + "secret"',
            ]
        )

        findings = scan_public_text("backend/tests/test_auth.py", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(1, 4)],
        )

    def test_javascript_complete_expression_matrix_fails_closed(self):
        value = "hardcoded-" + "javascript-tail"
        literal = json.dumps(value)
        text = "\n".join(
            [
                f"const API_KEY = process.env.API_KEY || {literal};",
                f"const token = process.env.TOKEN ?? {literal};",
                f"let password = arbitrary({literal});",
                f"const clientSecret = String({literal});",
                f"const GITHUB_PAT = enabled ? process.env.PAT : {literal};",
                f"function connect(apiKey = {literal}) {{}}",
                f"const fn = (token = {literal}) => token;",
                f"const config = {{ API_KEY: {literal} }};",
                f"connect({{ clientSecret: {literal} }});",
                f"API_KEY += {literal};",
                f"API_KEY ||= {literal};",
            ]
        )

        findings = scan_public_text("frontend/security.ts", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(1, 12)],
        )

    def test_javascript_multiline_complete_expression_matrix_fails_closed(self):
        value = "hardcoded-" + "multiline-tail"
        literal = json.dumps(value)
        text = "\n".join(
            [
                "const API_KEY = process.env.API_KEY",
                f"  || {literal};",
                "const token = process.env.TOKEN",
                f"  ?? {literal};",
                "const GITHUB_PAT = enabled",
                "  ? process.env.PAT",
                f"  : {literal};",
                "function connect(",
                "  apiKey =",
                f"    {literal},",
                ") {}",
                "const fn = (",
                "  password =",
                f"    {literal},",
                ") => password;",
                "const config = {",
                "  clientSecret:",
                f"    {literal},",
                "};",
                "connect({",
                "  API_KEY:",
                f"    {literal},",
                "});",
                "const authorization = `prefix-",
                f"${{user}}-{value}`;",
                "const cookie = wrapper(",
                f"  {literal}",
                ");",
                "const safe = { API_KEY: process.env.API_KEY, token: config.token };",
                "type Props = {",
                "  csrfToken: string | null;",
                "  clientSecret?: string;",
                "};",
                f'const prose = "token = {value}";',
                f"// API_KEY = {literal};",
                "const safeTemplate = `token = ${token}`;",
                "const first = 1; const API_KEY = process.env.API_KEY; const token = process.env.TOKEN;",
            ]
        )

        findings = scan_public_text("frontend/multiline-security.ts", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [
                ("PUBLIC_CREDENTIAL_VALUE", line)
                for line in (1, 3, 5, 9, 13, 17, 21, 24, 26)
            ],
        )

    def test_release_tree_blocks_javascript_multiline_expression_bypasses(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            value = "hardcoded-" + "release-js-tail"
            literal = json.dumps(value)
            (root / "frontend" / "security.ts").write_text(
                "\n".join(
                    [
                        "const API_KEY = process.env.API_KEY",
                        f"  || {literal};",
                        "const config = {",
                        "  clientSecret:",
                        f"    {literal},",
                        "};",
                        "const fn = (",
                        "  password =",
                        f"    {literal},",
                        ") => password;",
                    ]
                ),
                encoding="utf-8",
            )

            result = evaluate_public_release(root)

        findings = [
            finding
            for finding in result["findings"]
            if finding["rule_id"] == "PUBLIC_CREDENTIAL_VALUE"
        ]
        self.assertEqual(
            [(finding["path"], finding["line"]) for finding in findings],
            [
                ("frontend/security.ts", 1),
                ("frontend/security.ts", 4),
                ("frontend/security.ts", 8),
            ],
        )

    def test_javascript_lexer_handles_crlf_comments_regex_and_nested_templates(self):
        value = "hardcoded-" + "lexer-tail"
        literal = json.dumps(value)
        text = "\r\n".join(
            [
                f"const pattern = /token = {literal}/g;",
                "const description = `outer ${format(`token = ${token}`)}`;",
                "const API_KEY = process.env.API_KEY /*",
                f"  comment with token = {literal}",
                f"*/ || {literal};",
                "function connect(",
                "  apiKey =",
                f"    {literal},",
                ") {}",
                "const secret = process.env.SECRET /* unterminated",
            ]
        )

        findings = scan_public_text("frontend/lexer.ts", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [
                ("PUBLIC_CREDENTIAL_VALUE", 3),
                ("PUBLIC_CREDENTIAL_VALUE", 7),
                ("PUBLIC_CREDENTIAL_VALUE", 10),
            ],
        )

    def test_bearer_fixture_requires_one_complete_string_expression(self):
        fixtures = {
            "backend/tests/test_agent_auth.py": "admin-" + "secret",
            "frontend/src/auth.test.ts": "operator-" + "secret",
        }
        for path, fixture in fixtures.items():
            with self.subTest(path=path):
                text = "\n".join(
                    [
                        f'send("Bearer {fixture}")',
                        f'send("Bearer {fixture}" + runtime_suffix)',
                    ]
                )
                findings = scan_public_text(path, text)
                self.assertEqual(
                    [(finding.rule_id, finding.line) for finding in findings],
                    [("PUBLIC_CREDENTIAL_VALUE", 2)],
                )
                self.assertNotIn(
                    fixture,
                    json.dumps([finding.to_dict() for finding in findings]),
                )

        bearer_scheme = "Bear" + "er"
        cross_fixture = "admin-" + "secret"
        cross_path = scan_public_text(
            "frontend/src/not-auth.test.ts",
            f'send("{bearer_scheme} {cross_fixture}")',
        )
        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in cross_path],
            [("PUBLIC_CREDENTIAL_VALUE", 1)],
        )
        comparison_fixture = "secret-" + "read-token"
        comparison = scan_public_text(
            "backend/tests/test_healthcheck_script.py",
            f'if authorization != "Bearer {comparison_fixture}":',
        )
        self.assertEqual(comparison, [])

    def test_javascript_allows_only_complete_safe_expressions(self):
        text = "\n".join(
            [
                "const API_KEY = process.env.API_KEY;",
                "const token = import.meta.env.VITE_TOKEN;",
                "const password = config.password;",
                "const clientSecret = crypto.randomUUID();",
                'const GITHUB_PAT = crypto.randomBytes(32).toString("hex");',
                'const authorization = `Bearer ${token}`;',
                'const cookie = "placeholder";',
                "type Props = { csrfToken: string | null };",
            ]
        )

        self.assertEqual(scan_public_text("frontend/safe.ts", text), [])

    def test_typescript_annotations_and_bearer_constants_are_not_credentials(self):
        text = "\n".join(
            [
                "type Config = { token: string; clientSecret?: string }",
                'const BEARER = "bearer";',
                "function request(token: string): string { return token; }",
                "const authorization = `Bearer ${token}`;",
            ]
        )

        self.assertEqual(scan_public_text("frontend/types.ts", text), [])

    def test_blocks_yaml_and_json_credential_values_with_quoted_keys(self):
        credential_value = "yaml-" + "credential-456"
        text = "\n".join(
            [
                "password" + ": " + credential_value,
                '"api_token"' + ': "' + credential_value + '",',
                "'Client_Secret'" + ": '" + credential_value + "'",
            ]
        )

        findings = scan_public_text("deploy/config.yaml", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", 1), ("PUBLIC_CREDENTIAL_VALUE", 2), ("PUBLIC_CREDENTIAL_VALUE", 3)],
        )

    def test_blocks_url_userinfo_private_keys_and_bearer_tokens(self):
        credential_value = "network-" + "credential-789"
        key_material = "-----BEGIN " + "PRIVATE KEY-----"
        text = "\n".join(
            [
                "endpoint=https://alice:" + credential_value + "@example.com/api",
                key_material,
                "Bearer " + credential_value,
                "Authorization: Bearer " + credential_value,
            ]
        )

        findings = scan_public_text("deploy/secrets.txt", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [
                ("PUBLIC_URL_CREDENTIAL", 1),
                ("PUBLIC_PRIVATE_KEY", 2),
                ("PUBLIC_CREDENTIAL_VALUE", 3),
                ("PUBLIC_CREDENTIAL_VALUE", 4),
            ],
        )
        self.assertNotIn(credential_value, json.dumps([finding.to_dict() for finding in findings]))

    def test_blocks_password_userinfo_for_multiple_uri_schemes_and_encoded_characters(self):
        url_value = "p%40ss%3Aword%2Fwith%21chars"
        text = "\n".join(
            [
                f"postgresql://dbuser:{url_value}@db.example/app",
                f"mysql://dbuser:{url_value}@db.example/app",
                f"redis://default:{url_value}@cache.example/0",
                f"http://webuser:{url_value}@example.com/path",
                "postgresql://dbuser@db.example/app",
                "redis://default@cache.example/0",
            ]
        )

        findings = scan_public_text("deploy/connection-strings.txt", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_URL_CREDENTIAL", line) for line in range(1, 5)],
        )

    def test_credential_key_vocabulary_covers_provider_and_generic_secret_keys(self):
        keys = [
            "AWS_SECRET_ACCESS_KEY",
            "AWS_ACCESS_KEY_ID",
            "GITHUB_PAT",
            "DEPLOY_PAT",
            "CLIENT_SECRET",
            "TLS_PRIVATE_KEY",
            "SERVICE_ACCESS_KEY",
            "DB_CREDENTIAL",
            "DB_CREDENTIALS",
        ]
        value = "real-" + "credential-value"
        text = "\n".join(f"{key}={value}" for key in keys)

        findings = scan_public_text("deploy/provider.env", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(1, len(keys) + 1)],
        )

    def test_generic_credential_prose_is_not_an_assignment(self):
        text = "Creden" + "tials: configure these in your local environment."

        self.assertEqual(scan_public_text("docs/setup.md", text), [])

    def test_bearer_placeholder_prose_and_punctuation_are_allowed(self):
        prefix = "Bear" + "er "
        text = "\n".join(
            [
                prefix + "Token，configure it locally.",
                prefix + "credential in the request header.",
                prefix + "...",
            ]
        )

        self.assertEqual(scan_public_text("docs/auth.md", text), [])

    def test_url_detection_does_not_span_json_fields_to_an_email_address(self):
        text = (
            '{"url":"https://www.example.com","email":"sales@example.com",'
            '"type":"Organization"}'
        )

        self.assertEqual(scan_public_text("fixtures/company.json", text), [])

    def test_all_bearer_literals_are_blocked_regardless_of_shape(self):
        prefix = "Bear" + "er "
        text = "\n".join(
            [
                prefix + "abc123",
                prefix + "550e8400-e29b-41d4-a716-446655440000",
                "Authorization: " + prefix + "opaque-short-value",
                prefix + "$TOKEN",
                prefix + "${TOKEN}",
                prefix + "{token}",
                prefix + "{self.config.api_key}",
                prefix + "{tool_agent['agent_token']}",
                prefix + "<your-token>",
            ]
        )

        findings = scan_public_text("docs/auth.txt", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(1, 4)],
        )

    def test_allows_username_only_url_authority_without_password(self):
        findings = scan_public_text(
            "fixtures/page.html",
            '<a href="https://support@example.com/help">Support</a>',
        )

        self.assertEqual(findings, [])

    def test_blocks_multiline_yaml_credential_scalars(self):
        credential_value = "multiline-" + "credential-321"
        text = "\n".join(
            [
                "password: |",
                "  " + credential_value,
                "description: public",
                "api_token: >-",
                "  " + credential_value,
            ]
        )

        findings = scan_public_text("deploy/secrets.yaml", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", 1), ("PUBLIC_CREDENTIAL_VALUE", 4)],
        )

    def test_placeholder_and_dynamic_values_must_match_the_entire_value(self):
        lines = [
            "api_token=<token>",
            "api_token=<your-token>",
            "api_token=$TOKEN",
            "api_token=${TOKEN}",
            "api_token=placeholder",
            "api_token=$(openssl rand -hex 32)",
            "api_token=$(uuidgen)",
            "api_token=<token> actual",
            "api_token=placeholder actual",
            "api_token=audit-canary-live",
            "api_token=$(echo secret)",
        ]

        findings = scan_public_text("deploy/placeholders.env", "\n".join(lines))

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(8, 12)],
        )

    def test_allows_generic_paths_variable_names_and_placeholder_credentials(self):
        text = "\n".join(
            [
                "/opt/osint-agent-network",
                "/var/backups/osint-agent-network",
                "/path/to/osint-agent-network",
                "/home/aidi/...",
                "ADMIN_API_TOKEN",
                "ADMIN_API_TOKEN=<your-token>",
                "READ_API_TOKEN=${READ_API_TOKEN}",
                "PASSWORD=placeholder",
            ]
        )

        self.assertEqual(scan_public_text("docs/example.md", text), [])

    def test_ellipsized_home_placeholder_cannot_hide_a_continued_concrete_path(self):
        findings = scan_public_text(
            "notes.txt", "/home/" + "alice/.../private/config\n"
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "PUBLIC_PERSONAL_PATH")

    def test_personal_paths_are_case_insensitive_unicode_and_match_at_path_end(self):
        text = "\n".join(
            [
                "first=/HOME/" + "Alice",
                "second=/users/" + "张伟/项目",
                "third=/Users/" + "Élodie",
                "service=/home/osint/project",
                "placeholder=/home/aidi/...",
            ]
        )

        findings = scan_public_text("notes/paths.txt", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_PERSONAL_PATH", 1), ("PUBLIC_PERSONAL_PATH", 2), ("PUBLIC_PERSONAL_PATH", 3)],
        )

    def test_self_scan_allowlist_uses_exact_content_and_still_scans_adjacent_lines(self):
        marker = "Path: /Users/" + "example/.config"
        source = Path(__file__).with_name("test_report_export.py")
        allowed_line = next(
            line for line in source.read_text(encoding="utf-8").splitlines() if marker in line
        )
        adjacent = "checkout=/home/" + "mallory/private"

        findings = scan_public_text(
            "backend/tests/test_report_export.py",
            f"moved\n{allowed_line}\n{adjacent}\n",
        )

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_PERSONAL_PATH", 3)],
        )

    def test_self_scan_allowlist_blocks_identical_occurrences_beyond_count_one(self):
        path = "docs/count-one.md"
        rule_id = "PUBLIC_PERSONAL_PATH"
        source_line = "checkout=/Users/" + "example/private"
        signature = hashlib.sha256(source_line.encode("utf-8")).hexdigest()

        with patch(
            "scripts.public_release_check.SELF_SCAN_ALLOWLIST",
            {(path, rule_id, signature): 1},
        ):
            findings = scan_public_text(path, f"{source_line}\n{source_line}\n")

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [(rule_id, 2)],
        )

    def test_self_scan_allowlist_blocks_next_occurrence_beyond_larger_baseline(self):
        path = "docs/count-two.md"
        rule_id = "PUBLIC_PERSONAL_PATH"
        source_line = "checkout=/home/" + "example/private"
        signature = hashlib.sha256(source_line.encode("utf-8")).hexdigest()

        with patch(
            "scripts.public_release_check.SELF_SCAN_ALLOWLIST",
            {(path, rule_id, signature): 2},
        ):
            findings = scan_public_text(
                path,
                f"{source_line}\n{source_line}\n{source_line}\n",
            )

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [(rule_id, 3)],
        )

    def test_credential_allowlist_does_not_hide_adjacent_unmarked_assignments(self):
        marker = "VITE_ADMIN_API_" + "TOKEN=<same-value"
        source = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "superpowers"
            / "plans"
            / "2026-07-10-security-hardening.md"
        )
        allowed_line = next(
            line for line in source.read_text(encoding="utf-8").splitlines() if marker in line
        )
        adjacent = "password" + '="new-real-value"'

        findings = scan_public_text(
            "docs/superpowers/plans/2026-07-10-security-hardening.md",
            f"{allowed_line}\n{adjacent}\n",
        )

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", 2)],
        )

    def test_allows_code_constants_boolean_flags_and_generated_or_documented_values(self):
        text = "\n".join(
            [
                "KNOWN_OUTPUT_TOKENS = {'entities'}",
                "OSINT_ALLOW_LEGACY_AGENT_TOKEN=false",
                "ADMIN_API_TOKEN=$(openssl rand -hex 32)",
                "UPKUAJING_AUTHORIZATION=Bearer <your-token>",
                "UPKUAJING_AUTHORIZATION=Bearer your_token_here",
            ]
        )

        self.assertEqual(scan_public_text("docs/configuration.md", text), [])

    def test_runtime_artifact_policy_uses_tracked_path_not_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            (root / "data").mkdir()
            (root / "data" / "state.sqlite").write_bytes(b"\xff\xfeSQLite binary")
            (root / "notes.txt").write_text("state.sqlite is ignored at runtime\n", encoding="utf-8")

            result = evaluate_public_release(root)

        runtime = [item for item in result["findings"] if item["rule_id"] == "PUBLIC_RUNTIME_ARTIFACT"]
        self.assertEqual(runtime, [{
            "rule_id": "PUBLIC_RUNTIME_ARTIFACT",
            "path": "data/state.sqlite",
            "line": 0,
            "summary": "Tracked runtime artifact is not allowed in a public release.",
        }])

    def test_runtime_directory_marker_is_not_treated_as_an_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            (root / "reports").mkdir()
            (root / "reports" / ".gitkeep").write_text("", encoding="utf-8")

            result = evaluate_public_release(root)

        self.assertTrue(result["ready"])

    def test_blocks_database_auxiliaries_logs_backups_and_runtime_archives_by_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            artifact_paths = [
                "data/state.DB-wal",
                "data/state.sqlite3-SHM",
                "data/state.sqlite-journal",
                "logs/service.LOG",
                "config/settings.bak",
                "backups/runtime.tar.gz",
            ]
            for path in artifact_paths:
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("runtime", encoding="utf-8")
            source_archive = root / "fixtures" / "source.zip"
            source_archive.parent.mkdir()
            source_archive.write_text("legitimate source fixture", encoding="utf-8")

            result = evaluate_public_release(root)

        runtime_paths = [
            finding["path"]
            for finding in result["findings"]
            if finding["rule_id"] == "PUBLIC_RUNTIME_ARTIFACT"
        ]
        self.assertEqual(runtime_paths, sorted(artifact_paths))
        self.assertNotIn("fixtures/source.zip", runtime_paths)

    def test_blocks_nested_case_insensitive_dotenv_except_exact_templates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            blocked_paths = [
                ".ENV",
                "config/.env",
                "apps/web/.Env.Production",
                "nested/config/.env.local",
                "nested/config/.env.production.example",
            ]
            allowed_paths = [
                ".env.example",
                "config/.ENV.SAMPLE",
                "apps/web/.env.template",
            ]
            for path in blocked_paths + allowed_paths:
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("PUBLIC_SETTING=example\n", encoding="utf-8")

            result = evaluate_public_release(root)

        runtime_paths = [
            finding["path"]
            for finding in result["findings"]
            if finding["rule_id"] == "PUBLIC_RUNTIME_ARTIFACT"
        ]
        self.assertEqual(runtime_paths, sorted(blocked_paths))

    def test_blocks_compressed_and_rotated_runtime_logs_and_databases(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            artifact_paths = [
                "app.log.gz",
                "app.log.1.gz",
                "state.sqlite.gz",
                "state.sqlite-wal.gz",
                "data/cache.db-shm.gz",
            ]
            allowed_paths = ["fixtures/source.zip", "fixtures/source.tar.gz"]
            for path in artifact_paths + allowed_paths:
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("archive fixture", encoding="utf-8")

            result = evaluate_public_release(root)

        runtime_paths = [
            finding["path"]
            for finding in result["findings"]
            if finding["rule_id"] == "PUBLIC_RUNTIME_ARTIFACT"
        ]
        self.assertEqual(runtime_paths, sorted(artifact_paths))

    def test_binary_files_are_skipped_for_text_scanning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            binary = root / "opaque.bin"
            binary.write_bytes(b"\xff\xfe/home/alice/project")

            result = evaluate_public_release(root)

        self.assertTrue(result["ready"])

    def test_tracked_files_fallback_is_sorted_and_excludes_generated_dirs_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "z.txt").write_text("z", encoding="utf-8")
            (root / "a.txt").write_text("a", encoding="utf-8")
            (root / "frontend" / "node_modules").mkdir(parents=True)
            (root / "frontend" / "node_modules" / "ignored.js").write_text("x", encoding="utf-8")
            outside = root.parent / f"{root.name}-outside.txt"
            outside.write_text("outside", encoding="utf-8")
            try:
                (root / "escape.txt").symlink_to(outside)

                paths = tracked_files(root)
            finally:
                outside.unlink(missing_ok=True)

        self.assertEqual(paths, [Path("a.txt"), Path("z.txt")])

    def test_tracked_files_uses_git_index_and_handles_non_utf8_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "tracked.txt").write_text("tracked", encoding="utf-8")
            (root / "binary.dat").write_bytes(b"\xff\xfe")
            (root / "z space.txt").write_text("space", encoding="utf-8")
            (root / "a\nline.txt").write_text("newline", encoding="utf-8")
            (root / "untracked.txt").write_text("untracked", encoding="utf-8")
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "add",
                    "tracked.txt",
                    "binary.dat",
                    "z space.txt",
                    "a\nline.txt",
                ],
                check=True,
            )

            paths = tracked_files(root)

        self.assertEqual(
            paths,
            [Path("a\nline.txt"), Path("binary.dat"), Path("tracked.txt"), Path("z space.txt")],
        )

    def test_nested_directory_without_own_git_metadata_uses_filesystem_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            subprocess.run(["git", "init", "-q", str(parent)], check=True)
            root = parent / "fixture"
            root.mkdir()
            (root / "visible.txt").write_text("visible", encoding="utf-8")
            subprocess.run(["git", "-C", str(parent), "add", "fixture/visible.txt"], check=True)

            with patch(
                "scripts.public_release_check.subprocess.run",
                side_effect=AssertionError("nested root must not query parent Git repository"),
            ):
                try:
                    paths = tracked_files(root)
                except AssertionError as exc:
                    self.fail(str(exc))

        self.assertEqual(paths, [Path("visible.txt")])

    @unittest.skipUnless(os.name == "posix", "invalid filename bytes require POSIX paths")
    def test_invalid_utf8_git_filename_is_policy_checked_and_safely_displayed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            (root / ".git").mkdir()
            raw_name = b"runtime-\xff\n.sqlite"
            completed = SimpleNamespace(returncode=0, stdout=raw_name + b"\0")

            with (
                patch("scripts.public_release_check.subprocess.run", return_value=completed),
                patch("scripts.public_release_check._safe_regular_file", return_value=True),
            ):
                result = evaluate_public_release(root)

        runtime = [
            finding
            for finding in result["findings"]
            if finding["rule_id"] == "PUBLIC_RUNTIME_ARTIFACT"
        ]
        self.assertEqual(
            [finding["path"] for finding in runtime], ["runtime-\\xff\\n.sqlite"]
        )
        self.assertNotIn("\udcff", json.dumps(result))

    def test_tracked_symlinks_are_scanned_without_following_outside_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "personal-link").symlink_to("/home/" + "alice/private")
            (root / "runtime.sqlite").symlink_to("/outside/runtime.db")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)

            result = evaluate_public_release(root)

        findings = {(finding["rule_id"], finding["path"]) for finding in result["findings"]}
        self.assertIn(("PUBLIC_PERSONAL_PATH", "personal-link"), findings)
        self.assertIn(("PUBLIC_RUNTIME_ARTIFACT", "runtime.sqlite"), findings)

    def test_tracked_files_falls_back_when_git_command_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            (root / "visible.txt").write_text("visible", encoding="utf-8")

            paths = tracked_files(root)

        self.assertEqual(paths, [Path("visible.txt")])

    def test_allows_consistent_gplv3_license_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)

            result = evaluate_public_release(root)

        self.assertTrue(result["ready"])
        self.assertEqual(result["checks"]["license_file"], "ok")
        self.assertEqual(result["checks"]["package_license"], "ok")
        self.assertEqual(result["checks"]["backend_license"], "ok")
        self.assertEqual(result["findings"], [])

    def test_rejects_four_marker_license_spoof(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            (root / "LICENSE").write_text(
                "\n".join(
                    [
                        "GNU GENERAL PUBLIC LICENSE",
                        "Version 3, 29 June 2007",
                        "Everyone is permitted to copy and distribute verbatim copies",
                        "END OF TERMS AND CONDITIONS",
                    ]
                ),
                encoding="utf-8",
            )

            result = evaluate_public_release(root)

        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"]["license_file"], "fail")
        self.assertTrue(any(item["rule_id"] == "LICENSE_FILE" for item in result["findings"]))

    def test_accepts_canonical_gplv3_with_crlf_and_trailing_newline_normalization(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            normalized = GPL_TEXT.rstrip("\r\n").replace("\n", "\r\n") + "\r\n\r\n"
            (root / "LICENSE").write_bytes(normalized.encode("utf-8"))

            result = evaluate_public_release(root)

        self.assertTrue(result["ready"])

    def test_malformed_license_metadata_roots_return_stable_findings(self):
        cases = [
            ("[]", '[project]\nlicense = "GPL-3.0-only"\n', "LICENSE_FRONTEND"),
            ('"GPL-3.0-only"', '[project]\nlicense = "GPL-3.0-only"\n', "LICENSE_FRONTEND"),
            ('{"license":"GPL-3.0-only"}', 'project = "bad"\n', "LICENSE_BACKEND"),
            ('{"license":"GPL-3.0-only"}', 'name = "missing-project"\n', "LICENSE_BACKEND"),
        ]
        for package_json, backend_toml, expected_rule in cases:
            with self.subTest(expected_rule=expected_rule, backend_toml=backend_toml):
                with tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir)
                    write_release_fixture(root)
                    (root / "frontend" / "package.json").write_text(package_json, encoding="utf-8")
                    (root / "backend" / "pyproject.toml").write_text(backend_toml, encoding="utf-8")

                    try:
                        result = evaluate_public_release(root)
                    except (AttributeError, TypeError) as exc:
                        self.fail(f"malformed metadata raised {type(exc).__name__}")

                self.assertFalse(result["ready"])
                self.assertTrue(
                    any(item["rule_id"] == expected_rule for item in result["findings"])
                )

    def test_rejects_invalid_backend_toml_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            (root / "backend" / "pyproject.toml").write_text("[project\n", encoding="utf-8")

            result = evaluate_public_release(root)

        self.assertFalse(result["ready"])
        self.assertEqual(result["backend_license"], "")
        self.assertEqual(result["checks"]["backend_license"], "fail")


if __name__ == "__main__":
    unittest.main()
