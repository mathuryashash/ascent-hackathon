import asyncio
import json
import logging
import os
from typing import Dict, Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Import our AI pipeline
from member_2_ai import run_chimera_pipeline

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chimera.brain")

app = FastAPI(title="Chimera Orchestrator")

# Allow the Gateway UI to connect from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared queue for broadcasting events to all connected UI clients
event_queue = asyncio.Queue()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"UI Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"UI Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending to websocket: {e}")

manager = ConnectionManager()


@app.post("/webhook")
async def handle_webhook(request: Request):
    """
    Receives alerts from the SIEM.
    Triggers the LangGraph AI pipeline as a background task.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # In a real app, verify the HMAC signature here
    # signature = request.headers.get("X-Signature")

    logger.info(f"Received webhook alert: {payload.get('type')}")
    
    # Broadcast the initial alert to the UI
    await manager.broadcast(json.dumps({
        "event": "alert_received",
        "data": payload
    }))

    # Start the LangGraph pipeline in the background so we can return 202 Accepted quickly
    asyncio.create_task(run_pipeline_and_broadcast(payload))

    return {"status": "Accepted", "message": "Pipeline triggered."}


async def run_pipeline_and_broadcast(payload: dict):
    """
    Runs the Member 2 AI pipeline and streams every state update to the WebSocket.
    """
    try:
        # run_chimera_pipeline is an async generator that yields StateGraph updates
        async for state_update in run_chimera_pipeline(payload):
            # A state_update looks like {"scout_node": {"status": "investigating", ...}}
            # We want to broadcast this to the UI
            
            # Convert any LangChain message objects to strings or dicts before JSON serialization
            serialized_update = serialize_state(state_update)
            
            await manager.broadcast(json.dumps({
                "event": "pipeline_step",
                "data": serialized_update
            }))
            
            # Small delay to let the UI breathe and animate
            await asyncio.sleep(0.5)
            
        await manager.broadcast(json.dumps({
            "event": "pipeline_complete"
        }))
        
    except Exception as e:
        logger.error(f"Pipeline crashed: {e}")
        await manager.broadcast(json.dumps({
            "event": "pipeline_error",
            "data": str(e)
        }))

def serialize_state(state_update: dict) -> dict:
    """Helper to ensure the state dict is JSON serializable."""
    result = {}
    for node_name, state_data in state_update.items():
        result[node_name] = {}
        for key, value in state_data.items():
            if key == "messages":
                # Extract content from Langchain message objects
                result[node_name][key] = []
                for msg in value:
                    if hasattr(msg, "content"):
                        # If it's a ToolMessage, maybe include the tool name
                        if hasattr(msg, "tool_call_id") and getattr(msg, "name", None):
                            result[node_name][key].append(f"[Tool: {msg.name}] {msg.content}")
                        elif hasattr(msg, "tool_calls") and msg.tool_calls:
                            result[node_name][key].append(f"[Calling Tools] {json.dumps(msg.tool_calls)}")
                        else:
                            result[node_name][key].append(msg.content)
                    else:
                        result[node_name][key].append(str(msg))
            else:
                result[node_name][key] = value
    return result


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for the Gateway UI.
    """
    await manager.connect(websocket)
    try:
        while True:
            # We just keep the connection open, waiting for client messages if any
            data = await websocket.receive_text()
            logger.info(f"UI sent: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/health")
def health():
    return {"status": "ok", "service": "orchestrator"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.brain.main:app", host="0.0.0.0", port=8000, reload=True)
