"""
Chimera Pipeline — LangGraph State Machine
Wires up every node and defines conditional routing.

Graph topology (matches Project_Chimera_Architecture.md):

  [START] → Scout → Summarizer → Investigator → Evaluator
                                       ↑              |
                                       └── Fail ──────┤
                                                       |
                                   ┌── Success ────────┘
                                   ↓
                               Architect → Verifier
                                   ↑           |
                                   └── Fail ───┤
                                               ↓
                                    ┌── Blocked → [END / Resolved]
                                    └── Broken  → Rollback → [END / Failed]
"""
import logging
from typing import AsyncGenerator

# pyrefly: ignore [missing-import]
from langgraph.graph import StateGraph, END

from .state import GraphState, create_initial_state
from .nodes import (
    scout_node,
    summarizer_node,
    investigator_node,
    evaluator_node,
    architect_node,
    verifier_node,
    rollback_node,
)

logger = logging.getLogger("chimera.graph")


# ── Routing Functions ─────────────────────────────────────────────

def route_after_evaluator(state: GraphState) -> str:
    """Evaluator decides: loop back, move to patching, or give up."""
    status = state.get("status", "")

    if status == "patching":
        return "architect"        # Exploit proven → generate patch
    if status == "failed":
        return "human_review"     # Max iterations → stop
    return "investigator"          # Not yet proven → try again


def route_after_verifier(state: GraphState) -> str:
    """Verifier decides: resolved, retry patch, or rollback."""
    last_msg = state["messages"][-1].content.lower() if state["messages"] else ""

    blocked_markers = ["blocked", "rejected", "failed", "error", "denied", "patched", "fixed", "resolved"]
    broken_markers = ["500", "crash", "broken", "exception", "traceback", "internal server error"]

    is_blocked = any(m in last_msg for m in blocked_markers)
    is_broken = any(m in last_msg for m in broken_markers) and not is_blocked

    if is_broken:
        return "rollback"
    if is_blocked:
        return "resolved"
    return "architect"  # Exploit still works → Architect tries again


# ── Graph Builder ─────────────────────────────────────────────────

def build_graph():
    """Assemble and compile the full Chimera state machine."""
    workflow = StateGraph(GraphState)

    # ── Register nodes ────────────────────────────────────────────
    workflow.add_node("scout", scout_node)
    workflow.add_node("summarizer", summarizer_node)
    workflow.add_node("investigator", investigator_node)
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("verifier", verifier_node)
    workflow.add_node("rollback", rollback_node)

    # ── Entry ─────────────────────────────────────────────────────
    workflow.set_entry_point("scout")

    # ── Edges ─────────────────────────────────────────────────────
    workflow.add_edge("scout", "summarizer")
    workflow.add_edge("summarizer", "investigator")
    workflow.add_edge("investigator", "evaluator")

    # Evaluator → conditional branch
    workflow.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        {
            "architect": "architect",
            "investigator": "investigator",
            "human_review": END,
        },
    )

    workflow.add_edge("architect", "verifier")

    # Verifier → conditional branch
    workflow.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {
            "resolved": END,
            "architect": "architect",
            "rollback": "rollback",
        },
    )

    workflow.add_edge("rollback", END)

    return workflow.compile()


# ── Handover Function for Member 3 ───────────────────────────────

async def run_chimera_pipeline(alert_payload: dict) -> AsyncGenerator[dict, None]:
    """
    Kick off the autonomous pipeline.

    Usage by Member 3:
        async for event in run_chimera_pipeline(webhook_json):
            send_to_websocket(event)  # powers the Thinking Timeline
    """
    app = build_graph()
    initial_state = create_initial_state(alert_payload)

    logger.info("Pipeline started  (trace=%s)", initial_state["trace_id"])

    async for event in app.astream(initial_state, stream_mode="updates"):
        logger.info("Event: %s", list(event.keys()))
        yield event

    logger.info("Pipeline complete  (trace=%s)", initial_state["trace_id"])
