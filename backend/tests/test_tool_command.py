import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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

    def test_run_tool_command_uses_thread_safe_process_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            command = ToolCommand(
                args=[sys.executable, "-c", "print('ok')"],
                cwd=Path(tmpdir),
                expected_artifact=Path(tmpdir) / "artifact.json",
                timeout_seconds=10,
            )
            proc = Mock()
            proc.wait.return_value = None
            proc.returncode = 0

            with patch("app.tools.base.subprocess.Popen", return_value=proc) as popen:
                run_tool_command(command)

        _, kwargs = popen.call_args
        self.assertTrue(kwargs.get("start_new_session"))
        self.assertNotIn("preexec_fn", kwargs)


if __name__ == "__main__":
    unittest.main()
