"""
Project Chimera — Security Tool Functions
==========================================
These are the exact functions the LangGraph agents will call via TOOL_REGISTRY.

All functions:
  - Have complete, typed signatures
  - Return JSON-serializable dicts
  - Handle errors gracefully (never raise unhandled exceptions)
  - Return {"status": "error", "message": "..."} on failure

Member 2 imports these as:
    from tools.security_tools import TOOL_REGISTRY
    # Then binds them to LangGraph nodes via tool_node

Docker socket must be mounted into this container:
    /var/run/docker.sock:/var/run/docker.sock
"""

import os
import shutil
import datetime
import urllib.parse
import pathlib
from typing import Optional

import docker  # pip install docker>=6.0.0

# ─────────────────────────────────────────────────────────────────────────────
# Environment Configuration
# ─────────────────────────────────────────────────────────────────────────────

LOG_PATH = os.environ.get("LOG_PATH", "/app/victim-logs/access.log")
VICTIM_SRC_PATH = os.environ.get("VICTIM_SRC_PATH", "/app/victim-src/")
SANDBOX_CONTAINER_NAME = "chimera-sandbox"
VICTIM_HOST = "http://chimera-victim:5000"

# Patterns that indicate suspicious SQL injection activity
SUSPICIOUS_KEYWORDS = ["UNION", "SELECT", "--", "OR 1=1", "DROP", "INSERT", "'"]

# Strings in HTTP response bodies that indicate a SQLite error was triggered
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
    """
    Reads the last N lines from the victim's access.log file.
    The log file is mounted at LOG_PATH inside the orchestrator container.

    Returns:
        {
            "status": "success",
            "log_lines": ["line1", "line2", ...],
            "suspicious_entries": ["line with UNION SELECT...", ...]
        }
    """
    try:
        log_file = pathlib.Path(LOG_PATH)

        if not log_file.exists():
            return {
                "status": "error",
                "message": f"Log file not found at {LOG_PATH}",
                "log_lines": [],
                "suspicious_entries": []
            }

        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        tail = [line.rstrip() for line in all_lines[-tail_lines:]]

        suspicious = [
            line for line in tail
            if any(kw.lower() in line.lower() for kw in SUSPICIOUS_KEYWORDS)
        ]

        return {
            "status": "success",
            "log_path": str(LOG_PATH),
            "total_lines_read": len(all_lines),
            "tail_lines_requested": tail_lines,
            "log_lines": tail,
            "suspicious_entries": suspicious
        }

    except PermissionError as e:
        return {"status": "error", "message": f"Permission denied reading log: {e}", "log_lines": [], "suspicious_entries": []}
    except Exception as e:
        return {"status": "error", "message": str(e), "log_lines": [], "suspicious_entries": []}


# ─────────────────────────────────────────────────────────────────────────────
# Tool 2: execute_bash_in_sandbox
# ─────────────────────────────────────────────────────────────────────────────

def execute_bash_in_sandbox(command: str, timeout_seconds: int = 30) -> dict:
    """
    Executes a bash command INSIDE the chimera-sandbox container using Docker SDK.
    The sandbox can reach the victim at http://chimera-victim:5000

    Args:
        command: The bash command to run
        timeout_seconds: Max execution time before kill

    Returns:
        {
            "status": "success" | "error" | "timeout",
            "stdout": "...",
            "stderr": "...",
            "exit_code": 0,
            "command_executed": "..."
        }
    """
    try:
        client = docker.from_env()
        container = client.containers.get(SANDBOX_CONTAINER_NAME)

        exec_result = container.exec_run(
            cmd=["bash", "-c", command],
            demux=True,   # Split stdout and stderr into separate streams
        )

        exit_code = exec_result.exit_code
        stdout_raw, stderr_raw = exec_result.output if exec_result.output else (b"", b"")

        stdout = stdout_raw.decode("utf-8", errors="replace").strip() if stdout_raw else ""
        stderr = stderr_raw.decode("utf-8", errors="replace").strip() if stderr_raw else ""

        return {
            "status": "success" if exit_code == 0 else "error",
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "command_executed": command
        }

    except docker.errors.NotFound:
        return {
            "status": "error",
            "message": f"Container '{SANDBOX_CONTAINER_NAME}' not found. Is Docker Compose running?",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "command_executed": command
        }
    except docker.errors.APIError as e:
        return {
            "status": "error",
            "message": f"Docker API error: {e}",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "command_executed": command
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "command_executed": command
        }


# ─────────────────────────────────────────────────────────────────────────────
# Tool 3: run_http_probe
# ─────────────────────────────────────────────────────────────────────────────

def run_http_probe(
    path: str,
    params: Optional[dict] = None,
    method: str = "GET"
) -> dict:
    """
    Makes an HTTP request to the Victim App from inside the Sandbox container.
    Safer abstraction over execute_bash_in_sandbox for HTTP testing.

    Args:
        path: URL path, e.g. "/search"
        params: Query parameters dict, e.g. {"q": "' OR 1=1--"}
        method: "GET" or "POST"

    Returns:
        {
            "status": "success" | "error",
            "http_status_code": 200,
            "response_body": "...",
            "response_length": 1234,
            "contains_sql_error": True | False,
            "payload_used": "..."
        }
    """
    try:
        # Build the URL with query string.
        # urllib.parse.urlencode correctly encodes special chars (', space, etc.)
        # e.g. "' UNION SELECT 1,2,3--" -> "%27%20UNION%20SELECT%201%2C2%2C3--"
        encoded_params = urllib.parse.urlencode(params or {})
        url = f"{VICTIM_HOST}{path}"
        if encoded_params:
            url = f"{url}?{encoded_params}"

        payload_used = url

        # --globoff: disables curl's glob/range expansion so special chars in URLs
        # (single quotes, brackets, braces) are passed through literally.
        # Required for curl 8.x+ which rejects unencoded special characters.
        curl_cmd = f'curl -s --globoff -o - -w "\\n%{{http_code}}" --max-time 10 "{url}"'

        if method.upper() == "POST":
            curl_cmd = f'curl -s --globoff -o - -w "\\n%{{http_code}}" --max-time 10 -X POST "{url}"'

        result = execute_bash_in_sandbox(curl_cmd)

        if result["status"] == "error" and result["exit_code"] == -1:
            return {
                "status": "error",
                "message": result.get("message", "Sandbox execution failed"),
                "http_status_code": None,
                "response_body": "",
                "response_length": 0,
                "contains_sql_error": False,
                "payload_used": payload_used
            }

        raw_output = result["stdout"]

        # curl -w appends the status code as the last line
        lines = raw_output.rsplit("\n", 1)
        if len(lines) == 2:
            body = lines[0].strip()
            try:
                http_status = int(lines[1].strip())
            except ValueError:
                http_status = 0
        else:
            body = raw_output
            http_status = 0

        contains_sql_error = any(indicator.lower() in body.lower() for indicator in SQL_ERROR_INDICATORS)

        return {
            "status": "success",
            "http_status_code": http_status,
            "response_body": body,
            "response_length": len(body),
            "contains_sql_error": contains_sql_error,
            "payload_used": payload_used
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "http_status_code": None,
            "response_body": "",
            "response_length": 0,
            "contains_sql_error": False,
            "payload_used": str(params)
        }


# ─────────────────────────────────────────────────────────────────────────────
# Tool 4: apply_patch_to_victim
# ─────────────────────────────────────────────────────────────────────────────

def apply_patch_to_victim(filename: str, patched_content: str) -> dict:
    """
    Writes patched file content directly to the Victim App's source.
    Used by the Architect agent after generating the fix.

    Args:
        filename: Relative path within victim app, e.g. "app.py"
        patched_content: The complete new file content (full file, not a diff)

    Returns:
        {
            "status": "success" | "error",
            "filename": "app.py",
            "bytes_written": 1234,
            "backup_created": True,
            "backup_path": "app.py.bak"
        }
    """
    try:
        base_path = pathlib.Path(VICTIM_SRC_PATH)
        target_file = base_path / filename
        backup_path = base_path / f"{filename}.bak"

        # Ensure target is within the victim source directory (path traversal protection)
        target_file = target_file.resolve()
        if not str(target_file).startswith(str(base_path.resolve())):
            return {
                "status": "error",
                "message": f"Path traversal attempt detected for filename: {filename}"
            }

        backup_created = False
        if target_file.exists():
            shutil.copy2(target_file, backup_path)
            backup_created = True

        # Write the patched content
        target_file.parent.mkdir(parents=True, exist_ok=True)
        encoded = patched_content.encode("utf-8")
        target_file.write_bytes(encoded)
        bytes_written = len(encoded)

        return {
            "status": "success",
            "filename": filename,
            "bytes_written": bytes_written,
            "backup_created": backup_created,
            "backup_path": str(backup_path) if backup_created else None,
            "patched_at": datetime.datetime.utcnow().isoformat() + "Z"
        }

    except PermissionError as e:
        return {"status": "error", "message": f"Permission denied writing file: {e}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Tool 5: get_victim_source
# ─────────────────────────────────────────────────────────────────────────────

def get_victim_source(filename: str = "app.py") -> dict:
    """
    Reads the current source code of a Victim App file.
    Used by the Architect agent to understand what to patch.

    Args:
        filename: Relative path within victim app

    Returns:
        {
            "status": "success" | "error",
            "filename": "app.py",
            "content": "...",
            "line_count": 45
        }
    """
    try:
        base_path = pathlib.Path(VICTIM_SRC_PATH)
        target_file = (base_path / filename).resolve()

        # Path traversal protection
        if not str(target_file).startswith(str(base_path.resolve())):
            return {
                "status": "error",
                "message": f"Path traversal attempt detected for filename: {filename}"
            }

        if not target_file.exists():
            return {
                "status": "error",
                "message": f"File not found: {filename} (looked in {VICTIM_SRC_PATH})"
            }

        content = target_file.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        return {
            "status": "success",
            "filename": filename,
            "full_path": str(target_file),
            "content": content,
            "line_count": len(lines)
        }

    except PermissionError as e:
        return {"status": "error", "message": f"Permission denied reading file: {e}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# TOOL_REGISTRY — Member 2 imports this for LangGraph tool binding
# ─────────────────────────────────────────────────────────────────────────────
# Usage:
#   from tools.security_tools import TOOL_REGISTRY
#   tools = list(TOOL_REGISTRY.values())  # Pass to LangGraph ToolNode

TOOL_REGISTRY = {
    "get_logs": get_logs,
    "execute_bash_in_sandbox": execute_bash_in_sandbox,
    "run_http_probe": run_http_probe,
    "apply_patch_to_victim": apply_patch_to_victim,
    "get_victim_source": get_victim_source,
}


# ─────────────────────────────────────────────────────────────────────────────
# Quick self-test (run directly: python security_tools.py)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== TOOL_REGISTRY ===")
    for name, fn in TOOL_REGISTRY.items():
        print(f"  ✅ {name}: {fn.__doc__.strip().splitlines()[0]}")
    print("\n=== get_logs() quick test ===")
    result = get_logs(tail_lines=5)
    print(f"  Status: {result['status']}")
    print(f"  Lines read: {len(result.get('log_lines', []))}")
    print(f"  Suspicious: {len(result.get('suspicious_entries', []))}")
