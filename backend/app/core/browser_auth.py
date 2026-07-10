from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie


@dataclass(frozen=True, slots=True)
class LoginResult:
    csrf_token: str
    set_cookie: str


@dataclass(frozen=True, slots=True)
class BrowserPrincipal:
    role: str
    session_id: str


@dataclass(slots=True)
class _Session:
    csrf_token: str
    created_at: float
    last_seen_at: float
    expires_at: float


class BrowserSessionManager:
    COOKIE_NAME = "osint_admin_session"
    DEFAULT_SESSION_TTL_SECONDS = 28_800

    def __init__(
        self,
        admin_token: str,
        secure_cookie: bool,
        session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        now: Callable[[], float] = time.time,
        token_urlsafe: Callable[[int], str] = secrets.token_urlsafe,
    ) -> None:
        self._admin_token = admin_token
        self._secure_cookie = secure_cookie
        self._session_ttl_seconds = session_ttl_seconds
        self._now = now
        self._token_urlsafe = token_urlsafe
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    def login(self, supplied_token: str) -> LoginResult | None:
        if not self._secrets_match(self._admin_token, supplied_token):
            return None

        session_id = self._token_urlsafe(32)
        csrf_token = self._token_urlsafe(32)
        timestamp = self._now()
        session = _Session(
            csrf_token=csrf_token,
            created_at=timestamp,
            last_seen_at=timestamp,
            expires_at=timestamp + self._session_ttl_seconds,
        )
        with self._lock:
            self._sessions[session_id] = session

        return LoginResult(
            csrf_token=csrf_token,
            set_cookie=self._set_cookie(session_id, max_age=self._session_ttl_seconds),
        )

    def session_payload(self, headers: Mapping[str, str]) -> dict[str, object]:
        session_id = self._validated_session_id(headers)
        if session_id is None:
            return {"authenticated": False}

        timestamp = self._now()
        with self._lock:
            session = self._live_session(session_id, timestamp)
            if session is None:
                return {"authenticated": False}
            csrf_token = self._fresh_csrf_token(session.csrf_token)
            session.csrf_token = csrf_token
            session.last_seen_at = timestamp
            return {
                "authenticated": True,
                "role": "administrator",
                "csrf_token": csrf_token,
            }

    def authorize_session(
        self,
        headers: Mapping[str, str],
        allowed_origins: Iterable[str],
        mutation: bool,
    ) -> BrowserPrincipal | None:
        session_id = self._validated_session_id(headers)
        if session_id is None:
            return None

        supplied_csrf: str | None = None
        if mutation:
            origin = self._header(headers, "origin")
            supplied_csrf = self._header(headers, "x-csrf-token")
            if origin is None or origin not in allowed_origins:
                return None

        timestamp = self._now()
        with self._lock:
            session = self._live_session(session_id, timestamp)
            if session is None:
                return None
            if mutation and not self._secrets_match(
                session.csrf_token, supplied_csrf
            ):
                return None
            session.last_seen_at = timestamp

        return BrowserPrincipal(role="administrator", session_id=session_id)

    def logout(self, headers: Mapping[str, str]) -> str:
        session_ids, _malformed = self._cookie_session_ids(headers)
        with self._lock:
            for session_id in session_ids:
                self._sessions.pop(session_id, None)
        return self._set_cookie(
            "",
            max_age=0,
            expires="Thu, 01 Jan 1970 00:00:00 GMT",
        )

    def _validated_session_id(self, headers: Mapping[str, str]) -> str | None:
        parsed_session_id = self._parsed_session_id(headers)
        session_ids, malformed = self._cookie_session_ids(headers)
        if (
            parsed_session_id is None
            or malformed
            or session_ids != [parsed_session_id]
        ):
            return None
        return parsed_session_id

    def _live_session(self, session_id: str, timestamp: float) -> _Session | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if timestamp >= session.expires_at:
            self._sessions.pop(session_id, None)
            return None
        return session

    def _fresh_csrf_token(self, previous_token: str) -> str:
        for _attempt in range(3):
            candidate = self._token_urlsafe(32)
            if not self._secrets_match(previous_token, candidate):
                return candidate
        raise RuntimeError("unable to generate a fresh CSRF token")

    def _parsed_session_id(self, headers: Mapping[str, str]) -> str | None:
        raw_cookie = self._header(headers, "cookie")
        if not raw_cookie:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(raw_cookie)
        except CookieError:
            return None
        if self.COOKIE_NAME not in cookie:
            return None
        return cookie[self.COOKIE_NAME].value

    def _cookie_session_ids(
        self, headers: Mapping[str, str]
    ) -> tuple[list[str], bool]:
        raw_cookie = self._header(headers, "cookie")
        if not raw_cookie:
            return [], False

        session_ids: list[str] = []
        malformed_target = False
        for raw_part in raw_cookie.split(";"):
            part = raw_part.strip()
            if not part:
                continue
            cookie = SimpleCookie()
            try:
                cookie.load(part)
            except CookieError:
                cookie = SimpleCookie()
            if self.COOKIE_NAME in cookie:
                session_ids.append(cookie[self.COOKIE_NAME].value)
                continue
            possible_name = part.split("=", 1)[0].strip()
            if possible_name == self.COOKIE_NAME:
                malformed_target = True

        return session_ids, malformed_target

    def _set_cookie(
        self,
        value: str,
        *,
        max_age: int,
        expires: str | None = None,
    ) -> str:
        cookie = SimpleCookie()
        cookie[self.COOKIE_NAME] = value
        morsel = cookie[self.COOKIE_NAME]
        morsel["httponly"] = True
        morsel["max-age"] = str(max_age)
        morsel["path"] = "/"
        morsel["samesite"] = "Strict"
        if expires is not None:
            morsel["expires"] = expires
        if self._secure_cookie:
            morsel["secure"] = True
        return cookie.output(header="").strip()

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str | None:
        expected = name.casefold()
        for key, value in headers.items():
            if key.casefold() == expected and isinstance(value, str):
                return value
        return None

    @staticmethod
    def _secrets_match(expected: object, supplied: object) -> bool:
        if not isinstance(expected, str) or not isinstance(supplied, str):
            return False
        expected_digest = hashlib.sha256(
            expected.encode("utf-8", errors="surrogatepass")
        ).digest()
        supplied_digest = hashlib.sha256(
            supplied.encode("utf-8", errors="surrogatepass")
        ).digest()
        return hmac.compare_digest(expected_digest, supplied_digest)
