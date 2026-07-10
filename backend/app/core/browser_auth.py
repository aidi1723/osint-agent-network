from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from email.message import Message
from http.cookies import CookieError, SimpleCookie


HeaderInput = Mapping[str, str] | Message


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
    csrf_tokens: deque[str]
    created_at: float
    last_seen_at: float
    expires_at: float


class BrowserSessionManager:
    COOKIE_NAME = "osint_admin_session"
    DEFAULT_SESSION_TTL_SECONDS = 28_800
    MAX_CSRF_TOKENS = 4  # Includes the token returned by login.
    MAX_LIVE_SESSIONS = 128
    TOKEN_GENERATION_ATTEMPTS = 8
    TOKEN_GENERATION_ERROR = "unable to generate unique session credentials"

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
        if not self._admin_token or not self._secrets_match(
            self._admin_token, supplied_token
        ):
            return None

        with self._lock:
            timestamp = self._now()
            self._purge_expired_sessions_locked(timestamp)
            forbidden = self._active_tokens_locked()
            session_id = self._generate_unique_token(forbidden)
            forbidden.add(session_id)
            csrf_token = self._generate_unique_token(forbidden)
            if len(self._sessions) >= self.MAX_LIVE_SESSIONS:
                self._evict_oldest_session_locked()
            session = _Session(
                csrf_tokens=deque([csrf_token], maxlen=self.MAX_CSRF_TOKENS),
                created_at=timestamp,
                last_seen_at=timestamp,
                expires_at=timestamp + self._session_ttl_seconds,
            )
            self._sessions[session_id] = session

        return LoginResult(
            csrf_token=csrf_token,
            set_cookie=self._set_cookie(session_id, max_age=self._session_ttl_seconds),
        )

    def session_payload(self, headers: HeaderInput) -> dict[str, object]:
        session_id = self._validated_session_id(headers)
        if session_id is None:
            return {"authenticated": False}

        with self._lock:
            timestamp = self._now()
            session = self._live_session_locked(session_id, timestamp)
            if session is None:
                return {"authenticated": False}
            csrf_token = self._generate_unique_token(self._active_tokens_locked())
            session.csrf_tokens.append(csrf_token)
            session.last_seen_at = timestamp
            return {
                "authenticated": True,
                "role": "administrator",
                "csrf_token": csrf_token,
            }

    def authorize_session(
        self,
        headers: HeaderInput,
        allowed_origins: Collection[str],
        mutation: bool,
    ) -> BrowserPrincipal | None:
        session_id = self._validated_session_id(headers)
        if session_id is None:
            return None

        supplied_csrf: str | None = None
        if mutation:
            if not self._valid_allowed_origins(allowed_origins):
                return None
            origin = self._header(headers, "origin")
            supplied_csrf = self._header(headers, "x-csrf-token")
            if origin is None or origin not in allowed_origins:
                return None

        with self._lock:
            timestamp = self._now()
            session = self._live_session_locked(session_id, timestamp)
            if session is None:
                return None
            if mutation and not self._csrf_token_matches(
                session.csrf_tokens, supplied_csrf
            ):
                return None
            session.last_seen_at = timestamp

        return BrowserPrincipal(role="administrator", session_id=session_id)

    def logout(self, headers: HeaderInput) -> str:
        session_ids, malformed = self._cookie_session_ids(headers)
        if not malformed and len(session_ids) == 1:
            with self._lock:
                self._sessions.pop(session_ids[0], None)
        return self._set_cookie(
            "",
            max_age=0,
            expires="Thu, 01 Jan 1970 00:00:00 GMT",
        )

    def _validated_session_id(self, headers: HeaderInput) -> str | None:
        parsed_session_id = self._parsed_session_id(headers)
        session_ids, malformed = self._cookie_session_ids(headers)
        if (
            parsed_session_id is None
            or malformed
            or session_ids != [parsed_session_id]
        ):
            return None
        return parsed_session_id

    def _live_session_locked(
        self, session_id: str, timestamp: float
    ) -> _Session | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if timestamp >= session.expires_at:
            self._sessions.pop(session_id, None)
            return None
        return session

    def _generate_unique_token(self, forbidden: set[str]) -> str:
        for _attempt in range(self.TOKEN_GENERATION_ATTEMPTS):
            candidate = self._token_urlsafe(32)
            if (
                isinstance(candidate, str)
                and candidate
                and candidate not in forbidden
            ):
                return candidate
        raise RuntimeError(self.TOKEN_GENERATION_ERROR)

    def _active_tokens_locked(self) -> set[str]:
        tokens = set(self._sessions)
        for session in self._sessions.values():
            tokens.update(session.csrf_tokens)
        return tokens

    def _purge_expired_sessions_locked(self, timestamp: float) -> None:
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if timestamp >= session.expires_at
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)

    def _evict_oldest_session_locked(self) -> None:
        oldest_session_id = min(
            self._sessions,
            key=lambda session_id: self._sessions[session_id].created_at,
        )
        self._sessions.pop(oldest_session_id, None)

    def _parsed_session_id(self, headers: HeaderInput) -> str | None:
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

    def _cookie_session_ids(self, headers: HeaderInput) -> tuple[list[str], bool]:
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
    def _header(headers: HeaderInput, name: str) -> str | None:
        if isinstance(headers, Message):
            values = headers.get_all(name, [])
            if len(values) != 1 or not isinstance(values[0], str):
                return None
            return values[0]

        expected = name.casefold()
        values: list[object] = []
        for key, value in headers.items():
            if isinstance(key, str) and key.casefold() == expected:
                values.append(value)
        if len(values) != 1 or not isinstance(values[0], str):
            return None
        return values[0]

    @staticmethod
    def _valid_allowed_origins(allowed_origins: object) -> bool:
        return (
            isinstance(allowed_origins, Collection)
            and not isinstance(allowed_origins, (str, bytes))
            and all(isinstance(origin, str) for origin in allowed_origins)
        )

    @staticmethod
    def _secrets_match(expected: object, supplied: object) -> bool:
        if not isinstance(expected, str) or not isinstance(supplied, str):
            return False
        return hmac.compare_digest(
            BrowserSessionManager._secret_digest(expected),
            BrowserSessionManager._secret_digest(supplied),
        )

    @staticmethod
    def _csrf_token_matches(
        valid_tokens: Collection[str], supplied: object
    ) -> bool:
        if not isinstance(supplied, str):
            return False
        supplied_digest = BrowserSessionManager._secret_digest(supplied)
        matches = [
            hmac.compare_digest(
                BrowserSessionManager._secret_digest(valid_token), supplied_digest
            )
            for valid_token in valid_tokens
        ]
        return any(matches)

    @staticmethod
    def _secret_digest(value: str) -> bytes:
        return hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).digest()
