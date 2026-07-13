import json
import os
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen as stdlib_urlopen

import scripts.real_acceptance as real_acceptance
from scripts.real_acceptance import _execution_result, load_manifest, run_acceptance_manifest, validate_manifest


class _JsonResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self._body


def _manifest(**case_overrides):
    case = {
        "id": "authorized-domain",
        "name": "Authorized domain acceptance case",
        "seed_type": "domain",
        "seed_value": "acceptance.example",
        "real_target": True,
        "minimum_evidence": ["official_website", "business_scope"],
    }
    case.update(case_overrides)
    return {"version": 1, "cases": [case]}


def _case_result(seed_type):
    return {
        "case_id": f"authorized-{seed_type}",
        "seed_type": seed_type,
        "status": "COMPLETED",
        "completed": True,
        "manual_intervention_required": False,
        "evidence_floor_met": True,
        "identity_conflict": False,
        "reviewed_conflict_outcomes": [],
        "poll_count": 1,
    }


class RealAcceptanceTests(unittest.TestCase):
    def test_load_manifest_reads_json_document(self):
        manifest = _manifest()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            self.assertEqual(load_manifest(path), manifest)

    @patch("scripts.real_acceptance.urlopen")
    def test_dry_run_validates_manifest_without_http(self, urlopen_mock):
        result = run_acceptance_manifest(_manifest(real_target=False), execute=False)

        self.assertFalse(result["executed"])
        self.assertFalse(result["benchmark_established"])
        self.assertEqual(result["result_kind"], "dry_run_not_a_benchmark")
        self.assertEqual(result["case_count"], 1)
        self.assertIsNone(result["reviewed_false_conflict_rate"])
        urlopen_mock.assert_not_called()

    def test_validate_manifest_rejects_duplicate_case_ids(self):
        manifest = _manifest()
        manifest["cases"].append({**manifest["cases"][0]})

        with self.assertRaisesRegex(ValueError, "duplicate case id"):
            validate_manifest(manifest)

    def test_validate_manifest_rejects_unsupported_seed_type(self):
        with self.assertRaisesRegex(ValueError, "unsupported seed_type"):
            validate_manifest(_manifest(seed_type="email"))

    def test_validate_manifest_rejects_empty_minimum_evidence(self):
        with self.assertRaisesRegex(ValueError, "minimum_evidence"):
            validate_manifest(_manifest(minimum_evidence=[]))

    def test_polling_validation_rejects_nonfinite_intervals(self):
        for interval in (float("nan"), float("inf")):
            with self.subTest(interval=interval):
                with self.assertRaisesRegex(ValueError, "finite"):
                    real_acceptance._validate_polling(1, interval, 30)

    def test_no_redirect_handler_rejects_each_redirect_status_with_http_error(self):
        self.assertIsNot(real_acceptance.urlopen, stdlib_urlopen)
        handler = getattr(real_acceptance, "_NoRedirectHandler", None)

        self.assertIsNotNone(handler)
        headers = Message()
        headers["Location"] = "https://unapproved.example/redirected"
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                with self.assertRaises(HTTPError) as raised:
                    getattr(handler(), f"http_error_{status}")(
                        Request("https://approved.example/api/investigations"),
                        None,
                        status,
                        "Found",
                        headers,
                    )
                self.assertEqual(raised.exception.code, status)
                raised.exception.close()

    @patch("scripts.real_acceptance.urlopen")
    @patch.dict(os.environ, {"REAL_ACCEPTANCE_TOKEN": "test-token"}, clear=True)
    def test_execute_records_redirect_http_error_as_non_success(self, urlopen_mock):
        redirect_error = HTTPError(
            "https://approved.example/api/investigations",
            302,
            "redirect rejected",
            None,
            None,
        )
        urlopen_mock.side_effect = redirect_error

        result = run_acceptance_manifest(
            _manifest(),
            execute=True,
            base_url="https://approved.example",
            token_env="REAL_ACCEPTANCE_TOKEN",
        )

        self.assertEqual(result["status_counts"], {"UNREACHABLE": 1})
        self.assertEqual(result["completion_rate"], 0.0)
        self.assertEqual(result["manual_intervention_rate"], 1.0)
        self.assertEqual(urlopen_mock.call_count, 1)
        self.assertTrue(redirect_error.closed)

    @patch("scripts.real_acceptance.urlopen")
    @patch.dict(os.environ, {"REAL_ACCEPTANCE_TOKEN": "test-token"}, clear=True)
    def test_execute_rejects_nonreal_case_before_network(self, urlopen_mock):
        with self.assertRaisesRegex(ValueError, "real_target"):
            run_acceptance_manifest(
                _manifest(real_target=False),
                execute=True,
                base_url="https://acceptance.example",
                token_env="REAL_ACCEPTANCE_TOKEN",
            )

        urlopen_mock.assert_not_called()

    @patch("scripts.real_acceptance.urlopen")
    @patch.dict(os.environ, {}, clear=True)
    def test_execute_requires_token_from_requested_environment_variable(self, urlopen_mock):
        with self.assertRaisesRegex(ValueError, "token"):
            run_acceptance_manifest(
                _manifest(),
                execute=True,
                base_url="https://acceptance.example",
                token_env="REAL_ACCEPTANCE_TOKEN",
            )

        urlopen_mock.assert_not_called()

    @patch("scripts.real_acceptance.urlopen")
    @patch.dict(os.environ, {"REAL_ACCEPTANCE_TOKEN": "test-token"}, clear=True)
    def test_execute_rejects_remote_http_base_url_before_network(self, urlopen_mock):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            run_acceptance_manifest(
                _manifest(),
                execute=True,
                base_url="http://acceptance.example",
                token_env="REAL_ACCEPTANCE_TOKEN",
            )

        urlopen_mock.assert_not_called()

    @patch("scripts.real_acceptance.urlopen")
    @patch.dict(os.environ, {"REAL_ACCEPTANCE_TOKEN": "test-token"}, clear=True)
    def test_execute_posts_create_and_run_then_polls_detail(self, urlopen_mock):
        urlopen_mock.side_effect = [
            _JsonResponse({"id": "investigation-123"}),
            _JsonResponse({"accepted": True, "status": "QUEUED"}),
            _JsonResponse({"id": "investigation-123", "status": "RUNNING"}),
            _JsonResponse(
                {
                    "id": "investigation-123",
                    "status": "COMPLETED",
                    "completion_policy": {
                        "completion_mode": "strict",
                        "manual_decision_required": False,
                        "evidence_floor": {
                            "identity": True,
                            "official_website": True,
                            "business_scope": True,
                        },
                    },
                    "cross_verification_matrix": [
                        {
                            "field_key": "company_identity",
                            "status": "CONFLICTED",
                            "reviewed_conflict_outcome": "false_conflict",
                        }
                    ],
                }
            ),
        ]

        result = run_acceptance_manifest(
            _manifest(),
            execute=True,
            base_url="https://acceptance.example",
            token_env="REAL_ACCEPTANCE_TOKEN",
            max_polls=2,
        )

        self.assertTrue(result["executed"])
        self.assertFalse(result["benchmark_established"])
        self.assertEqual(result["status_counts"], {"COMPLETED": 1})
        self.assertEqual(result["completion_rate"], 1.0)
        self.assertEqual(result["manual_intervention_rate"], 0.0)
        self.assertEqual(result["evidence_floor_rate"], 1.0)
        self.assertEqual(result["identity_conflict_rate"], 1.0)
        self.assertEqual(result["reviewed_false_conflict_rate"], 1.0)
        self.assertEqual(urlopen_mock.call_count, 4)

        requests = [call.args[0] for call in urlopen_mock.call_args_list]
        self.assertEqual([request.get_method() for request in requests], ["POST", "POST", "GET", "GET"])
        self.assertEqual(
            [request.full_url for request in requests],
            [
                "https://acceptance.example/api/investigations",
                "https://acceptance.example/api/investigations/investigation-123/run-jobs",
                "https://acceptance.example/api/investigations/investigation-123",
                "https://acceptance.example/api/investigations/investigation-123",
            ],
        )
        self.assertEqual(
            json.loads(requests[0].data.decode("utf-8")),
            {
                "name": "Authorized domain acceptance case",
                "seed_type": "domain",
                "seed_value": "acceptance.example",
            },
        )
        self.assertEqual(json.loads(requests[1].data.decode("utf-8")), {})
        self.assertEqual(requests[0].get_header("Authorization"), "Bearer test-token")

    def test_execution_result_establishes_benchmark_for_all_three_seed_cohorts(self):
        result = _execution_result(
            [
                _case_result("domain"),
                _case_result("company"),
                _case_result("sparse_lead"),
            ]
        )

        self.assertTrue(result["benchmark_established"])


if __name__ == "__main__":
    unittest.main()
