import json
import os
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.main import ApiHandler
from app.core.upkuajing_customs import UpkuajingCustomsError
from http.server import ThreadingHTTPServer


class CustomsApiRouteTest(unittest.TestCase):
    def test_trade_list_route_requires_management_authorization(self):
        server, base_url = _start_server()
        try:
            request = Request(
                f"{base_url}/api/customs/trade/list",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with patch.dict(os.environ, {"ADMIN_API_TOKEN": "admin-secret"}, clear=False):
                with self.assertRaises(HTTPError) as raised:
                    urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 401)
            raised.exception.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_trade_list_route_proxies_payload(self):
        server, base_url = _start_server()
        calls = []

        class FakeClient:
            def trade_list(self, payload):
                calls.append(payload)
                return {"code": 0, "msg": "success", "data": {"list": [{"buyer": "ACME"}]}}

        try:
            request = Request(
                f"{base_url}/api/customs/trade/list",
                data=json.dumps({"seller": "SHANDONG ORIENT ALUMINIUM CO., LTD."}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": "Bearer admin-secret"},
                method="POST",
            )
            with patch.dict(os.environ, {"ADMIN_API_TOKEN": "admin-secret"}, clear=False):
                with patch("app.main.UpkuajingCustomsClient", return_value=FakeClient()):
                    with urlopen(request, timeout=5) as response:
                        payload = json.loads(response.read().decode("utf-8"))

            self.assertEqual(calls, [{"seller": "SHANDONG ORIENT ALUMINIUM CO., LTD."}])
            self.assertEqual(payload["data"]["list"][0]["buyer"], "ACME")
        finally:
            server.shutdown()
            server.server_close()

    def test_supply_chain_route_surfaces_customs_configuration_errors(self):
        server, base_url = _start_server()

        class FakeAdapter:
            def find_downstream_customers(self, company_name):
                raise UpkuajingCustomsError("missing customs credentials", status=503)

        try:
            request = Request(
                f"{base_url}/api/customs/supply-chain",
                data=json.dumps({"company": "Example Inc"}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": "Bearer admin-secret"},
                method="POST",
            )
            with patch.dict(os.environ, {"ADMIN_API_TOKEN": "admin-secret"}, clear=False):
                with patch("app.tools.customs_supply_chain.CustomsSupplyChainAdapter", return_value=FakeAdapter()):
                    with self.assertRaises(HTTPError) as raised:
                        urlopen(request, timeout=5)

            self.assertEqual(raised.exception.code, 503)
            try:
                payload = json.loads(raised.exception.read().decode("utf-8"))
            finally:
                raised.exception.close()
            self.assertEqual(payload["detail"], "missing customs credentials")
        finally:
            server.shutdown()
            server.server_close()


def _start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


if __name__ == "__main__":
    unittest.main()
