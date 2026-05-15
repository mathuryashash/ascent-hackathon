"""
Project Chimera — Security Tool Functions
==========================================
These are the exact functions the LangGraph agents will call via TOOL_REGISTRY.
"""

import os
import shutil
import datetime
import urllib.parse
import pathlib
import subprocess
import tempfile
from typing import Optional

import docker

# ─────────────────────────────────────────────────────────────────────────────
# Environment Configuration
# ─────────────────────────────────────────────────────────────────────────────

LOG_PATH = os.environ.get("LOG_PATH", "/app/victim-logs/access.log")
VICTIM_SRC_PATH = os.environ.get("VICTIM_SRC_PATH", "/app/victim-src/")
SANDBOX_CONTAINER_NAME = os.environ.get("SANDBOX_CONTAINER", "chimera-sandbox")
VICTIM_HOST = os.environ.get("VICTIM_HOST", "http://chimera-victim:5000")

SUSPICIOUS_KEYWORDS = ["UNION", "SELECT", "--", "OR 1=1", "DROP", "INSERT", "'"]
SQL_ERROR_INDICATORS = [
    "sqlite3.OperationalError",
    "syntax error",
    "SQLITE_ERROR",
    "no such column",
    "unrecognized token",
]

# ─────────────────────────────────────────────────────────────────────────────
# Tool 1: get_logs
# ─────────────────────────────────────────────────────────────────────────────

def get_logs(tail_lines: int = 50) -> dict:
    """Reads the last N lines from the victim's access.log file."""
    try:
        log_file = pathlib.Path(LOG_PATH)
        if not log_file.exists():
            return {"status": "error", "message": f"Log file not found at {LOG_PATH}"}

        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        tail = [line.rstrip() for line in all_lines[-tail_lines:]]
        suspicious = [line for line in tail if any(kw.lower() in line.lower() for kw in SUSPICIOUS_KEYWORDS)]

        return {
            "status": "success",
            "log_lines": tail,
            "suspicious_entries": suspicious
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# Tool 2: execute_bash_in_sandbox
# ─────────────────────────────────────────────────────────────────────────────

def execute_bash_in_sandbox(command: str, timeout_seconds: int = 30) -> dict:
    """Executes a bash command INSIDE the sandbox container."""
    try:
        client = docker.from_env()
        container = client.containers.get(SANDBOX_CONTAINER_NAME)
        exec_result = container.exec_run(cmd=["bash", "-c", command], demux=True)
        
        exit_code = exec_result.exit_code
        stdout_raw, stderr_raw = exec_result.output if exec_result.output else (b"", b"")
        stdout = stdout_raw.decode("utf-8", errors="replace").strip() if stdout_raw else ""
        stderr = stderr_raw.decode("utf-8", errors="replace").strip() if stderr_raw else ""

        return {
            "status": "success" if exit_code == 0 else "error",
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# Tool 3: run_http_probe
# ─────────────────────────────────────────────────────────────────────────────

def run_http_probe(path: str, params: Optional[dict] = None, method: str = "GET") -> dict:
    """Makes an HTTP request to the Victim App from inside the Sandbox."""
    try:
        encoded_params = urllib.parse.urlencode(params or {})
        url = f"{VICTIM_HOST}{path}"
        if encoded_params: url = f"{url}?{encoded_params}"

        curl_cmd = f'curl -s --globoff -o - -w "\\n%{{http_code}}" --max-time 10 "{url}"'
        if method.upper() == "POST":
            curl_cmd = f'curl -s --globoff -o - -w "\\n%{{http_code}}" --max-time 10 -X POST "{url}"'

        result = execute_bash_in_sandbox(curl_cmd)
        if result["status"] == "error": return result

        raw_output = result["stdout"]
        lines = raw_output.rsplit("\n", 1)
        body = lines[0].strip() if len(lines) == 2 else raw_output
        http_status = int(lines[1].strip()) if len(lines) == 2 else 0
        contains_sql_error = any(indicator.lower() in body.lower() for indicator in SQL_ERROR_INDICATORS)

        return {
            "status": "success",
            "http_status_code": http_status,
            "response_body": body,
            "contains_sql_error": contains_sql_error
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# Tool 4: verify_patch (Supports Unified Diffs)
# ─────────────────────────────────────────────────────────────────────────────

def verify_patch(file_path: str, diff: str) -> dict:
    """Applies a unified diff to a file and verifies it patches cleanly."""
    full_path = os.path.join(VICTIM_SRC_PATH, file_path)
    if not os.path.isfile(full_path):
        return {"status": "error", "message": f"File not found: {full_path}"}

    patch_fd, patch_path = tempfile.mkstemp(suffix=".patch")
    try:
        with os.fdopen(patch_fd, "w") as f:
            f.write(diff)

        # Apply patch using git apply
        apply = subprocess.run(
            ["git", "apply", patch_path],
            capture_output=True, text=True, timeout=30, cwd=VICTIM_SRC_PATH
        )
        if apply.returncode == 0:
            return {"status": "success", "output": apply.stdout}
        else:
            return {"status": "error", "message": apply.stderr.strip() or "Patch application failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if os.path.exists(patch_path): os.unlink(patch_path)

# ─────────────────────────────────────────────────────────────────────────────
# Tool 5: get_victim_source
# ─────────────────────────────────────────────────────────────────────────────

def get_victim_source(filename: str = "app.py") -> dict:
    """Reads current source code of a Victim App file."""
    try:
        full_path = os.path.join(VICTIM_SRC_PATH, filename)
        if not os.path.exists(full_path):
            return {"status": "error", "message": f"File not found: {filename}"}
        
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        return {"status": "success", "content": content}
    except Exception as e:
        return {"status": "error", "message": str(e)}

TOOL_REGISTRY = {
    "get_logs": get_logs,
    "execute_bash_in_sandbox": execute_bash_in_sandbox,
    "run_http_probe": run_http_probe,
    "verify_patch": verify_patch,
    "get_victim_source": get_victim_source,
}
