"""
Unit tests for services/brain/tools/security_tools.py.
Docker SDK calls are mocked — no live containers needed.
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch, mock_open

# Make sure the tools package is importable from tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub out the docker module before importing security_tools
import importlib
import types

docker_stub = types.ModuleType("docker")
docker_stub.from_env = MagicMock()
sys.modules.setdefault("docker", docker_stub)

from tools.security_tools import (  # noqa: E402
    get_logs,
    execute_bash_in_sandbox,
    apply_patch_to_victim,
    SUSPICIOUS_KEYWORDS,
)


# ─────────────────────────────────────────────────────────────────────────────
# get_logs
# ─────────────────────────────────────────────────────────────────────────────

class TestGetLogs(unittest.TestCase):

    def test_returns_error_when_file_missing(self):
        with patch("tools.security_tools.LOG_PATH", "/nonexistent/path/access.log"):
            result = get_logs()
        self.assertEqual(result["status"], "error")
        self.assertIn("not found", result["message"])

    def test_returns_last_n_lines(self):
        lines = [f"line {i}\n" for i in range(20)]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.writelines(lines)
            path = f.name
        try:
            with patch("tools.security_tools.LOG_PATH", path):
                result = get_logs(tail_lines=5)
            self.assertEqual(result["status"], "success")
            self.assertEqual(len(result["log_lines"]), 5)
            self.assertEqual(result["log_lines"][-1], "line 19")
        finally:
            os.unlink(path)

    def test_flags_suspicious_entries(self):
        content = "GET /search?q=hello HTTP/1.1\nGET /search?q=' UNION SELECT 1-- HTTP/1.1\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            with patch("tools.security_tools.LOG_PATH", path):
                result = get_logs()
            self.assertEqual(result["status"], "success")
            self.assertEqual(len(result["suspicious_entries"]), 1)
            self.assertIn("UNION", result["suspicious_entries"][0])
        finally:
            os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# execute_bash_in_sandbox
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteBashInSandbox(unittest.TestCase):

    def _make_exec_result(self, exit_code, stdout=b"", stderr=b""):
        result = MagicMock()
        result.exit_code = exit_code
        result.output = (stdout, stderr)
        return result

    def test_success_returns_stdout(self):
        mock_container = MagicMock()
        mock_container.exec_run.return_value = self._make_exec_result(0, stdout=b"CHIMERA{flag}")
        docker_stub.from_env.return_value.containers.get.return_value = mock_container

        result = execute_bash_in_sandbox("curl http://victim/search?q=test")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["stdout"], "CHIMERA{flag}")
        self.assertEqual(result["exit_code"], 0)

    def test_nonzero_exit_sets_error_status(self):
        mock_container = MagicMock()
        mock_container.exec_run.return_value = self._make_exec_result(1, stderr=b"connection refused")
        docker_stub.from_env.return_value.containers.get.return_value = mock_container

        result = execute_bash_in_sandbox("curl http://missing")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["exit_code"], 1)

    def test_docker_exception_returns_error_dict(self):
        docker_stub.from_env.return_value.containers.get.side_effect = Exception("container not found")

        result = execute_bash_in_sandbox("echo hi")

        self.assertEqual(result["status"], "error")
        self.assertIn("container not found", result["message"])
        self.assertEqual(result["exit_code"], -1)
        # Reset side_effect for subsequent tests
        docker_stub.from_env.return_value.containers.get.side_effect = None


# ─────────────────────────────────────────────────────────────────────────────
# apply_patch_to_victim
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyPatchToVictim(unittest.TestCase):

    def test_returns_error_when_file_not_found(self):
        with patch("tools.security_tools.VICTIM_SRC_PATH", "/nonexistent/"):
            result = apply_patch_to_victim("app.py", "some content")
        self.assertEqual(result["status"], "error")
        self.assertIn("not found", result["message"])

    def test_full_file_write_path(self):
        content = "import flask\napp = flask.Flask(__name__)\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            app_path = os.path.join(tmpdir, "app.py")
            with open(app_path, "w") as f:
                f.write("original content")

            # src (read-only check) and dst (write) both point to same tmpdir
            with patch("tools.security_tools.VICTIM_SRC_PATH", tmpdir), \
                 patch("tools.security_tools.VICTIM_DST_PATH", tmpdir):
                result = apply_patch_to_victim("app.py", content)

            self.assertEqual(result["status"], "success")
            with open(app_path) as f:
                written = f.read()
            self.assertEqual(written, content)

    def test_full_file_write_succeeds_without_git(self):
        """Non-diff content must never invoke git apply."""
        content = "# patched file\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            app_path = os.path.join(tmpdir, "app.py")
            open(app_path, "w").close()

            with patch("tools.security_tools.VICTIM_SRC_PATH", tmpdir), \
                 patch("tools.security_tools.VICTIM_DST_PATH", tmpdir), \
                 patch("tools.security_tools.subprocess.run") as mock_run:
                result = apply_patch_to_victim("app.py", content)
                mock_run.assert_not_called()

            self.assertEqual(result["status"], "success")

    def test_diff_path_calls_git_apply(self):
        diff = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            app_path = os.path.join(tmpdir, "app.py")
            with open(app_path, "w") as f:
                f.write("old\n")

            check_result = MagicMock(returncode=0, stderr="")
            apply_result = MagicMock(returncode=0, stdout="", stderr="")

            with patch("tools.security_tools.VICTIM_SRC_PATH", tmpdir), \
                 patch("tools.security_tools.subprocess.run", side_effect=[check_result, apply_result]) as mock_run:
                result = apply_patch_to_victim("app.py", diff)

            self.assertEqual(result["status"], "success")
            self.assertEqual(mock_run.call_count, 2)
            # First call should be --check
            first_args = mock_run.call_args_list[0][0][0]
            self.assertIn("--check", first_args)


if __name__ == "__main__":
    unittest.main()
