import sys
import tempfile
import unittest
from pathlib import Path

from app.tools.base import MAX_OUTPUT_BYTES, ToolCommand, run_tool_command


class ToolCommandTests(unittest.TestCase):
    def test_stdout_excerpt_marks_output_limit_exceeded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            command = ToolCommand(
                args=[
                    sys.executable,
                    "-c",
                    f"import sys; sys.stdout.write('x' * {MAX_OUTPUT_BYTES + 1024})",
                ],
                cwd=Path(tmpdir),
                expected_artifact=Path(tmpdir) / "artifact.json",
                timeout_seconds=10,
            )

            result = run_tool_command(command)

        self.assertEqual(result.returncode, 0)
        self.assertLessEqual(len(result.stdout_excerpt), MAX_OUTPUT_BYTES + 128)
        self.assertIn("[output limit exceeded]", result.stdout_excerpt)


if __name__ == "__main__":
    unittest.main()
