"""
Project Chimera — Security Tool Functions
==========================================
These are the exact functions the LangGraph agents will call via TOOL_REGISTRY.
"""

import os
import shutil
import subprocess  # noqa: F401 — imported for unittest.mock.patch testability
import datetime
import urllib.parse
import pathlib
from typing import Optional

import docker

# ─────────────────────────────────────────────────────────────────────────────
# Environment Configuration
# ─────────────────────────────────────────────────────────────────────────────

LOG_PATH = os.environ.get("LOG_PATH", "/app/victim-logs/access.log")
VICTIM_SRC_PATH = os.environ.get("VICTIM_SRC_PATH", "/app/victim-src/")
SANDBOX_CONTAINER_NAME = os.environ.get("SANDBOX_CONTAINER", "chimera-sandbox")
VICTIM_CONTAINER_NAME = os.environ.get("VICTIM_CONTAINER", "chimera-victim-1")
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
        return {
            "status": "error", 
            "message": str(e),
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1
        }

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
        return {"status": "error", "message": str(e), "exit_code": -1}

# ─────────────────────────────────────────────────────────────────────────────
# Tool 3: run_http_probe
# ─────────────────────────────────────────────────────────────────────────────

def run_http_probe(path: str, params: Optional[dict] = None, method: str = "GET", host_override: Optional[str] = None) -> dict:
    """Makes an HTTP request to the Victim App from inside the Sandbox."""
    try:
        encoded_params = urllib.parse.urlencode(params or {})
        base = host_override or VICTIM_HOST
        url = f"{base}{path}"
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
        return {
            "status": "error", 
            "message": str(e),
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1
        }

# ─────────────────────────────────────────────────────────────────────────────
# Tool 4: verify_patch (Supports Unified Diffs)
# ─────────────────────────────────────────────────────────────────────────────

def verify_patch(file_path: str, new_content: str) -> dict:
    """Writes full file content to the victim source file (overwrites in place).

    The Architect node produces complete patched file content — not a unified
    diff — so we write it directly rather than going through git apply, which
    would require the directory to be a git repository.
    """
    full_path = os.path.join(VICTIM_SRC_PATH, file_path)
    if not os.path.isfile(full_path):
        return {"status": "error", "message": f"File not found: {full_path}"}

    backup_path = full_path + ".bak"
    try:
        shutil.copy2(full_path, backup_path)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return {"status": "success", "output": f"Wrote {len(new_content)} bytes to {full_path}"}
    except Exception as e:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, full_path)
        return {"status": "error", "message": str(e)}
    finally:
        if os.path.exists(backup_path):
            os.unlink(backup_path)

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
        return {
            "status": "error", 
            "message": str(e),
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1
        }

def restart_victim_container(wait_timeout: int = 45) -> dict:
    """Restarts the victim container and waits for it to be healthy."""
    import time
    try:
        client = docker.from_env()
        container = client.containers.get(VICTIM_CONTAINER_NAME)
        container.restart(timeout=10)
        deadline = time.time() + wait_timeout
        while time.time() < deadline:
            container.reload()
            health = container.attrs.get("State", {}).get("Health", {}).get("Status", "")
            if health == "healthy":
                return {"status": "success"}
            if health == "unhealthy":
                return {"status": "error", "message": "Victim became unhealthy after restart"}
            time.sleep(2)
        return {"status": "error", "message": "Timed out waiting for victim health"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_vulnerabilities(query: str) -> dict:
    """Researches a vulnerability or CWE online to find exploitation techniques."""
    try:
        # In a production environment, this would call Firecrawl or Tavily.
        # For the hackathon, we'll provide a high-quality knowledge retrieval stub
        # that mimics a successful web search result.
        knowledge_base = {
            "sql injection": "Technique: UNION SELECT to extract schema. Steps: 1. Find column count. 2. Locate sensitive tables (users, secrets). 3. Extract data.",
            "rce": "Technique: Command injection via shell meta-characters. Steps: 1. Test for blind injection. 2. Attempt reverse shell.",
            "cwe-89": "CWE-89: Improper Neutralization of Special Elements used in an SQL Command. Remediation: Parameterized queries."
        }

        result = next((v for k, v in knowledge_base.items() if k in query.lower()), 
                      "General security best practices: Check for input sanitization and use least privilege.")

        return {
            "status": "success",
            "query": query,
            "results": [{"title": f"Research for {query}", "content": result}]
        }
    except Exception as e:
        return {
            "status": "error", 
            "message": str(e),
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1
        }

TOOL_REGISTRY = {
    "get_logs": get_logs,
    "execute_bash_sandboxed": execute_bash_in_sandbox,
    "run_http_probe": run_http_probe,
    "verify_patch": verify_patch,
    "get_victim_source": get_victim_source,
    "search_vulnerabilities": search_vulnerabilities,
}

