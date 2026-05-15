"""
tools/__init__.py — Unified tool interface for Project Chimera.
Aliases physical tool implementations to the logical names expected by graph.py.
"""
from .security_tools import (
    get_logs,
    execute_bash_in_sandbox,
    apply_patch_to_victim,
    get_victim_source,
    TOOL_REGISTRY
)

# Alias for graph.py compatibility
execute_bash_sandboxed = execute_bash_in_sandbox
verify_patch = apply_patch_to_victim # Architect uses this to apply/verify

__all__ = [
    "get_logs",
    "execute_bash_sandboxed",
    "verify_patch",
    "get_victim_source",
    "TOOL_REGISTRY"
]
