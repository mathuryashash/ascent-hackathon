"""
Chimera Pipeline — Tool Wrappers for LangGraph Agents
These wrap Member 1's actual tool functions from member_1_systems/tools.py
and expose them as LangChain @tool decorated functions for LLM bind_tools().

Member 1's actual signatures (from member_1_systems/tools.py):
  - get_logs(service_name: str, lines: int = 100) → str
  - execute_bash_sandboxed(command: str, timeout: int = 10) → dict
  - verify_patch(file_path: str, diff: str) → dict
"""
import os
import sys
import json
import logging

# pyrefly: ignore [missing-import]
from langchain_core.tools import tool

# Add the project root to sys.path so we can import member_1_systems
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from member_1_systems.tools import get_logs, execute_bash_sandboxed, verify_patch

logger = logging.getLogger("chimera.tools")

VICTIM_CONTAINER = os.getenv("VICTIM_CONTAINER", "chimera-victim-1")
VICTIM_SRC_PATH = os.getenv("VICTIM_SRC_PATH", "/victim_src")


# ── Scout Tools ──────────────────────────────────────────────────

@tool
def read_logs(lines: int = 50, filter_pattern: str = "") -> str:
    """Fetch recent access-log lines from the Victim App container.

    Args:
        lines: Number of recent log lines to fetch (default 50, max 500).
        filter_pattern: Optional text pattern to filter lines (e.g. 'UNION', '500').
    """
    try:
        raw = get_logs(service_name=VICTIM_CONTAINER, lines=min(lines, 500))
        if filter_pattern:
            raw = "\n".join(
                line for line in raw.splitlines()
                if filter_pattern.lower() in line.lower()
            )
        return raw if raw.strip() else "[No matching log lines found]"
    except Exception as e:
        logger.error("read_logs failed: %s", e)
        return f"[TOOL ERROR] read_logs failed: {e}"


@tool
def scan_network(target_host: str = "victim-app", ports: str = "80,5000,8080") -> str:
    """Probe open ports on the Victim container from the sandbox.

    Args:
        target_host: Hostname of the target on the Docker internal network.
        ports: Comma-separated port list to probe.
    """
    try:
        # Use the sandbox to run a quick port check via bash
        port_list = ports.replace(" ", "")
        cmd = (
            f"for p in {port_list.replace(',', ' ')}; do "
            f"(echo > /dev/tcp/{target_host}/$p) 2>/dev/null && echo \"PORT $p OPEN\" || echo \"PORT $p CLOSED\"; "
            f"done"
        )
        result = execute_bash_sandboxed(cmd, timeout=15)
        return result.get("output", str(result))
    except Exception as e:
        logger.error("scan_network failed: %s", e)
        return f"[TOOL ERROR] scan_network failed: {e}"


# ── Investigator Tools ───────────────────────────────────────────

@tool
def run_sql_query(query: str) -> str:
    """Execute a SQL injection test against the Victim App's search endpoint.

    Args:
        query: The SQL injection payload to send to the Victim's /search?q= parameter.
    """
    try:
        # Use the sandbox to curl the victim's vulnerable search endpoint
        safe_query = query.replace("'", "'\\''")  # Escape for bash
        cmd = f"curl -s 'http://victim:5000/search?q={safe_query}'"
        result = execute_bash_sandboxed(cmd, timeout=10)
        return result.get("output", str(result))
    except Exception as e:
        logger.error("run_sql_query failed: %s", e)
        return f"[TOOL ERROR] run_sql_query failed: {e}"


@tool
def execute_payload(command: str, timeout_seconds: int = 30) -> str:
    """Execute an arbitrary bash command inside the isolated Sandbox container.

    Args:
        command: The shell command or script to execute.
        timeout_seconds: Max seconds before the sandbox kills the command (5-120).
    """
    try:
        result = execute_bash_sandboxed(
            command,
            timeout=max(5, min(timeout_seconds, 120))
        )
        output = result.get("output", "")
        exit_code = result.get("exit_code", -1)
        success = result.get("success", False)
        return json.dumps({"exit_code": exit_code, "output": output, "success": success})
    except Exception as e:
        logger.error("execute_payload failed: %s", e)
        return f"[TOOL ERROR] execute_payload failed: {e}"


# ── Architect / Verifier Tools ───────────────────────────────────

@tool
def read_source(file_path: str = "app.py") -> str:
    """Read the current source code of a file in the Victim container.

    Args:
        file_path: Relative path of the source file inside the victim directory.
    """
    try:
        full_path = os.path.join(VICTIM_SRC_PATH, file_path)
        if not os.path.isfile(full_path):
            return f"[ERROR] File not found: {full_path}"
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error("read_source failed: %s", e)
        return f"[TOOL ERROR] read_source failed: {e}"


@tool
def apply_patch(patch_diff: str, target_file: str = "app.py") -> str:
    """Apply a unified-diff patch to fix a vulnerability in the Victim App.

    Args:
        patch_diff: The unified diff string to apply.
        target_file: Relative path of the file to patch inside the victim directory.
    """
    try:
        full_path = os.path.join(VICTIM_SRC_PATH, target_file)
        result = verify_patch(file_path=full_path, diff=patch_diff)
        return json.dumps(result)
    except Exception as e:
        logger.error("apply_patch failed: %s", e)
        return f"[TOOL ERROR] apply_patch failed: {e}"


# ── Tool Groups (used by nodes.py for bind_tools) ────────────────

SCOUT_TOOLS = [read_logs, scan_network]
INVESTIGATOR_TOOLS = [run_sql_query, execute_payload]
ARCHITECT_TOOLS = [read_source, apply_patch]
VERIFIER_TOOLS = [execute_payload, run_sql_query]
