import dataclasses
import unittest
from http.cookies import SimpleCookie

from app.core.browser_auth import BrowserPrincipal, BrowserSessionManager, LoginResult


class MutableClock:
    def __init__(self, value: float):
        self.value = value

    def __call__(self) -> float:
        return self.value


class TokenGenerator:
    def __init__(self, *values: str):
        self.values = list(values)
        self.sizes: list[int] = []

    def __call__(self, size: int) -> str:
        self.sizes.append(size)
        return self.values.pop(0)


def cookie_header(set_cookie: str) -> str:
    cookie = SimpleCookie()
    cookie.load(set_cookie)
    morsel = cookie[BrowserSessionManager.COOKIE_NAME]
    return f"{morsel.key}={morsel.value}"


def logged_in_manager(
    *, secure_cookie: bool = True, session_ttl_seconds: int = 28_800
) -> tuple[BrowserSessionManager, MutableClock, LoginResult, str]:
    clock = MutableClock(1_000.0)
    tokens = TokenGenerator("session-secret", "csrf-secret")
    manager = BrowserSessionManager(
        admin_token="admin-secret",
        secure_cookie=secure_cookie,
        session_ttl_seconds=session_ttl_seconds,
        now=clock,
        token_urlsafe=tokens,
    )
    result = manager.login("admin-secret")
    assert result is not None
    return manager, clock, result, cookie_header(result.set_cookie)


class BrowserSessionManagerTests(unittest.TestCase):
    def test_login_creates_strict_http_only_secure_cookie(self):
        clock = MutableClock(1_000.0)
        tokens = TokenGenerator("session-secret", "csrf-secret")
        manager = BrowserSessionManager(
            admin_token="admin-secret",
            secure_cookie=True,
            now=clock,
            token_urlsafe=tokens,
        )

        result = manager.login("admin-secret")

        self.assertEqual(result, LoginResult(csrf_token="csrf-secret", set_cookie=result.set_cookie))
        self.assertIn("osint_admin_session=session-secret", result.set_cookie)
        self.assertIn("HttpOnly", result.set_cookie)
        self.assertIn("SameSite=Strict", result.set_cookie)
        self.assertIn("Path=/", result.set_cookie)
        self.assertIn("Secure", result.set_cookie)
        self.assertIn("Max-Age=28800", result.set_cookie)
        self.assertNotIn("csrf-secret", result.set_cookie)
        self.assertNotEqual("session-secret", result.csrf_token)
        self.assertEqual(tokens.sizes, [32, 32])

    def test_login_result_and_principal_are_immutable(self):
        manager, _clock, result, cookie = logged_in_manager()
        principal = manager.authorize_session({"Cookie": cookie}, [], mutation=False)

        self.assertIsInstance(principal, BrowserPrincipal)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.csrf_token = "changed"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            principal.role = "reader"

    def test_wrong_login_input_is_rejected_without_generating_tokens(self):
        tokens = TokenGenerator("unused-session", "unused-csrf")
        manager = BrowserSessionManager(
            admin_token="admin-secret",
            secure_cookie=True,
            now=lambda: 1_000.0,
            token_urlsafe=tokens,
        )

        self.assertIsNone(manager.login("wrong-secret"))
        self.assertEqual(tokens.sizes, [])

    def test_unicode_wrong_login_is_rejected_without_generating_tokens(self):
        tokens = TokenGenerator("unused-session", "unused-csrf")
        manager = BrowserSessionManager(
            admin_token="admin-secret",
            secure_cookie=True,
            now=lambda: 1_000.0,
            token_urlsafe=tokens,
        )

        self.assertIsNone(manager.login("错误密码"))
        self.assertEqual(tokens.sizes, [])

    def test_session_expires_at_exact_absolute_deadline(self):
        manager, clock, _result, cookie = logged_in_manager()
        headers = {"Cookie": cookie}

        clock.value = 1_000.0 + 28_800 - 0.001
        self.assertIsNotNone(manager.authorize_session(headers, [], mutation=False))

        clock.value = 1_000.0 + 28_800
        self.assertIsNone(manager.authorize_session(headers, [], mutation=False))
        self.assertEqual(manager.session_payload(headers), {"authenticated": False})

    def test_configured_session_expiry_is_absolute_not_sliding(self):
        manager, clock, _result, cookie = logged_in_manager(session_ttl_seconds=10)
        headers = {"Cookie": cookie}

        clock.value = 1_005.0
        self.assertIsNotNone(manager.authorize_session(headers, [], mutation=False))
        clock.value = 1_010.0
        self.assertIsNone(manager.authorize_session(headers, [], mutation=False))

    def test_session_payload_rotates_and_persists_fresh_csrf_tokens(self):
        tokens = TokenGenerator(
            "session-secret",
            "csrf-login",
            "csrf-rotated-first",
            "csrf-rotated-second",
        )
        manager = BrowserSessionManager(
            admin_token="admin-secret",
            secure_cookie=True,
            now=lambda: 1_000.0,
            token_urlsafe=tokens,
        )
        login = manager.login("admin-secret")
        assert login is not None
        cookie = cookie_header(login.set_cookie)
        origin = "https://hcs.test"

        first = manager.session_payload({"cookie": cookie})

        self.assertEqual(first["csrf_token"], "csrf-rotated-first")
        self.assertNotEqual(first["csrf_token"], login.csrf_token)
        self.assertNotIn("session_id", first)
        self.assertIsNone(
            manager.authorize_session(
                {
                    "Cookie": cookie,
                    "Origin": origin,
                    "X-CSRF-Token": login.csrf_token,
                },
                [origin],
                mutation=True,
            )
        )
        self.assertIsNotNone(
            manager.authorize_session(
                {
                    "Cookie": cookie,
                    "Origin": origin,
                    "X-CSRF-Token": first["csrf_token"],
                },
                [origin],
                mutation=True,
            )
        )

        second = manager.session_payload({"Cookie": cookie})

        self.assertEqual(second["csrf_token"], "csrf-rotated-second")
        self.assertNotEqual(second["csrf_token"], first["csrf_token"])
        self.assertIsNone(
            manager.authorize_session(
                {
                    "Cookie": cookie,
                    "Origin": origin,
                    "X-CSRF-Token": first["csrf_token"],
                },
                [origin],
                mutation=True,
            )
        )
        self.assertIsNotNone(
            manager.authorize_session(
                {
                    "Cookie": cookie,
                    "Origin": origin,
                    "X-CSRF-Token": second["csrf_token"],
                },
                [origin],
                mutation=True,
            )
        )
        self.assertEqual(manager.session_payload({}), {"authenticated": False})
        self.assertEqual(tokens.sizes, [32, 32, 32, 32])

    def test_non_mutating_authorization_needs_no_csrf_or_origin(self):
        manager, _clock, _result, cookie = logged_in_manager()

        principal = manager.authorize_session({"Cookie": cookie}, [], mutation=False)

        self.assertEqual(
            principal,
            BrowserPrincipal(role="administrator", session_id="session-secret"),
        )

    def test_mutation_rejects_wrong_or_missing_csrf(self):
        manager, _clock, _result, cookie = logged_in_manager()
        origin = "https://hcs.test"

        self.assertIsNone(
            manager.authorize_session(
                {"Cookie": cookie, "Origin": origin}, [origin], mutation=True
            )
        )
        self.assertIsNone(
            manager.authorize_session(
                {
                    "Cookie": cookie,
                    "Origin": origin,
                    "X-CSRF-Token": "wrong",
                },
                [origin],
                mutation=True,
            )
        )

    def test_mutation_rejects_unicode_wrong_csrf_without_exception(self):
        manager, _clock, _result, cookie = logged_in_manager()

        self.assertIsNone(
            manager.authorize_session(
                {
                    "Cookie": cookie,
                    "Origin": "https://hcs.test",
                    "X-CSRF-Token": "错误令牌",
                },
                ["https://hcs.test"],
                mutation=True,
            )
        )

    def test_mutation_rejects_wrong_or_missing_origin(self):
        manager, _clock, result, cookie = logged_in_manager()

        self.assertIsNone(
            manager.authorize_session(
                {"Cookie": cookie, "X-CSRF-Token": result.csrf_token},
                ["https://hcs.test"],
                mutation=True,
            )
        )
        self.assertIsNone(
            manager.authorize_session(
                {
                    "Cookie": cookie,
                    "Origin": "https://other.test",
                    "X-CSRF-Token": result.csrf_token,
                },
                ["https://hcs.test"],
                mutation=True,
            )
        )

    def test_mutation_allows_exact_same_origin_and_matching_csrf(self):
        manager, _clock, result, cookie = logged_in_manager()

        principal = manager.authorize_session(
            {
                "cookie": cookie,
                "origin": "https://hcs.test",
                "x-csrf-token": result.csrf_token,
            },
            ["https://hcs.test"],
            mutation=True,
        )

        self.assertEqual(principal.role, "administrator")

    def test_malformed_and_ambiguous_cookies_are_rejected(self):
        manager, _clock, _result, cookie = logged_in_manager()

        malformed_headers = [
            {"Cookie": "osint_admin_session"},
            {"Cookie": "osint_admin_session=\"unterminated"},
            {
                "Cookie": (
                    'note="ignore; osint_admin_session=session-secret; x=y"'
                )
            },
            {"Cookie": "osint_admin_session=session-secret; osint_admin_session=other"},
            {"Cookie": "osint_admin_session=unknown"},
        ]
        for headers in malformed_headers:
            with self.subTest(headers=headers):
                self.assertIsNone(manager.authorize_session(headers, [], mutation=False))
                self.assertEqual(manager.session_payload(headers), {"authenticated": False})

        self.assertIsNotNone(manager.authorize_session({"Cookie": cookie}, [], mutation=False))

    def test_logout_revokes_session_and_immediately_expires_cookie(self):
        manager, _clock, _result, cookie = logged_in_manager()

        set_cookie = manager.logout({"Cookie": cookie})

        self.assertIn("osint_admin_session=", set_cookie)
        self.assertIn("Max-Age=0", set_cookie)
        self.assertIn(
            "expires=thu, 01 jan 1970 00:00:00 gmt", set_cookie.lower()
        )
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)
        self.assertIn("Path=/", set_cookie)
        self.assertIn("Secure", set_cookie)
        self.assertIsNone(
            manager.authorize_session({"Cookie": cookie}, [], mutation=False)
        )

    def test_logout_revokes_valid_session_despite_malformed_neighbor_cookie(self):
        manager, _clock, _result, cookie = logged_in_manager()

        manager.logout({"Cookie": f"malformed; {cookie}"})

        self.assertIsNone(
            manager.authorize_session({"Cookie": cookie}, [], mutation=False)
        )

    def test_development_cookie_omits_secure_attribute(self):
        manager, _clock, result, cookie = logged_in_manager(secure_cookie=False)

        self.assertNotIn("; Secure", result.set_cookie)
        expired_cookie = manager.logout({"Cookie": cookie})
        self.assertNotIn("; Secure", expired_cookie)


if __name__ == "__main__":
    unittest.main()
