import os
import unittest
from unittest.mock import patch

from app.services.llm import LLMConfig, LLMClient, load_llm_config, redact_secret
from app.main import llm_status_payload


class LLMClientTests(unittest.TestCase):
    def test_loads_osint_llm_config_and_redacts_secret(self):
        env = {
            "OSINT_LLM_BASE_URL": "http://192.0.2.10:6780/v1",
            "OSINT_LLM_API_KEY": "sk-secret-value",
            "OSINT_LLM_MODEL": "gpt-5.4",
        }

        with patch.dict(os.environ, env, clear=True):
            config = load_llm_config()

        self.assertTrue(config.enabled)
        self.assertEqual(config.base_url, "http://192.0.2.10:6780/v1")
        self.assertEqual(config.model, "gpt-5.4")
        self.assertEqual(config.redacted_api_key, "sk-s...alue")

    def test_prefers_osint_env_but_falls_back_to_openai_names(self):
        env = {
            "OPENAI_BASE_URL": "http://relay.local/v1",
            "OPENAI_API_KEY": "sk-openai-fallback",
            "OPENAI_MODEL": "gpt-5.4",
        }

        with patch.dict(os.environ, env, clear=True):
            config = load_llm_config()

        self.assertTrue(config.enabled)
        self.assertEqual(config.base_url, "http://relay.local/v1")
        self.assertEqual(config.model, "gpt-5.4")

    def test_chat_completion_posts_openai_compatible_payload_without_leaking_key(self):
        captured = {}

        def fake_transport(url, payload, headers, timeout):
            captured["url"] = url
            captured["payload"] = payload
            captured["headers"] = headers
            captured["timeout"] = timeout
            return {
                "choices": [
                    {
                        "message": {
                            "content": "模型正常"
                        }
                    }
                ]
            }

        client = LLMClient(
            LLMConfig(
                base_url="http://relay.local/v1",
                api_key="sk-secret-value",
                model="gpt-5.4",
                timeout_seconds=11,
            ),
            transport=fake_transport,
        )

        result = client.chat_completion(
            [
                {"role": "system", "content": "你是情报分析助手。"},
                {"role": "user", "content": "测试"},
            ],
            temperature=0.2,
        )

        self.assertEqual(result, "模型正常")
        self.assertEqual(captured["url"], "http://relay.local/v1/chat/completions")
        self.assertEqual(captured["payload"]["model"], "gpt-5.4")
        self.assertEqual(captured["payload"]["temperature"], 0.2)
        self.assertEqual(
            captured["headers"]["Authorization"], "Bearer " + "sk-secret-value"
        )
        self.assertNotIn("sk-secret-value", repr(client.status()))

    def test_status_payload_never_exposes_api_key(self):
        env = {
            "OSINT_LLM_BASE_URL": "http://192.0.2.10:6780/v1",
            "OSINT_LLM_API_KEY": "sk-secret-value",
            "OSINT_LLM_MODEL": "gpt-5.4",
        }

        with patch.dict(os.environ, env, clear=True):
            payload = llm_status_payload()

        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["model"], "gpt-5.4")
        self.assertEqual(payload["api_key"], "sk-s...alue")
        self.assertNotIn("sk-secret-value", repr(payload))

    def test_redact_secret_handles_empty_and_short_values(self):
        self.assertEqual(redact_secret(""), "")
        self.assertEqual(redact_secret("short"), "***")


if __name__ == "__main__":
    unittest.main()
