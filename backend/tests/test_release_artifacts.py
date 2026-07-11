import unittest
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


class ReleaseArtifactTests(unittest.TestCase):
    def test_backend_package_discovery_excludes_runtime_data(self):
        config = tomllib.loads(
            (ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
        )

        package_find = (
            config.get("tool", {})
            .get("setuptools", {})
            .get("packages", {})
            .get("find")
        )
        self.assertEqual(
            package_find,
            {"include": ["app*"], "exclude": ["data*", "tests*"]},
        )

    def test_production_compose_uses_built_images_and_healthchecks(self):
        compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

        self.assertIn("build:", compose)
        self.assertIn("backend/Dockerfile", compose)
        self.assertIn("frontend/Dockerfile", compose)
        self.assertIn("healthcheck:", compose)
        self.assertNotIn("npm install && npm run dev", compose)

    def test_frontend_nginx_proxies_api_to_backend_service(self):
        config = (ROOT / "deploy" / "nginx" / "default.conf").read_text(encoding="utf-8")

        self.assertIn("try_files $uri $uri/ /index.html", config)
        self.assertIn("proxy_pass http://api:8088", config)

    def test_publish_readiness_documents_gplv3_release_gate(self):
        doc = (ROOT / "docs" / "PUBLIC_RELEASE_READINESS.md").read_text(encoding="utf-8")

        self.assertIn("GPLv3 release gate", doc)
        self.assertIn("GPL-3.0-only", doc)
        self.assertIn("python3 scripts/public_release_check.py", doc)
        self.assertIn("runtime inventory", doc.lower())

    def test_license_options_document_records_selected_gplv3_license(self):
        doc = (ROOT / "docs" / "OPEN_SOURCE_LICENSE_OPTIONS.md").read_text(encoding="utf-8")

        self.assertIn("Selected license", doc)
        self.assertIn("GPL-3.0-only", doc)
        self.assertIn("strong copyleft", doc)


if __name__ == "__main__":
    unittest.main()
