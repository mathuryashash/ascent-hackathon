"""
tracing.py — Structured logging and Omium verifiable tracing for Project Chimera.

Every LangGraph node transition is recorded as a trace event, creating an
immutable, verifiable audit trail of the AI's reasoning process.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import structlog

# ---------------------------------------------------------------------------
# Structlog configuration
# ---------------------------------------------------------------------------


def configure_logging(log_level: str = "INFO") -> None:
    import logging

    logging.basicConfig(
        format="%(message)s", level=getattr(logging, log_level.upper(), logging.INFO)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(name: str = __name__) -> Any:
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# Verifiable Trace Record
# ---------------------------------------------------------------------------


class TraceEvent:
    def __init__(
        self,
        trace_id: str,
        node: str,
        event_type: str,
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
        self.state_snapshot = _redact_state(state_snapshot)
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {
                "trace_id": self.trace_id,
                "node": self.node,
                "event_type": self.event_type,
                "state_snapshot": self.state_snapshot,
                "parent_hash": self.parent_hash,
            },
            sort_keys=True,
        )
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
    REDACT = {"original_source", "remediation_patch"}
    result = {}
    for k, v in state.items():
        if k in REDACT:
            result[k] = f"<{len(str(v))} chars redacted>"
        else:
            result[k] = v
    return result


class ChimeraTracer:
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
        parent_hash = self._last_hash(trace_id)
        event = TraceEvent(trace_id, node, event_type, state, duration_ms, parent_hash)
        self._chains.setdefault(trace_id, []).append(event)

        self._log.info(
            "trace_event",
            trace_id=trace_id,
            node=node,
            event_type=event_type,
            hash=event.hash[:12],
        )

        return event

    def get_chain(self, trace_id: str) -> list[dict]:
        return [e.to_dict() for e in self._chains.get(trace_id, [])]


_tracer: ChimeraTracer | None = None


def get_tracer() -> ChimeraTracer:
    global _tracer
    if _tracer is None:
        _tracer = ChimeraTracer()
    return _tracer


def trace_node_enter(trace_id: str, node: str, state: dict) -> float:
    get_tracer().record(trace_id, node, "enter", state)
    return time.time()


def trace_node_exit(
    trace_id: str, node: str, state: dict, start_time: float
) -> TraceEvent:
    duration_ms = (time.time() - start_time) * 1000
    return get_tracer().record(trace_id, node, "exit", state, duration_ms)


def trace_node_error(
    trace_id: str, node: str, state: dict, error: Exception
) -> TraceEvent:
    get_logger().error("node_error", trace_id=trace_id, node=node, error=str(error))
    return get_tracer().record(trace_id, node, "error", {**state, "_error": str(error)})
