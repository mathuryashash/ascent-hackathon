"""
Project Chimera — Orchestrator FastAPI App
==========================================
Provides the HTTP API that drives the LangGraph pipeline.
* `/webhook`   – receives SIEM alerts and starts a run.
* `/ws`        – WebSocket endpoint for real-time dashboard updates.
* `/status/{trace_id}` – fetches the latest GraphState snapshot.
* `/metrics`   – Prometheus metrics endpoint.
* `/health`    – liveness probe.
"""

import os
import json
import uuid
import hashlib
import hmac
import structlog
import asyncio
from typing import List, Dict, Any, AsyncGenerator
from fastapi import FastAPI, Request, BackgroundTasks, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import aiosqlite

# Local imports
from graph import get_graph
from metrics import prometheus_text, record_run_start, record_run_end
from tracing import configure_logging

configure_logging()
log = structlog.get_logger(__name__)

app = FastAPI(
    title="Project Chimera Orchestrator",
    description="FastAPI wrapper around the LangGraph autonomous pipeline",
    version="1.0.0",
)

# Allow UI (different origin) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
        for connection in self.active_connections:
            try:
                await connection.send_text(msg_str)
            except Exception as e:
                log.error("ws_broadcast_error", error=str(e))

manager = ConnectionManager()

# ---------------------------------------------------------------------------
# State Serialization Helper
# ---------------------------------------------------------------------------

def serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures LangGraph state is JSON serializable for the UI."""
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

# HMAC secret
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
_early_states: dict[str, dict] = {}
_early_state_times: dict[str, float] = {}
_EARLY_STATE_TTL = 3600  # 1 hour

def _prune_early_states() -> None:
    now = __import__("time").time()
    stale = [k for k, t in _early_state_times.items() if now - t > _EARLY_STATE_TTL]
    for k in stale:
        _early_states.pop(k, None)
        _early_state_times.pop(k, None)

def _valid_hmac(body: bytes, header_val: str) -> bool:
    if not WEBHOOK_SECRET:
        return True
    if not header_val or not header_val.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_val)

# ---------------------------------------------------------------------------
# Background task that runs the full pipeline for a given alert.
# ---------------------------------------------------------------------------
async def _run_pipeline(alert_payload: dict, trace_id: str) -> None:
    """Execute the LangGraph pipeline and broadcast updates."""
    record_run_start(trace_id)
    log.info("pipeline_start", trace_id=trace_id)
    
    # Notify UI that an alert was received
    await manager.broadcast({
        "event": "alert_received",
        "data": {
            "type": alert_payload.get("trigger", {}).get("matched_pattern", "Unknown Alert"),
            "source": alert_payload.get("source", "external"),
            "trace_id": trace_id
        }
    })

    async with aiosqlite.connect("/app/checkpoints.sqlite") as conn:
        checkpointer = AsyncSqliteSaver(conn)
        graph = get_graph(checkpointer=checkpointer)

        init_state = {
            "trace_id": trace_id,
            "alert_payload": alert_payload,
            "status": "queued",
            "messages": [],
            "iteration_count": 0,
            "retry_count": 0,
        }
        
        try:
            async for event in graph.astream(init_state, config={"configurable": {"thread_id": trace_id}}, stream_mode="updates"):
                serialized_event = serialize_state(event)
                await manager.broadcast({
                    "event": "pipeline_step",
                    "data": serialized_event
                })
                await asyncio.sleep(0.5)

            snapshot = await graph.get_state({"configurable": {"thread_id": trace_id}})
            final_state = snapshot.values if snapshot else {}
            status = final_state.get("status", "completed")
            iters = final_state.get("iteration_count", 0)
            flag = bool(final_state.get("captured_flag"))
            
            await manager.broadcast({
                "event": "pipeline_complete",
                "data": {"status": status, "trace_id": trace_id}
            })
            
        except Exception as e:
            log.error("pipeline_error", trace_id=trace_id, error=str(e))
            status = "failed"
            iters = 0
            flag = False
            await manager.broadcast({
                "event": "pipeline_error",
                "error": str(e),
                "trace_id": trace_id
            })
            
        record_run_end(trace_id, status, iters, flag)

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.post("/webhook", status_code=202)
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_signature: str = Header(default=""),
):
    body = await request.body()
    if not _valid_hmac(body, x_signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    trace_id = str(uuid.uuid4())
    _prune_early_states()
    _early_states[trace_id] = {"trace_id": trace_id, "status": "queued"}
    _early_state_times[trace_id] = __import__("time").time()
    background_tasks.add_task(_run_pipeline, payload, trace_id)
    return {"trace_id": trace_id, "status": "queued"}

@app.post("/webhook/alert", status_code=202)
async def webhook_alert(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_signature: str = Header(default=""),
    x_signature: str = Header(default=""),
):
    sig = x_webhook_signature or x_signature
    return await webhook(request, background_tasks, sig)

@app.post("/trigger", status_code=202)
async def trigger_demo(background_tasks: BackgroundTasks):
    import datetime
    payload = {
        "alert_id": str(uuid.uuid4()),
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "severity": "HIGH",
        "source": "ui_trigger",
        "target": {"host": "chimera-victim", "port": 5000, "service": "flask-app"},
        "trigger": {
            "log_line": "GET /search?q=%27+UNION+SELECT+1,value,%27x%27,0+FROM+secrets+WHERE+key=%27flag%27--",
            "matched_pattern": "UNION SELECT",
            "route": "/search"
        }
    }
    trace_id = str(uuid.uuid4())
    _prune_early_states()
    _early_states[trace_id] = {"trace_id": trace_id, "status": "queued"}
    _early_state_times[trace_id] = __import__("time").time()
    background_tasks.add_task(_run_pipeline, payload, trace_id)
    return {"trace_id": trace_id, "status": "queued"}

@app.get("/status/{trace_id}")
async def status(trace_id: str):
    async with aiosqlite.connect("/app/checkpoints.sqlite") as conn:
        checkpointer = AsyncSqliteSaver(conn)
        graph = get_graph(checkpointer=checkpointer)
        try:
            snapshot = await graph.get_state({"configurable": {"thread_id": trace_id}})
            return snapshot.values if snapshot else _early_states.get(trace_id, {"trace_id": trace_id, "status": "not_found"})
        except Exception:
            return _early_states.get(trace_id, {"trace_id": trace_id, "status": "not_found"})

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
    async with aiosqlite.connect("/app/checkpoints.sqlite") as conn:
        checkpointer = AsyncSqliteSaver(conn)
        graph = get_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": trace_id}}
        try:
            async for event in graph.astream(None, config=config, stream_mode="updates"):
                await manager.broadcast({"event": "pipeline_step", "data": serialize_state(event)})
                await asyncio.sleep(0.1)
            snapshot = await graph.get_state(config)
            final_state = snapshot.values if snapshot else {}
            status = final_state.get("status", "completed")
            record_run_end(trace_id, status, final_state.get("iteration_count", 0), bool(final_state.get("captured_flag")))
            await manager.broadcast({"event": "pipeline_complete", "data": {"status": status, "trace_id": trace_id}})
        except Exception as e:
            log.error("resume_error", trace_id=trace_id, error=str(e))
            await manager.broadcast({"event": "pipeline_error", "error": str(e), "trace_id": trace_id})


@app.post("/approve/{trace_id}", status_code=202)
async def approve_patch(trace_id: str, background_tasks: BackgroundTasks):
    """Set human_approved=True and resume the graph past the human_approval interrupt."""
    async with aiosqlite.connect("/app/checkpoints.sqlite") as conn:
        checkpointer = AsyncSqliteSaver(conn)
        graph = get_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": trace_id}}
        snapshot = await graph.get_state(config)
        if not snapshot or not snapshot.next:
            raise HTTPException(status_code=404, detail="No paused pipeline found for this trace_id")
        await graph.aupdate_state(config, {"human_approved": True})
    background_tasks.add_task(_resume_pipeline, trace_id)
    await manager.broadcast({"event": "human_approved", "data": {"trace_id": trace_id}})
    return {"trace_id": trace_id, "status": "resuming"}


@app.post("/reject/{trace_id}", status_code=200)
async def reject_patch(trace_id: str):
    """Set human_approved=False — pipeline ends without applying the patch."""
    async with aiosqlite.connect("/app/checkpoints.sqlite") as conn:
        checkpointer = AsyncSqliteSaver(conn)
        graph = get_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": trace_id}}
        snapshot = await graph.get_state(config)
        if not snapshot or not snapshot.next:
            raise HTTPException(status_code=404, detail="No paused pipeline found for this trace_id")
        await graph.aupdate_state(config, {"human_approved": False, "status": "rejected"})
    await manager.broadcast({"event": "human_rejected", "data": {"trace_id": trace_id}})
    return {"trace_id": trace_id, "status": "rejected"}


@app.get("/traces")
def list_traces():
    return {"traces": list(_early_states.values())}

@app.get("/metrics")
def metrics_endpoint():
    data = prometheus_text()
    if data is None:
        return PlainTextResponse("# prometheus_client not available\n", status_code=503, media_type="text/plain; version=0.4")
    return PlainTextResponse(data, media_type="text/plain; version=0.4")

@app.get("/health")
def health():
    return {"status": "ok", "service": "chimera-orchestrator"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("ORCHESTRATOR_PORT", "8000")))