import json
import unittest
from unittest.mock import patch

from app.core.upkuajing_customs import (
    UpkuajingCustomsClient,
    UpkuajingCustomsConfig,
    UpkuajingCustomsError,
    load_upkuajing_customs_config,
)


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class UpkuajingCustomsClientTest(unittest.TestCase):
    def test_loads_config_from_environment(self):
        with patch.dict(
            "os.environ",
            {
                "UPKUAJING_BASE_URL": "https://example.test/",
                "UPKUAJING_AUTHORIZATION": "Bearer secret",
                "UPKUAJING_TIMEOUT_SECONDS": "12.5",
            },
            clear=False,
        ):
            config = load_upkuajing_customs_config()

        self.assertEqual(config.base_url, "https://example.test")
        self.assertEqual(config.authorization, "Bearer secret")
        self.assertEqual(config.timeout_seconds, 12.5)

    def test_requires_authorization_before_request(self):
        client = UpkuajingCustomsClient(
            UpkuajingCustomsConfig(base_url="https://example.test", authorization="")
        )

        with self.assertRaises(UpkuajingCustomsError) as raised:
            client.trade_list({"seller": "SHANDONG ORIENT ALUMINIUM CO., LTD."})

        self.assertEqual(raised.exception.status, 503)
        self.assertIn("not configured", str(raised.exception))

    def test_trade_list_posts_json_with_authorization(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({"code": 0, "msg": "success", "data": {"list": []}})

        client = UpkuajingCustomsClient(
            UpkuajingCustomsConfig(
                base_url="https://example.test",
                authorization="Bearer secret",
                timeout_seconds=9,
            )
        )
        with patch("app.core.upkuajing_customs.urlopen", fake_urlopen):
            result = client.trade_list({"seller": "SHANDONG ORIENT ALUMINIUM CO., LTD."})

        self.assertEqual(captured["url"], "https://example.test/customs/trade/list")
        self.assertEqual(captured["timeout"], 9)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(captured["headers"]["Content-type"], "application/json")
        self.assertEqual(captured["body"]["seller"], "SHANDONG ORIENT ALUMINIUM CO., LTD.")
        self.assertEqual(result["code"], 0)


if __name__ == "__main__":
    unittest.main()
