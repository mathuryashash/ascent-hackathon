"""
Chimera Pipeline — Pydantic Tool Schemas
Strict JSON contracts that the LLM must follow when invoking
Member 1's sandbox tools.  These are passed to `llm.bind_tools()`.
"""
from pydantic import BaseModel, Field


# ── Recon Tools (Scout) ──────────────────────────────────────────

class ReadLogsInput(BaseModel):
    """Retrieve recent access-log lines from the Victim App."""
    lines: int = Field(
        default=50,
        description="Number of recent log lines to fetch from the Victim's access.log.",
        ge=1,
        le=500,
    )
    filter_pattern: str = Field(
        default="",
        description="Optional grep-style pattern to pre-filter log lines (e.g. 'UNION', '500').",
    )


class ScanNetworkInput(BaseModel):
    """Lightweight port/service scan of the Victim container."""
    target_host: str = Field(
        default="victim-app",
        description="Hostname or IP of the target on the Docker bridge network.",
    )
    ports: str = Field(
        default="80,443,5000,8080",
        description="Comma-separated port list to probe.",
    )


# ── Exploit Tools (Investigator) ─────────────────────────────────

class RunSQLQueryInput(BaseModel):
    """Execute a raw SQL statement against the Victim's SQLite database."""
    query: str = Field(
        ...,
        description="The SQL query to execute (e.g. a UNION SELECT injection test).",
    )


class ExecutePayloadInput(BaseModel):
    """Run an arbitrary bash command inside the isolated Sandbox container."""
    command: str = Field(
        ...,
        description="The shell command or script to execute in the sandbox.",
    )
    target_url: str = Field(
        default="http://victim-app:5000",
        description="Internal URL of the Victim App reachable from the sandbox.",
    )
    timeout_seconds: int = Field(
        default=30,
        description="Max seconds before the sandbox kills the command.",
        ge=5,
        le=120,
    )


# ── Patch Tools (Architect / Verifier) ───────────────────────────

class ApplyPatchInput(BaseModel):
    """Apply a git-diff style patch to the Victim App source code."""
    patch_diff: str = Field(
        ...,
        description="The unified diff string to apply to the vulnerable source file.",
    )
    target_file: str = Field(
        default="app.py",
        description="Relative path of the file to patch inside the Victim container.",
    )


class ReadSourceInput(BaseModel):
    """Read the current source code of a file in the Victim container."""
    file_path: str = Field(
        default="app.py",
        description="Relative path of the source file to read.",
    )
