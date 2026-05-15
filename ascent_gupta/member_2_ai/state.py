"""
Chimera Pipeline — Graph State Definition
Matches the official Project_Chimera_Architecture.md spec (v2 — CTF Mode).
"""
from typing import Annotated, TypedDict, List
import operator
import uuid

# pyrefly: ignore [missing-import]
from langchain_core.messages import BaseMessage


class GraphState(TypedDict):
    """
    The single source of truth passed between every node in the
    LangGraph state machine.  Field names and semantics are locked
    to the architecture doc so Member 1 and Member 3 can rely on them.
    """

    # ── identity ──────────────────────────────────────────────────
    trace_id: str                 # Unique run identifier (UUID4)

    # ── ingress ───────────────────────────────────────────────────
    alert_payload: dict           # Raw webhook JSON from the SIEM

    # ── conversation ──────────────────────────────────────────────
    messages: Annotated[List[BaseMessage], operator.add]  # Append-only chat log

    # ── scout outputs ─────────────────────────────────────────────
    target_topography: str        # Condensed 5-line summary of logs/services

    # ── investigator outputs ──────────────────────────────────────
    current_hypothesis: str       # The suspected vulnerability type
    exploit_proof: str            # The exact payload string that succeeded
    captured_flag: str            # Content of /flag.txt (CTF proof of exploitation)

    # ── architect outputs ─────────────────────────────────────────
    remediation_patch: str        # Generated git-diff style patch
    original_source: str          # Pre-patch file contents for rollback

    # ── control flow ──────────────────────────────────────────────
    status: str                   # scouting | investigating | patching | resolved | failed
    iteration_count: int          # Loop guard — max 10 (Evaluator enforces)
    retry_count: int              # Transient failure tracker


def create_initial_state(alert_payload: dict) -> GraphState:
    """Factory that produces a clean initial state for a new pipeline run."""
    return GraphState(
        trace_id=str(uuid.uuid4()),
        alert_payload=alert_payload,
        messages=[],
        target_topography="",
        current_hypothesis="",
        exploit_proof="",
        captured_flag="",
        remediation_patch="",
        original_source="",
        status="scouting",
        iteration_count=0,
        retry_count=0,
    )
