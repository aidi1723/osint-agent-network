import socket
import threading
import time
import traceback
import unittest
from unittest.mock import patch

from app.core import safe_http as safe_http_module
from app.core.normalization import NormalizationError, normalize_target
from app.core.safe_http import (
    BlockedNetworkTarget,
    InvalidHttpTarget,
    RedirectLimitExceeded,
    ResponseTooLarge,
    SafeHttpError,
    ValidatedTarget,
    connect_pinned,
    safe_fetch,
    validate_public_url,
)


PUBLIC_IP = "8.8.8.8"


def resolver_for(*addresses):
    def resolve(host, port, *args, **kwargs):
        return [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))
            for address in addresses
        ]

    return resolve


class FakeResponse:
    def __init__(self, status=200, body=b"ok", headers=None):
        self.status = status
        self.headers = headers or {}
        self._body = body
        self.closed = False

    def read(self, limit):
        return self._body[:limit]

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class SafeHttpValidationTests(unittest.TestCase):
    def test_accepts_public_target_and_preserves_request_identity(self):
        calls = []

        def resolver(host, port, *args, **kwargs):
            calls.append((host, port))
            return resolver_for("1.1.1.1", PUBLIC_IP)(host, port)

        target = validate_public_url("https://Example.COM:443/a%20b?q=1", resolver=resolver)

        self.assertEqual(target.scheme, "https")
        self.assertEqual(target.hostname, "example.com")
        self.assertEqual(target.port, 443)
        self.assertEqual(target.request_path, "/a%20b?q=1")
        self.assertEqual(target.validated_ips, ("1.1.1.1", "8.8.8.8"))
        self.assertEqual(calls, [("example.com", 443)])

    def test_rejects_all_non_global_address_classes(self):
        blocked = [
            "127.0.0.1",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.0.1",
            "169.254.169.254",
            "0.0.0.0",
            "224.0.0.1",
            "192.0.2.1",
            "::1",
            "fc00::1",
            "fe80::1",
            "ff02::1",
            "::",
            "::ffff:127.0.0.1",
        ]
        for address in blocked:
            with self.subTest(address=address):
                with self.assertRaises(BlockedNetworkTarget):
                    validate_public_url("http://example.com", resolver=resolver_for(address))

    def test_rejects_alternate_loopback_literals_after_resolution(self):
        for url in ("http://127.1/", "http://2130706433/"):
            with self.subTest(url=url):
                with self.assertRaises(BlockedNetworkTarget):
                    validate_public_url(url, resolver=resolver_for("127.0.0.1"))

    def test_blocks_private_literals_without_trusting_resolver_answers(self):
        private_urls = (
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
            "http://127.1/",
            "http://2130706433/",
            "http://0177.0.0.1/",
            "http://0x7f000001/",
            "http://0x7f.1/",
        )
        for url in private_urls:
            calls = []
            with self.subTest(url=url):
                with self.assertRaises(BlockedNetworkTarget):
                    validate_public_url(
                        url,
                        resolver=lambda *args, calls=calls, **kwargs: calls.append(args)
                        or resolver_for(PUBLIC_IP)(*args),
                    )
                self.assertEqual(calls, [])

    def test_public_literal_is_pinned_exactly_without_resolver(self):
        calls = []

        target = validate_public_url(
            "https://8.8.8.8/path",
            resolver=lambda *args, **kwargs: calls.append(args) or resolver_for("1.1.1.1")(*args),
        )

        self.assertEqual(target.original_hostname, PUBLIC_IP)
        self.assertEqual(target.validated_ips, (PUBLIC_IP,))
        self.assertEqual(calls, [])

    def test_public_hexadecimal_literal_is_canonicalized_without_resolver(self):
        calls = []

        target = validate_public_url(
            "https://0x08080808/path",
            resolver=lambda *args, **kwargs: calls.append(args) or resolver_for("1.1.1.1")(*args),
        )

        self.assertEqual(target.original_hostname, "0x08080808")
        self.assertEqual(target.validated_ips, (PUBLIC_IP,))
        self.assertEqual(calls, [])

    def test_lazy_resolver_failure_is_stable_and_non_reflective(self):
        def lazy_answers():
            yield (socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 443))
            raise OSError("secret.internal resolver detail")

        with self.assertRaisesRegex(InvalidHttpTarget, "^target resolution failed$") as caught:
            validate_public_url("https://example.com/", resolver=lambda *args, **kwargs: lazy_answers())

        formatted = "".join(traceback.format_exception(caught.exception))
        self.assertNotIn("secret.internal", formatted)

    def test_malformed_lazy_resolver_answer_is_stable(self):
        for answer in ((socket.AF_INET,), {"address": "secret.internal"}, None):
            with self.subTest(answer=answer):
                with self.assertRaisesRegex(InvalidHttpTarget, "^target resolution failed$"):
                    validate_public_url(
                        "https://example.com/",
                        resolver=lambda *args, answer=answer, **kwargs: iter([answer]),
                    )

    def test_normalization_rejects_non_global_and_legacy_ip_literals(self):
        for url in (
            "http://10.0.0.1/",
            "http://[::1]/",
            "http://127.1/",
            "http://2130706433/",
            "http://0x7f000001/",
            "http://0x7f.1/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(NormalizationError):
                    normalize_target("url", url)

    def test_rejects_mixed_public_and_private_dns_answers(self):
        with self.assertRaises(BlockedNetworkTarget):
            validate_public_url("https://example.com", resolver=resolver_for(PUBLIC_IP, "10.0.0.2"))

    def test_rejects_excessive_unique_answers_before_connector(self):
        addresses = tuple(f"8.8.8.{index}" for index in range(1, 10))
        connector_calls = []

        with self.assertRaises(InvalidHttpTarget):
            safe_fetch(
                "https://example.com/",
                timeout_seconds=1,
                max_bytes=10,
                resolver=resolver_for(*addresses),
                connector=lambda *args: connector_calls.append(args),
            )

        self.assertEqual(connector_calls, [])

    def test_rejects_nine_duplicate_raw_answers_before_connector(self):
        connector_calls = []

        with self.assertRaisesRegex(InvalidHttpTarget, "^too many resolved addresses$"):
            safe_fetch(
                "https://example.com/",
                timeout_seconds=1,
                max_bytes=10,
                resolver=resolver_for(*([PUBLIC_IP] * 9)),
                connector=lambda *args: connector_calls.append(args),
            )

        self.assertEqual(connector_calls, [])

    def test_resolver_worker_consumes_at_most_nine_answers_and_recovers(self):
        yielded = 0
        generator_closed = threading.Event()

        def resolver(host, port, *args, **kwargs):
            def excessive_answers():
                nonlocal yielded
                try:
                    while True:
                        yielded += 1
                        if yielded > 9:
                            raise AssertionError("resolver generator was over-consumed")
                        yield (socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, port))
                finally:
                    generator_closed.set()

            return excessive_answers()

        with self.assertRaisesRegex(InvalidHttpTarget, "^too many resolved addresses$"):
            safe_fetch(
                "https://example.com/",
                timeout_seconds=1,
                max_bytes=10,
                resolver=resolver,
                connector=lambda *args: self.fail("connector must not run"),
            )

        self.assertEqual(yielded, 9)
        self.assertTrue(generator_closed.wait(0.1))
        recovered = safe_fetch(
            "https://example.com/",
            timeout_seconds=1,
            max_bytes=10,
            resolver=resolver_for(PUBLIC_IP),
            connector=lambda *args: (FakeResponse(body=b"recovered"), FakeConnection()),
        )
        self.assertEqual(recovered.body, b"recovered")

    def test_accepts_exactly_eight_valid_raw_answers(self):
        addresses = tuple(f"8.8.8.{index}" for index in range(1, 9))

        target = validate_public_url("https://example.com/", resolver=resolver_for(*addresses))

        self.assertEqual(len(target.validated_ips), 8)

    def test_expired_deadline_never_invokes_or_enqueues_resolver(self):
        calls = []

        with self.assertRaisesRegex(SafeHttpError, "^HTTP fetch timed out$"):
            validate_public_url(
                "https://example.com/",
                resolver=lambda *args, **kwargs: calls.append(args) or resolver_for(PUBLIC_IP)(*args),
                deadline=time.monotonic() - 1,
            )
        time.sleep(0.02)

        self.assertEqual(calls, [])

    def test_excessive_answers_with_private_member_remain_blocked(self):
        addresses = tuple(f"8.8.8.{index}" for index in range(1, 8)) + ("10.0.0.1", "8.8.8.8")

        with self.assertRaises(BlockedNetworkTarget):
            validate_public_url("https://example.com/", resolver=resolver_for(*addresses))

    def test_rejects_invalid_url_forms(self):
        invalid = [
            "ftp://example.com/file",
            "https:///missing-host",
            "https://user@example.com/",
            "https://example.com/#fragment",
            "https://example.com:444/",
            "https://exa mple.com/",
        ]
        for url in invalid:
            with self.subTest(url=url):
                with self.assertRaises(InvalidHttpTarget):
                    validate_public_url(url, resolver=resolver_for(PUBLIC_IP))


class SafeFetchTests(unittest.TestCase):
    def test_address_attempts_share_decreasing_timeout_budget(self):
        target = ValidatedTarget(
            "http",
            "example.com",
            ("1.1.1.1", "8.8.8.8", "9.9.9.9"),
            80,
            "/",
        )
        budgets = []

        class Connection:
            def __init__(self, *args, **kwargs):
                self.closed = False

            def close(self):
                self.closed = True

        def slow_failure(address, timeout):
            budgets.append(timeout)
            time.sleep(0.018)
            raise OSError("late address")

        started = time.monotonic()
        with patch.object(safe_http_module.socket, "create_connection", side_effect=slow_failure), patch.object(
            safe_http_module.http.client, "HTTPConnection", side_effect=Connection
        ):
            with self.assertRaisesRegex(SafeHttpError, "^HTTP fetch timed out$"):
                connect_pinned(target, timeout_seconds=0.03, headers={"Host": "example.com"})
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.08)
        self.assertGreaterEqual(len(budgets), 1)
        self.assertLess(len(budgets), len(target.validated_ips) + 1)
        self.assertTrue(all(later < earlier for earlier, later in zip(budgets, budgets[1:])))

    def test_connect_pinned_rejects_excessive_addresses_without_attempting_any(self):
        target = ValidatedTarget(
            "http",
            "example.com",
            tuple(f"8.8.8.{index}" for index in range(1, 10)),
            80,
            "/",
        )
        attempts = []

        with patch.object(
            safe_http_module.socket,
            "create_connection",
            side_effect=lambda *args, **kwargs: attempts.append(args) or (_ for _ in ()).throw(OSError()),
        ):
            with self.assertRaises(InvalidHttpTarget):
                connect_pinned(target, timeout_seconds=1, headers={"Host": "example.com"})

        self.assertEqual(attempts, [])

    def test_redirects_share_deadline_and_cleanup_late_response(self):
        budgets = []
        resources = []

        def connector(target, timeout_seconds, headers):
            budgets.append(timeout_seconds)
            response = FakeResponse(302, headers={"Location": "/next"})
            connection = FakeConnection()
            resources.append((response, connection))
            time.sleep(0.025)
            return response, connection

        started = time.monotonic()
        with self.assertRaisesRegex(SafeHttpError, "^HTTP fetch timed out$"):
            safe_fetch(
                "https://example.com/start",
                timeout_seconds=0.04,
                max_bytes=10,
                resolver=resolver_for(PUBLIC_IP),
                connector=connector,
            )
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.09)
        self.assertGreaterEqual(len(budgets), 1)
        self.assertTrue(all(later < earlier for earlier, later in zip(budgets, budgets[1:])))
        self.assertTrue(all(response.closed and connection.closed for response, connection in resources))

    def test_blocking_lazy_resolver_is_bounded_by_total_deadline(self):
        release = threading.Event()

        def resolver(host, port, *args, **kwargs):
            def answers():
                release.wait(0.2)
                yield (socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, port))

            return answers()

        started = time.monotonic()
        try:
            with self.assertRaisesRegex(SafeHttpError, "^HTTP fetch timed out$") as caught:
                safe_fetch(
                    "https://example.com/",
                    timeout_seconds=0.03,
                    max_bytes=10,
                    resolver=resolver,
                    connector=lambda *args: self.fail("connector must not run"),
                )
        finally:
            release.set()
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 0.12)
        self.assertNotIn("example.com", "".join(traceback.format_exception(caught.exception)))

    def test_late_read_exhausts_deadline_and_cleans_resources(self):
        class LateResponse(FakeResponse):
            def read(self, limit):
                time.sleep(0.04)
                return b"ok"

        response = LateResponse()
        connection = FakeConnection()
        started = time.monotonic()

        with self.assertRaisesRegex(SafeHttpError, "^HTTP fetch timed out$"):
            safe_fetch(
                "https://example.com/",
                timeout_seconds=0.02,
                max_bytes=10,
                resolver=resolver_for(PUBLIC_IP),
                connector=lambda *args: (response, connection),
            )

        self.assertLess(time.monotonic() - started, 0.08)
        self.assertTrue(response.closed)
        self.assertTrue(connection.closed)

    def test_fetches_public_target_with_original_host_and_pinned_ips(self):
        seen = []
        response = FakeResponse(headers={"Content-Type": "text/plain"})
        connection = FakeConnection()

        def connector(target, timeout_seconds, headers):
            seen.append((target, timeout_seconds, headers))
            return response, connection

        result = safe_fetch(
            "https://Example.com/data",
            timeout_seconds=3,
            max_bytes=10,
            resolver=resolver_for(PUBLIC_IP),
            connector=connector,
            headers={"User-Agent": "test"},
        )

        self.assertEqual(result.body, b"ok")
        self.assertEqual(result.status, 200)
        self.assertEqual(seen[0][0].validated_ips, (PUBLIC_IP,))
        self.assertEqual(seen[0][2]["Host"], "example.com")
        self.assertEqual(seen[0][2]["User-Agent"], "test")
        self.assertTrue(response.closed)
        self.assertTrue(connection.closed)

    def test_replaces_caller_supplied_host_header(self):
        seen_headers = []

        safe_fetch(
            "https://example.com/",
            timeout_seconds=1,
            max_bytes=10,
            resolver=resolver_for(PUBLIC_IP),
            connector=lambda target, timeout, headers: (
                seen_headers.append(headers) or FakeResponse(),
                FakeConnection(),
            ),
            headers={"host": "internal.test"},
        )

        self.assertEqual(seen_headers, [{"Host": "example.com"}])

    def test_rejects_malformed_headers_before_connector_without_reflection(self):
        malformed = (
            ({"X-Bad\r\nInjected": "value"}, "name control"),
            ({"X-Test": "secret\nvalue"}, "value control"),
            ({"Bad Header": "value"}, "invalid token"),
            ({1: "value"}, "non-string name"),
            ({"X-Test": 1}, "non-string value"),
            ({"Host": "secret\r\nInjected: yes"}, "malformed replaced host"),
        )
        for headers, label in malformed:
            connector_calls = []
            with self.subTest(label=label):
                with self.assertRaisesRegex(SafeHttpError, "^invalid HTTP headers$") as caught:
                    safe_fetch(
                        "https://example.com/",
                        timeout_seconds=1,
                        max_bytes=10,
                        resolver=resolver_for(PUBLIC_IP),
                        connector=lambda *args: connector_calls.append(args),
                        headers=headers,
                    )
                self.assertNotIn("secret", str(caught.exception))
                self.assertEqual(connector_calls, [])

    def test_header_and_connector_tracebacks_do_not_expose_sensitive_causes(self):
        with self.assertRaises(InvalidHttpTarget) as header_error:
            safe_fetch(
                "https://example.com/",
                timeout_seconds=1,
                max_bytes=10,
                headers={"X-Test": "supersecret\nvalue"},
                resolver=resolver_for(PUBLIC_IP),
                connector=lambda *args: self.fail("connector must not run"),
            )
        self.assertNotIn("supersecret", "".join(traceback.format_exception(header_error.exception)))

        with self.assertRaises(SafeHttpError) as connector_error:
            safe_fetch(
                "https://example.com/",
                timeout_seconds=1,
                max_bytes=10,
                resolver=resolver_for(PUBLIC_IP),
                connector=lambda *args: (_ for _ in ()).throw(OSError("supersecret.internal connector")),
            )
        self.assertNotIn("supersecret.internal", "".join(traceback.format_exception(connector_error.exception)))

    def test_blocked_target_never_calls_connector(self):
        calls = []

        with self.assertRaises(BlockedNetworkTarget):
            safe_fetch(
                "http://127.1/",
                timeout_seconds=1,
                max_bytes=10,
                resolver=resolver_for("127.0.0.1"),
                connector=lambda *args: calls.append(args),
            )

        self.assertEqual(calls, [])

    def test_revalidates_redirect_and_rejects_private_destination(self):
        responses = [(FakeResponse(302, headers={"Location": "http://internal.test/"}), FakeConnection())]

        def resolver(host, port, *args, **kwargs):
            return resolver_for(PUBLIC_IP if host == "example.com" else "10.0.0.1")(host, port)

        with self.assertRaises(BlockedNetworkTarget):
            safe_fetch(
                "https://example.com/start",
                timeout_seconds=1,
                max_bytes=10,
                resolver=resolver,
                connector=lambda *args: responses.pop(0),
            )

    def test_literal_redirect_is_blocked_before_resolver_or_second_connection(self):
        connector_calls = []
        resolver_calls = []

        def resolver(host, port, *args, **kwargs):
            resolver_calls.append(host)
            return resolver_for(PUBLIC_IP)(host, port)

        def connector(target, timeout_seconds, headers):
            connector_calls.append(target.original_hostname)
            return FakeResponse(302, headers={"Location": "http://127.1/admin"}), FakeConnection()

        with self.assertRaises(BlockedNetworkTarget):
            safe_fetch(
                "https://example.com/start",
                timeout_seconds=1,
                max_bytes=10,
                resolver=resolver,
                connector=connector,
            )

        self.assertEqual(connector_calls, ["example.com"])
        self.assertEqual(resolver_calls, ["example.com"])

    def test_follows_relative_redirect(self):
        requested_paths = []
        resolved_hosts = []
        pairs = [
            (FakeResponse(302, headers={"Location": "../final?q=1"}), FakeConnection()),
            (FakeResponse(200, body=b"done"), FakeConnection()),
        ]

        def connector(target, timeout_seconds, headers):
            requested_paths.append(target.request_path)
            return pairs.pop(0)

        def resolver(host, port, *args, **kwargs):
            resolved_hosts.append(host)
            return resolver_for(PUBLIC_IP)(host, port)

        result = safe_fetch(
            "https://example.com/a/start",
            timeout_seconds=1,
            max_bytes=10,
            resolver=resolver,
            connector=connector,
        )

        self.assertEqual(result.body, b"done")
        self.assertEqual(result.url, "https://example.com/final?q=1")
        self.assertEqual(requested_paths, ["/a/start", "/final?q=1"])
        self.assertEqual(resolved_hosts, ["example.com", "example.com"])

    def test_enforces_redirect_limit_of_five_hops(self):
        calls = []

        def connector(target, timeout_seconds, headers):
            calls.append(target.request_path)
            return FakeResponse(302, headers={"Location": "/next"}), FakeConnection()

        with self.assertRaises(RedirectLimitExceeded):
            safe_fetch(
                "https://example.com/start",
                timeout_seconds=1,
                max_bytes=10,
                resolver=resolver_for(PUBLIC_IP),
                connector=connector,
            )

        self.assertEqual(len(calls), 6)

    def test_rejects_missing_or_invalid_redirect_location(self):
        for location in (None, "http://"):
            with self.subTest(location=location):
                headers = {} if location is None else {"Location": location}
                with self.assertRaises(InvalidHttpTarget):
                    safe_fetch(
                        "https://example.com/start",
                        timeout_seconds=1,
                        max_bytes=10,
                        resolver=resolver_for(PUBLIC_IP),
                        connector=lambda *args, headers=headers: (FakeResponse(302, headers=headers), FakeConnection()),
                    )

    def test_maps_timeout_and_connection_errors_without_target_details(self):
        for error in (TimeoutError("secret.test timed out"), OSError("connection to secret.test failed")):
            with self.subTest(error=type(error).__name__):
                with self.assertRaisesRegex(SafeHttpError, "^HTTP fetch failed$"):
                    safe_fetch(
                        "https://example.com/secret",
                        timeout_seconds=1,
                        max_bytes=10,
                        resolver=resolver_for(PUBLIC_IP),
                        connector=lambda *args, error=error: (_ for _ in ()).throw(error),
                    )

    def test_rejects_body_at_max_bytes_plus_one_and_cleans_up(self):
        response = FakeResponse(body=b"123456")
        connection = FakeConnection()

        with self.assertRaises(ResponseTooLarge):
            safe_fetch(
                "https://example.com/",
                timeout_seconds=1,
                max_bytes=5,
                resolver=resolver_for(PUBLIC_IP),
                connector=lambda *args: (response, connection),
            )

        self.assertTrue(response.closed)
        self.assertTrue(connection.closed)

    def test_response_close_error_does_not_skip_connection_cleanup(self):
        class BrokenCloseResponse(FakeResponse):
            def close(self):
                self.closed = True
                raise OSError("close failed")

        response = BrokenCloseResponse()
        connection = FakeConnection()

        result = safe_fetch(
            "https://example.com/",
            timeout_seconds=1,
            max_bytes=10,
            resolver=resolver_for(PUBLIC_IP),
            connector=lambda *args: (response, connection),
        )

        self.assertEqual(result.body, b"ok")
        self.assertTrue(response.closed)
        self.assertTrue(connection.closed)

    def test_connector_value_error_closes_connection_and_socket_and_is_stable(self):
        class Socket:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        class Connection:
            def __init__(self, *args, **kwargs):
                self.sock = None
                self.closed = False

            def request(self, *args, **kwargs):
                raise ValueError("secret request construction detail")

            def close(self):
                self.closed = True

        raw_socket = Socket()
        connection = Connection()

        with patch.object(safe_http_module.socket, "create_connection", return_value=raw_socket), patch.object(
            safe_http_module.http.client, "HTTPConnection", return_value=connection
        ):
            with self.assertRaisesRegex(SafeHttpError, "^HTTP fetch failed$") as caught:
                safe_fetch(
                    "http://8.8.8.8/",
                    timeout_seconds=1,
                    max_bytes=10,
                    connector=connect_pinned,
                )

        self.assertNotIn("secret", "".join(traceback.format_exception(caught.exception)))
        self.assertTrue(connection.closed)
        self.assertTrue(raw_socket.closed)

    def test_socket_failure_traceback_is_sanitized_and_connection_is_closed(self):
        class Connection:
            def __init__(self, *args, **kwargs):
                self.closed = False

            def close(self):
                self.closed = True

        connection = Connection()
        with patch.object(
            safe_http_module.socket,
            "create_connection",
            side_effect=OSError("supersecret.internal socket"),
        ), patch.object(safe_http_module.http.client, "HTTPConnection", return_value=connection):
            with self.assertRaises(SafeHttpError) as caught:
                safe_fetch("http://8.8.8.8/", timeout_seconds=1, max_bytes=10)

        self.assertNotIn("supersecret.internal", "".join(traceback.format_exception(caught.exception)))
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
