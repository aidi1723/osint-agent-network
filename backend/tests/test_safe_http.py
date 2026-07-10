import socket
import unittest

from app.core.normalization import NormalizationError, normalize_target
from app.core.safe_http import (
    BlockedNetworkTarget,
    InvalidHttpTarget,
    RedirectLimitExceeded,
    ResponseTooLarge,
    SafeHttpError,
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

    def test_normalization_rejects_non_global_and_legacy_ip_literals(self):
        for url in ("http://10.0.0.1/", "http://[::1]/", "http://127.1/", "http://2130706433/"):
            with self.subTest(url=url):
                with self.assertRaises(NormalizationError):
                    normalize_target("url", url)

    def test_rejects_mixed_public_and_private_dns_answers(self):
        with self.assertRaises(BlockedNetworkTarget):
            validate_public_url("https://example.com", resolver=resolver_for(PUBLIC_IP, "10.0.0.2"))

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


if __name__ == "__main__":
    unittest.main()
