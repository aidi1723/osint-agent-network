from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://saas.upkuajing.com"
TRADE_LIST_PATH = "/customs/trade/list"


class UpkuajingCustomsError(RuntimeError):
    def __init__(self, message: str, status: int = 502, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {"detail": message}


@dataclass(frozen=True)
class UpkuajingCustomsConfig:
    base_url: str
    authorization: str
    timeout_seconds: float = 30.0

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.authorization)


class UpkuajingCustomsClient:
    def __init__(self, config: UpkuajingCustomsConfig | None = None):
        self.config = config or load_upkuajing_customs_config()

    def trade_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.config.configured:
            raise UpkuajingCustomsError(
                "Upkuajing customs API is not configured. Set UPKUAJING_AUTHORIZATION.",
                status=503,
            )
        return self._post_json(TRADE_LIST_PATH, payload)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            _join_url(self.config.base_url, path),
            data=body,
            headers={
                "Authorization": self.config.authorization,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return _decode_json_response(response.read())
        except HTTPError as exc:
            error_payload = _decode_json_response(exc.read(), fallback={"detail": exc.reason})
            raise UpkuajingCustomsError(
                f"Upkuajing customs API returned HTTP {exc.code}",
                status=502,
                payload={"detail": "upstream customs api error", "upstream_status": exc.code, "upstream": error_payload},
            ) from exc
        except URLError as exc:
            raise UpkuajingCustomsError(
                f"Could not reach Upkuajing customs API: {exc.reason}",
                status=502,
            ) from exc
        except TimeoutError as exc:
            raise UpkuajingCustomsError("Upkuajing customs API request timed out.", status=504) from exc


def load_upkuajing_customs_config() -> UpkuajingCustomsConfig:
    timeout = os.getenv("UPKUAJING_TIMEOUT_SECONDS", "30")
    try:
        timeout_seconds = float(timeout)
    except ValueError:
        timeout_seconds = 30.0
    return UpkuajingCustomsConfig(
        base_url=os.getenv("UPKUAJING_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        authorization=os.getenv("UPKUAJING_AUTHORIZATION", ""),
        timeout_seconds=timeout_seconds,
    )


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _decode_json_response(body: bytes, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not body:
        return fallback or {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return fallback or {"detail": "upstream response was not valid JSON"}
    return payload if isinstance(payload, dict) else {"data": payload}
