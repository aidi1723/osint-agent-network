import dataclasses
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
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


class ThreadSafeTokenGenerator(TokenGenerator):
    def __init__(self, *values: str):
        super().__init__(*values)
        self.lock = threading.Lock()

    def __call__(self, size: int) -> str:
        with self.lock:
            return super().__call__(size)


class ObservableLock:
    def __init__(self):
        self._lock = threading.Lock()
        self.waiting = threading.Event()

    def acquire(self) -> None:
        self._lock.acquire()

    def release(self) -> None:
        self._lock.release()

    def __enter__(self) -> "ObservableLock":
        self.waiting.set()
        self._lock.acquire()
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self._lock.release()


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


def mutation_headers(cookie: str, csrf_token: str) -> dict[str, str]:
    return {
        "Cookie": cookie,
        "Origin": "https://hcs.test",
        "X-CSRF-Token": csrf_token,
    }


def authorize_mutation(
    manager: BrowserSessionManager, cookie: str, csrf_token: str
) -> BrowserPrincipal | None:
    return manager.authorize_session(
        mutation_headers(cookie, csrf_token),
        ["https://hcs.test"],
        mutation=True,
    )


def run_after_clock_advance_while_lock_waits(
    manager: BrowserSessionManager,
    clock: MutableClock,
    advanced_time: float,
    operation,
):
    observable_lock = ObservableLock()
    manager._lock = observable_lock
    observable_lock.acquire()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(operation)
        try:
            if not observable_lock.waiting.wait(timeout=2):
                raise AssertionError("operation did not attempt the session lock")
            clock.value = advanced_time
        finally:
            observable_lock.release()
        return future.result(timeout=2)


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

    def test_empty_configured_and_supplied_login_tokens_fail_closed(self):
        tokens = TokenGenerator("unused-session", "unused-csrf")
        manager = BrowserSessionManager(
            admin_token="",
            secure_cookie=True,
            now=lambda: 1_000.0,
            token_urlsafe=tokens,
        )

        self.assertIsNone(manager.login(""))
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

    def test_authorize_rechecks_time_after_waiting_for_session_lock(self):
        manager, clock, _result, cookie = logged_in_manager(
            session_ttl_seconds=10
        )

        principal = run_after_clock_advance_while_lock_waits(
            manager,
            clock,
            1_010.0,
            lambda: manager.authorize_session(
                {"Cookie": cookie}, [], mutation=False
            ),
        )

        self.assertIsNone(principal)

    def test_session_payload_rechecks_time_after_waiting_for_session_lock(self):
        clock = MutableClock(1_000.0)
        tokens = TokenGenerator(
            "session-secret", "csrf-login", "csrf-refresh"
        )
        manager = BrowserSessionManager(
            admin_token="admin-secret",
            secure_cookie=True,
            session_ttl_seconds=10,
            now=clock,
            token_urlsafe=tokens,
        )
        login = manager.login("admin-secret")
        assert login is not None
        cookie = cookie_header(login.set_cookie)

        payload = run_after_clock_advance_while_lock_waits(
            manager,
            clock,
            1_010.0,
            lambda: manager.session_payload({"Cookie": cookie}),
        )

        self.assertEqual(payload, {"authenticated": False})
        self.assertEqual(tokens.sizes, [32, 32])

    def test_login_samples_creation_and_purge_time_inside_session_lock(self):
        clock = MutableClock(1_000.0)
        tokens = TokenGenerator(
            "session-old", "csrf-old", "session-new", "csrf-new"
        )
        manager = BrowserSessionManager(
            admin_token="admin-secret",
            secure_cookie=True,
            session_ttl_seconds=10,
            now=clock,
            token_urlsafe=tokens,
        )
        old_login = manager.login("admin-secret")
        assert old_login is not None

        new_login = run_after_clock_advance_while_lock_waits(
            manager,
            clock,
            1_010.0,
            lambda: manager.login("admin-secret"),
        )

        assert new_login is not None
        new_cookie = cookie_header(new_login.set_cookie)
        with self.subTest("expired session purged at lock acquisition time"):
            self.assertEqual(set(manager._sessions), {"session-new"})
        with self.subTest("new session lifetime starts at lock acquisition time"):
            self.assertIsNotNone(
                manager.authorize_session(
                    {"Cookie": new_cookie}, [], mutation=False
                )
            )

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

        first = manager.session_payload({"cookie": cookie})

        self.assertEqual(first["csrf_token"], "csrf-rotated-first")
        self.assertNotEqual(first["csrf_token"], login.csrf_token)
        self.assertNotIn("session_id", first)
        self.assertIsNotNone(
            authorize_mutation(manager, cookie, login.csrf_token)
        )
        self.assertIsNotNone(
            authorize_mutation(manager, cookie, first["csrf_token"])
        )

        second = manager.session_payload({"Cookie": cookie})

        self.assertEqual(second["csrf_token"], "csrf-rotated-second")
        self.assertNotEqual(second["csrf_token"], first["csrf_token"])
        self.assertIsNotNone(
            authorize_mutation(manager, cookie, login.csrf_token)
        )
        self.assertIsNotNone(
            authorize_mutation(manager, cookie, first["csrf_token"])
        )
        self.assertIsNotNone(
            authorize_mutation(manager, cookie, second["csrf_token"])
        )
        self.assertEqual(manager.session_payload({}), {"authenticated": False})
        self.assertEqual(tokens.sizes, [32, 32, 32, 32])

    def test_concurrent_session_payload_tokens_remain_valid(self):
        tokens = ThreadSafeTokenGenerator(
            "session-secret",
            "csrf-login",
            "csrf-refresh-one",
            "csrf-refresh-two",
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
        barrier = threading.Barrier(3)
        payloads: list[dict[str, object]] = []

        def refresh() -> None:
            barrier.wait()
            payloads.append(manager.session_payload({"Cookie": cookie}))

        threads = [threading.Thread(target=refresh) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=2)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        csrf_tokens = {payload["csrf_token"] for payload in payloads}
        self.assertEqual(csrf_tokens, {"csrf-refresh-one", "csrf-refresh-two"})
        for csrf_token in csrf_tokens:
            self.assertIsNotNone(authorize_mutation(manager, cookie, csrf_token))

    def test_csrf_window_evicts_only_tokens_beyond_bound(self):
        tokens = TokenGenerator(
            "session-secret",
            "csrf-login",
            "csrf-refresh-one",
            "csrf-refresh-two",
            "csrf-refresh-three",
            "csrf-refresh-four",
            "csrf-refresh-five",
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
        refreshes = [
            manager.session_payload({"Cookie": cookie})["csrf_token"]
            for _ in range(5)
        ]

        self.assertEqual(manager.MAX_CSRF_TOKENS, 4)
        self.assertIsNone(authorize_mutation(manager, cookie, login.csrf_token))
        self.assertIsNone(authorize_mutation(manager, cookie, refreshes[0]))
        for csrf_token in refreshes[-4:]:
            self.assertIsNotNone(authorize_mutation(manager, cookie, csrf_token))

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

    def test_mutation_rejects_scalar_and_one_shot_allowed_origins(self):
        manager, _clock, result, cookie = logged_in_manager()
        headers = mutation_headers(cookie, result.csrf_token)

        invalid_allowed_origins = [
            "prefix-https://hcs.test-suffix",
            b"prefix-https://hcs.test-suffix",
            iter(["https://hcs.test"]),
        ]
        for allowed_origins in invalid_allowed_origins:
            with self.subTest(allowed_origins=allowed_origins):
                self.assertIsNone(
                    manager.authorize_session(
                        headers, allowed_origins, mutation=True
                    )
                )

    def test_duplicate_security_headers_never_authorize(self):
        manager, _clock, result, cookie = logged_in_manager()

        repeated_cookie = Message()
        repeated_cookie["Cookie"] = cookie
        repeated_cookie["Cookie"] = "osint_admin_session=unknown"

        repeated_origin = Message()
        repeated_origin["Cookie"] = cookie
        repeated_origin["Origin"] = "https://hcs.test"
        repeated_origin["Origin"] = "https://other.test"
        repeated_origin["X-CSRF-Token"] = result.csrf_token

        repeated_csrf = Message()
        repeated_csrf["Cookie"] = cookie
        repeated_csrf["Origin"] = "https://hcs.test"
        repeated_csrf["X-CSRF-Token"] = result.csrf_token
        repeated_csrf["X-CSRF-Token"] = "wrong"

        self.assertIsNone(
            manager.authorize_session(repeated_cookie, [], mutation=False)
        )
        self.assertIsNone(
            manager.authorize_session(
                repeated_origin, ["https://hcs.test"], mutation=True
            )
        )
        self.assertIsNone(
            manager.authorize_session(
                repeated_csrf, ["https://hcs.test"], mutation=True
            )
        )

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

    def test_logout_rejects_ambiguous_cookie_headers_without_revoking(self):
        manager, _clock, _result, cookie = logged_in_manager()
        headers = Message()
        headers["Cookie"] = cookie
        headers["Cookie"] = "osint_admin_session=unknown"

        manager.logout(headers)

        self.assertIsNotNone(
            manager.authorize_session({"Cookie": cookie}, [], mutation=False)
        )
        manager.logout(
            {"Cookie": f"{cookie}; osint_admin_session=unknown"}
        )
        self.assertIsNotNone(
            manager.authorize_session({"Cookie": cookie}, [], mutation=False)
        )
        manager.logout({"Cookie": cookie})
        self.assertIsNone(
            manager.authorize_session({"Cookie": cookie}, [], mutation=False)
        )

    def test_login_retries_session_id_and_global_csrf_collisions(self):
        tokens = TokenGenerator(
            "session-one",
            "csrf-one",
            "session-one",
            "session-two",
            "csrf-one",
            "csrf-two",
        )
        manager = BrowserSessionManager(
            admin_token="admin-secret",
            secure_cookie=True,
            now=lambda: 1_000.0,
            token_urlsafe=tokens,
        )

        first = manager.login("admin-secret")
        second = manager.login("admin-secret")

        assert first is not None and second is not None
        first_cookie = cookie_header(first.set_cookie)
        second_cookie = cookie_header(second.set_cookie)
        self.assertEqual(first_cookie, "osint_admin_session=session-one")
        self.assertEqual(second_cookie, "osint_admin_session=session-two")
        self.assertIsNotNone(authorize_mutation(manager, first_cookie, "csrf-one"))
        self.assertIsNotNone(authorize_mutation(manager, second_cookie, "csrf-two"))
        self.assertEqual(tokens.sizes, [32] * 6)

    def test_refresh_retries_session_id_and_valid_csrf_collisions(self):
        tokens = TokenGenerator(
            "session-secret",
            "csrf-login",
            "session-secret",
            "csrf-login",
            "csrf-refresh",
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

        payload = manager.session_payload({"Cookie": cookie})

        self.assertEqual(payload["csrf_token"], "csrf-refresh")
        self.assertIsNotNone(authorize_mutation(manager, cookie, "csrf-login"))
        self.assertIsNotNone(authorize_mutation(manager, cookie, "csrf-refresh"))
        self.assertEqual(tokens.sizes, [32] * 5)

    def test_generation_fails_stably_after_bounded_collisions(self):
        manager = BrowserSessionManager(
            admin_token="admin-secret",
            secure_cookie=True,
            now=lambda: 1_000.0,
            token_urlsafe=lambda _size: "collision",
        )

        with self.assertRaisesRegex(
            RuntimeError, "^unable to generate unique session credentials$"
        ) as raised:
            manager.login("admin-secret")

        self.assertNotIn("admin-secret", str(raised.exception))

    def test_login_purges_expired_sessions(self):
        clock = MutableClock(1_000.0)
        tokens = TokenGenerator("session-one", "csrf-one", "session-two", "csrf-two")
        manager = BrowserSessionManager(
            admin_token="admin-secret",
            secure_cookie=True,
            session_ttl_seconds=10,
            now=clock,
            token_urlsafe=tokens,
        )
        manager.login("admin-secret")

        clock.value = 1_010.0
        manager.login("admin-secret")

        self.assertEqual(set(manager._sessions), {"session-two"})

    def test_login_evicts_oldest_session_at_live_session_bound(self):
        limit = 128
        values = [
            value
            for index in range(limit + 1)
            for value in (f"session-{index}", f"csrf-{index}")
        ]
        tokens = TokenGenerator(*values)
        clock = MutableClock(1_000.0)
        manager = BrowserSessionManager(
            admin_token="admin-secret",
            secure_cookie=True,
            now=clock,
            token_urlsafe=tokens,
        )
        cookies: list[str] = []
        for index in range(limit + 1):
            clock.value = 1_000.0 + index
            login = manager.login("admin-secret")
            assert login is not None
            cookies.append(cookie_header(login.set_cookie))

        self.assertEqual(len(manager._sessions), limit)
        self.assertEqual(manager.MAX_LIVE_SESSIONS, limit)
        self.assertIsNone(
            manager.authorize_session({"Cookie": cookies[0]}, [], mutation=False)
        )
        self.assertIsNotNone(
            manager.authorize_session({"Cookie": cookies[1]}, [], mutation=False)
        )
        self.assertIsNotNone(
            manager.authorize_session({"Cookie": cookies[-1]}, [], mutation=False)
        )

    def test_development_cookie_omits_secure_attribute(self):
        manager, _clock, result, cookie = logged_in_manager(secure_cookie=False)

        self.assertNotIn("; Secure", result.set_cookie)
        expired_cookie = manager.logout({"Cookie": cookie})
        self.assertNotIn("; Secure", expired_cookie)


if __name__ == "__main__":
    unittest.main()
