"""
tracing.py — Structured logging and Omium verifiable tracing for Project Chimera.

Every LangGraph node transition is recorded as a trace event, creating an
immutable, verifiable audit trail of the AI's reasoning process.

Usage:
    from tracing import get_tracer, trace_node_enter, trace_node_exit

    tracer = get_tracer()

    # At the start of each LangGraph node:
    trace_node_enter(tracer, trace_id, "investigator", state)

    # At the end of each LangGraph node:
    trace_node_exit(tracer, trace_id, "investigator", state, duration_ms)
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import structlog

# ---------------------------------------------------------------------------
# Structlog configuration (JSON output for log aggregators)
# ---------------------------------------------------------------------------

def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog with JSON renderer. Call once at app startup."""
    import logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(__import__("logging"), log_level.upper(), 20)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> Any:
    """Return a structlog logger bound to a module name."""
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# Verifiable Trace Record
# ---------------------------------------------------------------------------

class TraceEvent:
    """
    An immutable record of a single node transition in the Chimera pipeline.

    Each event is content-addressed (SHA256 of its JSON payload) so judges
    can independently verify that the AI's reasoning was not modified post-hoc.
    The `parent_hash` creates a chain — altering any prior event breaks the chain.
    """

    def __init__(
        self,
        trace_id: str,
        node: str,
        event_type: str,     # "enter" | "exit" | "error"
        state_snapshot: dict,
        duration_ms: float = 0.0,
        parent_hash: str = "",
    ):
        self.trace_id = trace_id
        self.node = node
        self.event_type = event_type
        self.timestamp = time.time()
        self.duration_ms = duration_ms
        self.parent_hash = parent_hash

        # Redact sensitive fields from snapshot
        self.state_snapshot = _redact_state(state_snapshot)

        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = json.dumps({
            "trace_id": self.trace_id,
            "node": self.node,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "state_snapshot": self.state_snapshot,
            "parent_hash": self.parent_hash,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "node": self.node,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "state_snapshot": self.state_snapshot,
            "parent_hash": self.parent_hash,
            "hash": self.hash,
        }


def _redact_state(state: dict) -> dict:
    """Remove large/sensitive fields before storing in the trace event."""
    REDACT = {"original_source", "remediation_patch"}
    TRUNCATE_AT = 500

    result = {}
    for k, v in state.items():
        if k in REDACT:
            result[k] = f"<{len(str(v))} chars redacted>"
        elif isinstance(v, str) and len(v) > TRUNCATE_AT:
            result[k] = v[:TRUNCATE_AT] + "…"
        elif isinstance(v, list) and k == "messages":
            result[k] = f"<{len(v)} messages>"
        else:
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Tracer — manages a chain of events per run
# ---------------------------------------------------------------------------

class ChimeraTracer:
    """
    Manages verifiable trace chains for Chimera pipeline runs.

    Each trace_id has its own chain. Events are kept in memory and
    can be flushed to a file/database for persistence.
    """

    def __init__(self, log=None):
        self._chains: dict[str, list[TraceEvent]] = {}
        self._log = log or get_logger(__name__)

    def _last_hash(self, trace_id: str) -> str:
        chain = self._chains.get(trace_id, [])
        return chain[-1].hash if chain else ""

    def record(
        self,
        trace_id: str,
        node: str,
        event_type: str,
        state: dict,
        duration_ms: float = 0.0,
    ) -> TraceEvent:
        """Record a node transition event and append to the chain."""
        parent_hash = self._last_hash(trace_id)
        event = TraceEvent(
            trace_id=trace_id,
            node=node,
            event_type=event_type,
            state_snapshot=dict(state),
            duration_ms=duration_ms,
            parent_hash=parent_hash,
        )

        self._chains.setdefault(trace_id, []).append(event)

        self._log.info(
            "trace_event",
            trace_id=trace_id,
            node=node,
            event_type=event_type,
            status=state.get("status"),
            iteration=state.get("iteration_count"),
            hash=event.hash[:12],
            duration_ms=round(duration_ms, 1),
        )

        return event

    def get_chain(self, trace_id: str) -> list[dict]:
        """Return all events for a run as serializable dicts."""
        return [e.to_dict() for e in self._chains.get(trace_id, [])]

    def verify_chain(self, trace_id: str) -> bool:
        """
        Verify the integrity of a trace chain.
        Returns True if every event's hash is consistent with its content and parent.
        """
        chain = self._chains.get(trace_id, [])
        prev_hash = ""
        for event in chain:
            expected_hash = event._compute_hash()
            if event.hash != expected_hash:
                self._log.error("chain_tampered", trace_id=trace_id, node=event.node)
                return False
            if event.parent_hash != prev_hash:
                self._log.error("chain_broken", trace_id=trace_id, node=event.node)
                return False
            prev_hash = event.hash
        return True

    def export_chain(self, trace_id: str, path: str) -> None:
        """Write the full trace chain to a JSON file for external verification."""
        chain = self.get_chain(trace_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"trace_id": trace_id, "events": chain, "length": len(chain)}, f, indent=2)
        self._log.info("chain_exported", trace_id=trace_id, path=path, events=len(chain))


# ---------------------------------------------------------------------------
# Global singleton tracer
# ---------------------------------------------------------------------------
_tracer: ChimeraTracer | None = None


def get_tracer() -> ChimeraTracer:
    global _tracer
    if _tracer is None:
        _tracer = ChimeraTracer()
    return _tracer


# ---------------------------------------------------------------------------
# Convenience wrappers for LangGraph node instrumentation
# ---------------------------------------------------------------------------

def trace_node_enter(trace_id: str, node: str, state: dict) -> float:
    """Call at the start of a LangGraph node. Returns start time for duration tracking."""
    get_tracer().record(trace_id, node, "enter", state)
    return time.time()


def trace_node_exit(trace_id: str, node: str, state: dict, start_time: float) -> TraceEvent:
    """Call at the end of a LangGraph node with the updated state."""
    duration_ms = (time.time() - start_time) * 1000
    return get_tracer().record(trace_id, node, "exit", state, duration_ms)


def trace_node_error(trace_id: str, node: str, state: dict, error: Exception) -> TraceEvent:
    """Call when a node raises an exception."""
    get_logger().error("node_error", trace_id=trace_id, node=node, error=str(error))
    return get_tracer().record(trace_id, node, "error", {**state, "_error": str(error)})
