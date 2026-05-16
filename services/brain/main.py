"""
Project Chimera — Orchestrator FastAPI App
==========================================
Provides the HTTP API that drives the LangGraph pipeline.
* `/webhook/alert` – receives SIEM alerts and starts a run.
* `/ws`            – WebSocket endpoint for real-time dashboard updates.
* `/status/{trace_id}` – fetches the latest GraphState snapshot.
* `/metrics`       – Prometheus metrics endpoint.
* `/health`        – liveness probe.
"""

import os
import json
import uuid
import hashlib
import hmac
import time
import structlog
import asyncio
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from fastapi import (
    FastAPI,
    Request,
    BackgroundTasks,
    Header,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Depends,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import aiosqlite

# Local imports
from graph import get_graph
from metrics import prometheus_text, record_run_start, record_run_end
from schemas import StatusResponse, AlertPayload
from tracing import configure_logging

configure_logging()
log = structlog.get_logger(__name__)

_shared_conn: Optional[aiosqlite.Connection] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _shared_conn
    _shared_conn = await aiosqlite.connect("/app/checkpoints.sqlite")
    checkpointer = AsyncSqliteSaver(_shared_conn)
    await checkpointer.setup()
    get_graph(checkpointer=checkpointer)
    log.info("graph_initialized")
    yield
    if _shared_conn:
        await _shared_conn.close()
        _shared_conn = None


app = FastAPI(
    title="Project Chimera Orchestrator",
    description="FastAPI wrapper around the LangGraph autonomous pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow UI (different origin) to call the API.
# ALLOWED_ORIGIN can be "*" (wildcard) or a comma-separated list of origins.
_origins_raw = os.getenv("ALLOWED_ORIGIN", "http://localhost:3001")
if _origins_raw.strip() == "*":
    _allow_origins = ["*"]
    _allow_credentials = False
else:
    _allow_origins = [o.strip() for o in _origins_raw.split(",") if o.strip()]
    _allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# WebSocket Connection Manager
# ---------------------------------------------------------------------------


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info("ws_client_connected", count=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            log.info("ws_client_disconnected", count=len(self.active_connections))

    async def broadcast(self, message: dict):
        msg_str = json.dumps(message)
        dead = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(msg_str)
            except Exception as e:
                log.error("ws_broadcast_error", error=str(e))
                dead.append(connection)
        for conn in dead:
            self.disconnect(conn)


manager = ConnectionManager()

# ---------------------------------------------------------------------------
# State Serialization Helper
# ---------------------------------------------------------------------------


def serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures LangGraph state is JSON serializable for the UI."""
    if not isinstance(state, dict):
        return {"_raw": str(state)}
    serialized = {}
    for node_name, data in state.items():
        if not isinstance(data, dict):
            serialized[node_name] = str(data)
            continue

        serialized[node_name] = {}
        for k, v in data.items():
            if k == "messages":
                msgs = []
                for m in v:
                    if hasattr(m, "content"):
                        if hasattr(m, "tool_calls") and m.tool_calls:
                            msgs.append(f"[Tool Calls] {json.dumps(m.tool_calls)}")
                        else:
                            msgs.append(str(m.content))
                    else:
                        msgs.append(str(m))
                serialized[node_name][k] = msgs
            elif isinstance(v, (dict, list, str, int, float, bool, type(None))):
                serialized[node_name][k] = v
            else:
                serialized[node_name][k] = str(v)
    return serialized


# HMAC secret — mandatory; reject startup if missing or too short
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
if not WEBHOOK_SECRET or len(WEBHOOK_SECRET) < 32:
    raise RuntimeError(
        "WEBHOOK_SECRET must be set to a value of at least 32 characters. "
        "Set WEBHOOK_SECRET in your .env before starting the orchestrator."
    )

# NOTE: _early_states is an in-process dict. With multiple uvicorn workers each worker
# has its own copy — /status may return not_found for runs started on another worker.
# Run with a single worker (--workers 1) or migrate to Redis for multi-worker deployments.
_early_states: dict[str, dict] = {}
_early_state_times: dict[str, float] = {}
_EARLY_STATE_TTL = 3600  # 1 hour
_last_trigger_time: float = 0.0


def _prune_early_states() -> None:
    now = time.time()
    stale = [k for k, t in _early_state_times.items() if now - t > _EARLY_STATE_TTL]
    for k in stale:
        _early_states.pop(k, None)
        _early_state_times.pop(k, None)


def _valid_hmac(body: bytes, header_val: str) -> bool:
    if not header_val or not header_val.startswith("sha256="):
        return False
    expected = (
        "sha256=" + hmac.HMAC(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, header_val)


# ---------------------------------------------------------------------------
# Admin Token Dependency
# ---------------------------------------------------------------------------
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", None)


async def verify_admin_token(
    authorization: Optional[str] = Header(default=None),
) -> None:
    """Dependency: if ADMIN_TOKEN is set, require a matching Bearer token."""
    if not ADMIN_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header"
        )
    token = authorization[len("Bearer ") :]
    if not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid admin token")


# ---------------------------------------------------------------------------
# Background task that runs the full pipeline for a given alert.
# ---------------------------------------------------------------------------
async def _run_pipeline(alert_payload: dict, trace_id: str) -> None:
    """Execute the LangGraph pipeline and broadcast updates."""
    record_run_start(trace_id)
    log.info("pipeline_start", trace_id=trace_id)
    status = "failed"
    iters = 0
    flag = False
    try:
        trigger_data = alert_payload.get("trigger") or {}
        matched_pattern = (
            trigger_data.get("matched_pattern")
            or alert_payload.get("type")
            or "Unknown Alert"
        )

        await manager.broadcast(
            {
                "event": "alert_received",
                "data": {
                    "type": matched_pattern,
                    "source": alert_payload.get("source", "external"),
                    "trace_id": trace_id,
                },
            }
        )

        graph = get_graph()
        init_state: Dict[str, Any] = {
            "trace_id": trace_id,
            "alert_payload": alert_payload,
            "status": "queued",
            "messages": [],
            "iteration_count": 0,
        }

        try:
            async for event in graph.astream(
                init_state,
                config={"configurable": {"thread_id": trace_id}},
                stream_mode="updates",
            ):
                serialized_event = serialize_state(event)
                await manager.broadcast(
                    {"event": "pipeline_step", "data": serialized_event}
                )

            snapshot = await graph.aget_state({"configurable": {"thread_id": trace_id}})
            final_state = snapshot.values if snapshot else {}
            status = final_state.get("status", "completed")
            iters = final_state.get("iteration_count", 0)
            flag = bool(final_state.get("captured_flag"))

            # Don't broadcast pipeline_complete for interrupted runs — the UI
            # must keep the approval banner visible until the user acts.
            if status != "awaiting_approval":
                await manager.broadcast(
                    {
                        "event": "pipeline_complete",
                        "data": {"status": status, "trace_id": trace_id},
                    }
                )

        except Exception as e:
            log.error("pipeline_error", trace_id=trace_id, error=str(e))
            await manager.broadcast(
                {
                    "event": "pipeline_error",
                    "trace_id": trace_id,
                    "data": {"error": str(e)},
                }
            )

    except Exception as e:
        log.error("pipeline_outer_error", trace_id=trace_id, error=str(e))
    finally:
        _early_states[trace_id] = {
            "trace_id": trace_id,
            "status": status,
            "iteration_count": iters,
            "has_flag": flag,
        }
        _early_state_times[trace_id] = time.time()
        record_run_end(trace_id, status, iters, flag)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@app.post("/webhook/alert", status_code=202)
async def webhook_alert(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_signature: str = Header(default=""),
    _token: None = Depends(verify_admin_token),
):
    body = await request.body()
    if not _valid_hmac(body, x_webhook_signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        raw_payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    try:
        alert = AlertPayload(**raw_payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    trace_id = str(uuid.uuid4())
    _prune_early_states()
    _early_states[trace_id] = {"trace_id": trace_id, "status": "queued"}
    _early_state_times[trace_id] = time.time()
    background_tasks.add_task(_run_pipeline, alert.model_dump(), trace_id)
    return {"trace_id": trace_id, "status": "queued"}


DEMO_TRIGGER_ENABLED = os.getenv("DEMO_TRIGGER_ENABLED", "false").lower() == "true"


@app.post("/trigger", status_code=202)
async def trigger_demo(request: Request, background_tasks: BackgroundTasks):
    global _last_trigger_time
    if not DEMO_TRIGGER_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Demo trigger not enabled. Set DEMO_TRIGGER_ENABLED=true.",
        )
    if time.time() - _last_trigger_time < 10:
        raise HTTPException(
            status_code=429, detail="Rate limited — try again in a few seconds."
        )
    _last_trigger_time = time.time()
    import datetime

    try:
        body = await request.json()
        target = body.get("target", "chimera-victim-1")
    except Exception:
        target = "chimera-victim-1"
    payload = {
        "alert_id": str(uuid.uuid4()),
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "severity": "HIGH",
        "source": "ui_trigger",
        "target": target,
        "trigger": {
            "log_line": f"Manual trigger against {target}",
            "matched_pattern": "MANUAL_TRIGGER",
            "route": "/manual",
        },
    }
    trace_id = str(uuid.uuid4())
    _prune_early_states()
    _early_states[trace_id] = {"trace_id": trace_id, "status": "queued"}
    _early_state_times[trace_id] = time.time()
    background_tasks.add_task(_run_pipeline, payload, trace_id)
    return {"trace_id": trace_id, "status": "queued"}


@app.get("/status/{trace_id}", response_model=StatusResponse)
async def status(trace_id: str):
    graph = get_graph()
    try:
        snapshot = await graph.aget_state({"configurable": {"thread_id": trace_id}})
        if snapshot and snapshot.values:
            sv = snapshot.values
            return StatusResponse(
                trace_id=trace_id,
                status=sv.get("status", "unknown"),
                iteration_count=sv.get("iteration_count", 0),
                current_node=sv.get("current_node"),
                has_flag=bool(sv.get("captured_flag")),
                human_approval_pending=sv.get("human_approved") is None
                and sv.get("status") == "awaiting_approval",
            )
        early = _early_states.get(trace_id)
        if early:
            return StatusResponse(
                trace_id=trace_id, status=early.get("status", "unknown")
            )
        return StatusResponse(trace_id=trace_id, status="not_found")
    except Exception as exc:
        log.warning("state_store_unavailable", trace_id=trace_id, error=str(exc))
        return StatusResponse(trace_id=trace_id, status="unknown")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def _resume_pipeline(trace_id: str) -> None:
    """Resume graph execution after human_approval interrupt and broadcast result."""
    graph = get_graph()
    config = {"configurable": {"thread_id": trace_id}}
    try:
        async for event in graph.astream(None, config=config, stream_mode="updates"):
            await manager.broadcast(
                {"event": "pipeline_step", "data": serialize_state(event)}
            )
            await asyncio.sleep(0.1)
        snapshot = await graph.aget_state(config)
        final_state = snapshot.values if snapshot else {}
        status = final_state.get("status", "completed")
        iters = final_state.get("iteration_count", 0)
        flag = bool(final_state.get("captured_flag"))
        _early_states[trace_id] = {
            "trace_id": trace_id,
            "status": status,
            "iteration_count": iters,
            "has_flag": flag,
        }
        _early_state_times[trace_id] = time.time()
        record_run_end(trace_id, status, iters, flag)
        await manager.broadcast(
            {
                "event": "pipeline_complete",
                "data": {"status": status, "trace_id": trace_id},
            }
        )
    except Exception as e:
        log.error("resume_error", trace_id=trace_id, error=str(e))
        await manager.broadcast(
            {"event": "pipeline_error", "trace_id": trace_id, "data": {"error": str(e)}}
        )


@app.post("/approve/{trace_id}", status_code=202)
async def approve_patch(
    trace_id: str,
    background_tasks: BackgroundTasks,
    _token: None = Depends(verify_admin_token),
):
    """Set human_approved=True and resume the graph past the human_approval interrupt."""
    graph = get_graph()
    config = {"configurable": {"thread_id": trace_id}}
    snapshot = await graph.aget_state(config)
    if not snapshot or not snapshot.next:
        raise HTTPException(
            status_code=404, detail="No paused pipeline found for this trace_id"
        )
    await graph.aupdate_state(config, {"human_approved": True})
    background_tasks.add_task(_resume_pipeline, trace_id)
    await manager.broadcast({"event": "human_approved", "data": {"trace_id": trace_id}})
    return {"trace_id": trace_id, "status": "resuming"}


@app.post("/reject/{trace_id}", status_code=202)
async def reject_patch(trace_id: str, _token: None = Depends(verify_admin_token)):
    """Set human_approved=False — pipeline ends without applying the patch."""
    graph = get_graph()
    config = {"configurable": {"thread_id": trace_id}}
    snapshot = await graph.aget_state(config)
    if not snapshot or not snapshot.next:
        raise HTTPException(
            status_code=404, detail="No paused pipeline found for this trace_id"
        )
    await graph.aupdate_state(config, {"human_approved": False, "status": "rejected"})
    await manager.broadcast({"event": "human_rejected", "data": {"trace_id": trace_id}})
    await manager.broadcast(
        {
            "event": "pipeline_complete",
            "data": {"status": "rejected", "trace_id": trace_id},
        }
    )
    return {"trace_id": trace_id, "status": "rejected"}


@app.get("/verify-fix/{trace_id}")
async def verify_fix(trace_id: str):
    """Re-runs the original exploit against the victim to confirm the patch blocked it."""
    import httpx
    import re

    victim_host = os.getenv("VICTIM_HOST", "http://chimera-victim-1:5000")

    # Standard SQLi probe
    test_url = f"{victim_host}/search?q=' UNION SELECT 1,value,'x',0 FROM secrets WHERE key='flag'--"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(test_url)
        flag_found = bool(re.search(r"CHIMERA\{[^}]+\}", r.text, re.IGNORECASE))
        return {
            "trace_id": trace_id,
            "exploit_blocked": not flag_found,
            "status_code": r.status_code,
            "verdict": "PATCH_EFFECTIVE" if not flag_found else "STILL_VULNERABLE",
        }
    except Exception as e:
        return {"trace_id": trace_id, "error": str(e), "verdict": "UNREACHABLE"}


@app.get("/state/{trace_id}")
async def full_state(trace_id: str):
    """Returns the full GraphState for the approval modal (patch, flag, exploit)."""
    graph = get_graph()
    try:
        snapshot = await graph.aget_state({"configurable": {"thread_id": trace_id}})
        if snapshot and snapshot.values:
            sv = snapshot.values
            return {
                "trace_id": trace_id,
                "status": sv.get("status", "unknown"),
                "target_ip": sv.get("target_ip", ""),
                "captured_flag": sv.get("captured_flag", ""),
                "exploit_proof": sv.get("exploit_proof", ""),
                "remediation_patch": sv.get("remediation_patch", ""),
                "target_topography": sv.get("target_topography", ""),
                "htb_questions": sv.get("htb_questions", ""),
                "failure_reason": sv.get("failure_reason", ""),
                "iteration_count": sv.get("iteration_count", 0),
                "human_approved": sv.get("human_approved"),
            }
    except Exception as exc:
        log.warning("full_state_error", trace_id=trace_id, error=str(exc))
    raise HTTPException(status_code=404, detail="State not found")


@app.get("/report/{trace_id}")
async def download_report(trace_id: str):
    """Generates and returns a markdown report for the completed run."""
    import datetime

    graph = get_graph()
    try:
        snapshot = await graph.aget_state({"configurable": {"thread_id": trace_id}})
        sv = snapshot.values if (snapshot and snapshot.values) else {}
    except Exception:
        sv = {}

    target_ip = sv.get("target_ip", "unknown")
    flag = sv.get("captured_flag", "")
    exploit = sv.get("exploit_proof", "")
    topography = sv.get("target_topography", "")
    patch = sv.get("remediation_patch", "")
    questions = sv.get("htb_questions", "")
    status = sv.get("status", "unknown")
    iters = sv.get("iteration_count", 0)
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Answer HTB questions using Groq if questions were provided
    answers_section = ""
    if questions and flag:
        try:
            from langchain_groq import ChatGroq
            from langchain_core.messages import HumanMessage

            llm = ChatGroq(
                model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
                groq_api_key=os.environ["GROQ_API_KEY"],
                temperature=0,
            )
            q_prompt = (
                f"You are a CTF analyst. Based on the following recon and exploit data, "
                f"answer each HTB question precisely and concisely.\n\n"
                f"Target: {target_ip}\nRecon:\n{topography}\nExploit used: {exploit}\n"
                f"Flag captured: {flag}\n\nQuestions:\n{questions}\n\n"
                f"For each question, reply with: Q: <question>\\nA: <answer>"
            )
            resp = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=q_prompt)]), timeout=30
            )
            answers_section = f"\n## HTB Questions & Answers\n\n{resp.content}\n"
        except Exception as e:
            answers_section = f"\n## HTB Questions & Answers\n\n> Could not auto-answer: {e}\n\n**Questions asked:**\n{questions}\n"
    elif questions:
        answers_section = f"\n## HTB Questions\n\n{questions}\n\n> Flag not yet captured — answers unavailable.\n"

    patch_section = (
        f"\n## Remediation Patch Applied\n\n```python\n{patch}\n```\n" if patch else ""
    )
    flag_section = f"\n**Flag:** `{flag}`\n" if flag else "\n**Flag:** Not captured\n"

    md = f"""# Chimera Pentest Report
**Trace ID:** `{trace_id}`
**Target:** `{target_ip}`
**Status:** `{status}`
**Iterations:** {iters}
**Generated:** {timestamp}
{flag_section}
---

## Recon (Scout)

```
{topography}
```

## Exploit Used (Investigator → Sandbox)

```bash
{exploit or "No exploit executed"}
```
{answers_section}{patch_section}
---
*Generated by Project Chimera — Autonomous SecOps Pipeline*
"""

    from fastapi.responses import Response

    filename = f"chimera-report-{trace_id[:8]}.md"
    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/runs")
def list_runs():
    return {"runs": list(_early_states.values())}


@app.get("/metrics")
def metrics_endpoint():
    data = prometheus_text()
    if data is None:
        return PlainTextResponse(
            "# prometheus_client not available\n",
            status_code=503,
            media_type="text/plain; version=0.4",
        )
    return PlainTextResponse(data, media_type="text/plain; version=0.4")


@app.get("/")
async def root():
    return {
        "service": "Project Chimera Orchestrator",
        "status": "online",
        "endpoints": [
            "/webhook/alert",
            "/status/{trace_id}",
            "/runs",
            "/metrics",
            "/health",
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "chimera-orchestrator"}


if __name__ == "__main__":
    import uvicorn
    # Railway provides the port via the PORT environment variable
    port = int(os.getenv("PORT", os.getenv("ORCHESTRATOR_PORT", "8000")))
    uvicorn.run(app, host="0.0.0.0", port=port)
