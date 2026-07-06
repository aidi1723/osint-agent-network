from __future__ import annotations

import shutil
import subprocess
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread


class HealthcheckScriptTests(unittest.TestCase):
    def test_healthcheck_allows_no_read_token_for_unprotected_system_status(self):
        api_server = ThreadingHTTPServer(("127.0.0.1", 0), _PublicApiHandler)
        web_server = ThreadingHTTPServer(("127.0.0.1", 0), _WebHandler)
        api_thread = Thread(target=api_server.serve_forever, daemon=True)
        web_thread = Thread(target=web_server.serve_forever, daemon=True)
        api_thread.start()
        web_thread.start()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                scripts = root / "scripts"
                scripts.mkdir()
                shutil.copy2(Path(__file__).resolve().parents[2] / "scripts" / "healthcheck.sh", scripts / "healthcheck.sh")
                (root / ".env").write_text(
                    "\n".join(
                        [
                            f"API_URL=http://127.0.0.1:{api_server.server_address[1]}",
                            f"WEB_URL=http://127.0.0.1:{web_server.server_address[1]}",
                        ]
                    ),
                    encoding="utf-8",
                )

                result = subprocess.run(
                    ["bash", str(scripts / "healthcheck.sh")],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("api=ok", result.stdout)
            self.assertIn("web=ok", result.stdout)
        finally:
            api_server.shutdown()
            api_server.server_close()
            web_server.shutdown()
            web_server.server_close()

    def test_healthcheck_uses_read_token_for_protected_system_status(self):
        api_server = ThreadingHTTPServer(("127.0.0.1", 0), _ProtectedApiHandler)
        web_server = ThreadingHTTPServer(("127.0.0.1", 0), _WebHandler)
        api_thread = Thread(target=api_server.serve_forever, daemon=True)
        web_thread = Thread(target=web_server.serve_forever, daemon=True)
        api_thread.start()
        web_thread.start()
        try:
            with TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                scripts = root / "scripts"
                scripts.mkdir()
                shutil.copy2(Path(__file__).resolve().parents[2] / "scripts" / "healthcheck.sh", scripts / "healthcheck.sh")
                (root / ".env").write_text(
                    "\n".join(
                        [
                            f"API_URL=http://127.0.0.1:{api_server.server_address[1]}",
                            f"WEB_URL=http://127.0.0.1:{web_server.server_address[1]}",
                            "READ_API_TOKEN=secret-read-token",
                        ]
                    ),
                    encoding="utf-8",
                )

                result = subprocess.run(
                    ["bash", str(scripts / "healthcheck.sh")],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("api=ok", result.stdout)
            self.assertIn("web=ok", result.stdout)
        finally:
            api_server.shutdown()
            api_server.server_close()
            web_server.shutdown()
            web_server.server_close()


class _PublicApiHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/health":
            self._json('{"status":"ok"}', 200)
            return
        if self.path == "/api/system/status":
            self._json(
                '{"database":{"status":"ok","schema_version_count":2},'
                '"scripts":{"backup":{"present":true}},"investigations":{"total":0}}',
                200,
            )
            return
        self._json('{"detail":"not found"}', 404)

    def log_message(self, format, *args):
        return

    def _json(self, body: str, status: int):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _ProtectedApiHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/health":
            self._json('{"status":"ok"}', 200)
            return
        if self.path == "/api/system/status":
            if self.headers.get("Authorization") != "Bearer secret-read-token":
                self._json('{"detail":"unauthorized read request"}', 401)
                return
            self._json(
                '{"database":{"status":"ok","schema_version_count":2},'
                '"scripts":{"backup":{"present":true}},"investigations":{"total":0}}',
                200,
            )
            return
        self._json('{"detail":"not found"}', 404)

    def log_message(self, format, *args):
        return

    def _json(self, body: str, status: int):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = b"<!doctype html><html><body>ok</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    unittest.main()
