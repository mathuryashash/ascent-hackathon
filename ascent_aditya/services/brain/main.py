"""
Project Chimera — Orchestrator FastAPI App
==========================================
Placeholder for Member 2's LangGraph implementation.
Member 2 will replace /webhook/alert and /status/{trace_id} with real logic.

Grok LLM initialization (for Member 2):
    from langchain_xai import ChatXAI
    llm = ChatXAI(model="grok-3", api_key=os.environ["XAI_API_KEY"])

Member 3 will add Streamlit dashboard and Omium tracing to this file.
"""

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uuid

app = FastAPI(
    title="Project Chimera Orchestrator",
    description="Autonomous Purple Team Pipeline — Webhook Ingress + Status API",
    version="0.1.0"
)

# Allow all origins during hackathon (Member 3's UI will call this)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory state store (Member 2 will replace with real LangGraph state)
_pipeline_states: dict = {}


@app.get("/health")
def health():
    """Health check — used by Docker and Member 3's UI."""
    return {"status": "ok", "service": "chimera-orchestrator"}


@app.post("/webhook/alert")
async def receive_alert(payload: dict, background_tasks: BackgroundTasks):
    """
    Ingress for SIEM alerts from Member 1's siem_simulator.py.
    Member 2 will replace the body of this function with run_chimera_pipeline().
    """
    alert_id = payload.get("alert_id", str(uuid.uuid4()))
    trace_id = str(uuid.uuid4())

    print(f"[ORCHESTRATOR] 🚨 Alert received: {alert_id} → trace: {trace_id}")
    print(f"[ORCHESTRATOR]    Pattern: {payload.get('trigger', {}).get('matched_pattern')}")

    # Placeholder state — Member 2 replaces this with LangGraph execution
    _pipeline_states[trace_id] = {
        "trace_id": trace_id,
        "alert_id": alert_id,
        "status": "queued",
        "steps": [],
        "payload": payload
    }

    # TODO (Member 2): background_tasks.add_task(run_chimera_pipeline, payload, trace_id)

    return {"status": "queued", "trace_id": trace_id, "alert_id": alert_id}


@app.get("/status/{trace_id}")
def get_status(trace_id: str):
    """
    Polling endpoint for Member 3's UI to track pipeline progress.
    Member 2 will populate real LangGraph state updates here.
    """
    state = _pipeline_states.get(trace_id)
    if not state:
        return {"trace_id": trace_id, "status": "not_found"}
    return state


@app.get("/traces")
def list_traces():
    """Lists all active pipeline traces (for debugging)."""
    return {"traces": list(_pipeline_states.values())}
