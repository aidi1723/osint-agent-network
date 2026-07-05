from __future__ import annotations

from dataclasses import dataclass
import json
import os
from urllib import request


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 30

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    @property
    def redacted_api_key(self) -> str:
        return redact_secret(self.api_key)


class LLMClient:
    def __init__(self, config: LLMConfig | None = None, transport=None):
        self.config = config or load_llm_config()
        self._transport = transport or _post_json

    def status(self) -> dict:
        return {
            "enabled": self.config.enabled,
            "base_url": self.config.base_url,
            "model": self.config.model,
            "api_key": self.config.redacted_api_key,
        }

    def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> str:
        if not self.config.enabled:
            raise RuntimeError("LLM relay is not configured")
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }
        data = self._transport(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            payload,
            headers,
            self.config.timeout_seconds,
        )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM relay response did not contain message content") from exc


def load_llm_config() -> LLMConfig:
    base_url = os.getenv("OSINT_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ""
    api_key = os.getenv("OSINT_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    model = os.getenv("OSINT_LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-5.4"
    timeout = int(os.getenv("OSINT_LLM_TIMEOUT", "30"))
    return LLMConfig(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=model,
        timeout_seconds=timeout,
    )


def redact_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) < 10:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method="POST")
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))
