"""
tools.py — Low-level bridge between LangGraph agents and the Docker infrastructure.

Exposes three validated tool functions consumed by the Orchestrator:
  - get_logs(service_name, lines)         → str
  - execute_bash_sandboxed(command)       → dict
  - verify_patch(file_path, diff)         → dict
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Optional

import docker
from tenacity import retry, stop_after_attempt, wait_exponential

# ---------------------------------------------------------------------------
# Docker client (lazy singleton — host-side only, never inside a container)
# ---------------------------------------------------------------------------
_client: Optional[docker.DockerClient] = None


def _docker() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


SANDBOX_CONTAINER = os.getenv("SANDBOX_CONTAINER", "chimera-sandbox-1")
EXEC_TIMEOUT = int(os.getenv("EXEC_TIMEOUT", "10"))


# ---------------------------------------------------------------------------
# Tool 1: get_logs
# ---------------------------------------------------------------------------
def get_logs(service_name: str, lines: int = 100) -> str:
    """
    Fetch the last `lines` log lines from a named Docker container.

    Returns the decoded log text, or an [ERROR] string on failure so
    the LangGraph agent can handle it gracefully.
    """
    try:
        container = _docker().containers.get(service_name)
        return container.logs(tail=lines, timestamps=True).decode("utf-8", errors="replace")
    except docker.errors.NotFound:
        return f"[ERROR] Container '{service_name}' not found."
    except docker.errors.APIError as exc:
        return f"[ERROR] Docker API error: {exc}"


# ---------------------------------------------------------------------------
# Tool 2: execute_bash_sandboxed
# ---------------------------------------------------------------------------
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def execute_bash_sandboxed(command: str, timeout: int = EXEC_TIMEOUT) -> dict:
    """
    Execute a bash command inside the isolated sandbox container.

    The sandbox has network access only to the victim on `internal_net`.
    Retries up to 3× with exponential back-off on transient Docker errors.

    Returns:
        {
          "exit_code": int,
          "output":    str,
          "success":   bool,
        }
    """
    try:
        container = _docker().containers.get(SANDBOX_CONTAINER)
        exit_code, raw_output = container.exec_run(
            cmd=["bash", "-c", command],
            user="sandboxuser",
            timeout=timeout,
            demux=False,
        )
        output = raw_output.decode("utf-8", errors="replace") if raw_output else ""
        return {"exit_code": exit_code, "output": output, "success": exit_code == 0}
    except docker.errors.NotFound:
        return {"exit_code": -1, "output": f"Sandbox container '{SANDBOX_CONTAINER}' not running.", "success": False}
    except docker.errors.APIError as exc:
        return {"exit_code": -1, "output": f"Docker API error: {exc}", "success": False}


# ---------------------------------------------------------------------------
# Tool 3: verify_patch
# ---------------------------------------------------------------------------
def verify_patch(file_path: str, diff: str) -> dict:
    """
    Apply a unified diff to `file_path` and verify it patches cleanly.

    Strategy:
      1. Back up the original file.
      2. Try `git apply` (available inside the orchestrator container).
      3. On failure, restore the backup and return the error.
      4. On success, leave the patch in place (Verifier will run the exploit next).

    Returns:
        {
          "success": bool,
          "output":  str,   # stdout from git apply
          "error":   str,   # populated on failure
        }
    """
    if not os.path.isfile(file_path):
        return {"success": False, "output": "", "error": f"File not found: {file_path}"}

    backup = file_path + ".chimera_bak"
    shutil.copy2(file_path, backup)

    patch_fd, patch_path = tempfile.mkstemp(suffix=".patch")
    try:
        with os.fdopen(patch_fd, "w") as f:
            f.write(diff)

        result = subprocess.run(
            ["git", "apply", "--check", patch_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            shutil.copy2(backup, file_path)
            return {"success": False, "output": result.stdout, "error": result.stderr.strip()}

        apply = subprocess.run(
            ["git", "apply", patch_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if apply.returncode == 0:
            return {"success": True, "output": apply.stdout, "error": ""}

        shutil.copy2(backup, file_path)
        return {"success": False, "output": apply.stdout, "error": apply.stderr.strip()}

    except subprocess.TimeoutExpired:
        shutil.copy2(backup, file_path)
        return {"success": False, "output": "", "error": "git apply timed out after 30s"}
    except FileNotFoundError:
        # git not available — fall back to the `patch` POSIX command
        return _patch_fallback(file_path, patch_path, backup)
    finally:
        os.unlink(patch_path)
        if os.path.exists(backup):
            os.unlink(backup)


def _patch_fallback(file_path: str, patch_path: str, backup: str) -> dict:
    """Fallback: apply diff with the POSIX `patch` command."""
    try:
        result = subprocess.run(
            ["patch", "--forward", "--unified", file_path, patch_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return {"success": True, "output": result.stdout, "error": ""}
        shutil.copy2(backup, file_path)
        return {"success": False, "output": result.stdout, "error": result.stderr.strip()}
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        shutil.copy2(backup, file_path)
        return {"success": False, "output": "", "error": str(exc)}
