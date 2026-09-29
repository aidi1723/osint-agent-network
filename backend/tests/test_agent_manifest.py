from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from agent_manifest_validator import validate_repository


class AgentManifestValidationTests(unittest.TestCase):
    def test_repository_manifest_is_valid(self):
        errors = validate_repository(Path(__file__).resolve().parents[2])

        self.assertEqual(errors, [])

    def test_missing_agent_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_fixture(Path(tmp))
            manifest_path = root / "agent-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["agents"][0]["path"] = "agents/missing-agent.md"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            errors = validate_repository(root)

        self.assertTrue(any("missing agent file" in error for error in errors), errors)

    def test_missing_skill_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_fixture(Path(tmp))
            manifest_path = root / "agent-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["skills"][0]["path"] = "skills/missing/SKILL.md"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            errors = validate_repository(root)

        self.assertTrue(any("missing skill file" in error for error in errors), errors)

    def test_unknown_agent_skill_reference_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_fixture(Path(tmp))
            agent_path = root / "agents" / "enterprise-intel-agent.md"
            text = agent_path.read_text(encoding="utf-8")
            text = text.replace("  - constrained-search", "  - unknown-skill")
            agent_path.write_text(text, encoding="utf-8")

            errors = validate_repository(root)

        self.assertTrue(any("unknown frontmatter skill" in error for error in errors), errors)

    def test_invalid_output_contract_token_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _copy_fixture(Path(tmp))
            manifest_path = root / "agent-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["agents"][0]["output_contract"] = "entities,unsupported"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            errors = validate_repository(root)

        self.assertTrue(any("invalid output contract token" in error for error in errors), errors)


def _copy_fixture(tmp: Path) -> Path:
    root = tmp / "repo"
    root.mkdir()
    source_root = Path(__file__).resolve().parents[2]
    for relative in ("agent-manifest.json", "agents", "skills"):
        source = source_root / relative
        target = root / relative
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    return root


if __name__ == "__main__":
    unittest.main()
