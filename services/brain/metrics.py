"""
metrics.py — Prometheus-compatible metrics for Project Chimera.

Exposes:
  - runs_total          Counter  Total pipeline runs initiated
  - runs_resolved       Counter  Runs that reached 'resolved' status
  - runs_failed         Counter  Runs that reached 'failed' status
  - run_duration_seconds Histogram  Time from ingress to terminal state
  - active_runs         Gauge    Currently in-progress runs
  - iterations_per_run  Histogram  Number of Investigator loops per run
  - flag_capture_rate   Gauge    Fraction of resolved runs that captured the flag

Usage (in FastAPI):
    from metrics import registry, record_run_start, record_run_end, record_iteration
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi import FastAPI
    from fastapi.responses import Response

    app = FastAPI()

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
"""
from __future__ import annotations

import time
from typing import Optional

try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Registry (isolated from the default global to avoid collisions in tests)
# ---------------------------------------------------------------------------
if _PROMETHEUS_AVAILABLE:
    registry = CollectorRegistry()

    _runs_total = Counter(
        "chimera_runs_total",
        "Total number of Chimera pipeline runs initiated",
        registry=registry,
    )
    _runs_resolved = Counter(
        "chimera_runs_resolved_total",
        "Runs that reached resolved status",
        registry=registry,
    )
    _runs_failed = Counter(
        "chimera_runs_failed_total",
        "Runs that reached failed status",
        registry=registry,
    )
    _active_runs = Gauge(
        "chimera_active_runs",
        "Number of in-progress pipeline runs",
        registry=registry,
    )
    _run_duration = Histogram(
        "chimera_run_duration_seconds",
        "Wall-clock time from ingress to terminal state",
        buckets=[10, 30, 60, 120, 240, 480, 900, 1800],
        registry=registry,
    )
    _iterations = Histogram(
        "chimera_iterations_per_run",
        "Number of Investigator→Sandbox loops per run",
        buckets=[1, 2, 3, 5, 7, 10],
        registry=registry,
    )
    _flag_capture_rate = Gauge(
        "chimera_flag_capture_rate",
        "Fraction of all runs where the flag was successfully captured",
        registry=registry,
    )

# ---------------------------------------------------------------------------
# In-memory tracking (used even without prometheus_client)
# ---------------------------------------------------------------------------
_run_starts: dict[str, float] = {}   # trace_id → epoch
_totals = {"total": 0, "resolved": 0, "failed": 0, "flag_captured": 0}


def record_run_start(trace_id: str) -> None:
    """Call when a new pipeline run begins (after ingress node)."""
    _run_starts[trace_id] = time.time()
    _totals["total"] += 1
    if _PROMETHEUS_AVAILABLE:
        _runs_total.inc()
        _active_runs.inc()


def record_run_end(trace_id: str, status: str, iteration_count: int = 0, flag_captured: bool = False) -> None:
    """Call when a run reaches a terminal state (resolved or failed)."""
    start = _run_starts.pop(trace_id, None)
    duration = time.time() - start if start else 0.0

    _totals[status if status in ("resolved", "failed") else "failed"] += 1
    if flag_captured:
        _totals["flag_captured"] += 1

    if _PROMETHEUS_AVAILABLE:
        _active_runs.dec()
        _run_duration.observe(duration)
        _iterations.observe(iteration_count)

        if status == "resolved":
            _runs_resolved.inc()
        else:
            _runs_failed.inc()

        total = _totals["total"]
        if total > 0:
            _flag_capture_rate.set(_totals["flag_captured"] / total)


def record_iteration(trace_id: str) -> None:
    """Increment iteration gauge — called each time Evaluator routes back to Investigator."""
    pass  # tracked via iteration_count in run_end; hook reserved for future per-run tracking


def prometheus_text() -> Optional[bytes]:
    """Return Prometheus text format for /metrics scrape endpoint."""
    if not _PROMETHEUS_AVAILABLE:
        return None
    return generate_latest(registry)
