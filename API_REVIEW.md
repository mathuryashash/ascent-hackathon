# Project Chimera — API Design Review

**Reviewer:** Claude (claude-sonnet-4-6)  
**Date:** 2026-05-15  
**Scope:** REST API, SSE, WebSocket, inter-service contracts across all five services.

---

## Table of Contents
1. [DESIGN ISSUES](#1-design-issues)
2. [CONSISTENCY ISSUES](#2-consistency-issues)
3. [MISSING FEATURES](#3-missing-features)
4. [GOOD PATTERNS](#4-good-patterns)

---

## 1. DESIGN ISSUES

### 1.1 Duplicate webhook endpoints with divergent header contracts
**Files:** `services/brain/main.py` lines 196–224

Two endpoints accept the exact same payload and do the exact same work:
- `POST /webhook` — expects header `X-Signature`
- `POST /webhook/alert` — expects `X-Webhook-Signature` (with fallback to `X-Signature`)

`/webhook/alert` is a wrapper that calls through to `/webhook` after normalising the header. This creates two public surfaces for the same operation, and the header name inconsistency requires the fallback union logic (`sig = x_webhook_signature or x_signature`). Clients (the two SIEM implementations) already disagree on which header to send:

- `services/victim_sandbox/siem/monitor.py` line 69 — sends `X-Signature`
- `siem_simulator.py` line 104 — sends `X-Webhook-Signature`

**Suggestion:** Collapse to a single `POST /webhook/alert` endpoint. Standardise on `X-Webhook-Signature`. Deprecate and remove `/webhook`.

---

### 1.2 HTTP method mismatch on approve/reject
**Files:** `services/brain/main.py` lines 288 and 304

- `POST /approve/{trace_id}` returns `202 Accepted` (correct — async work is queued)
- `POST /reject/{trace_id}` returns `200 OK`

A rejection also causes a state transition and triggers a broadcast, so the status code asymmetry is arbitrary. Both should be `202` since neither operation is synchronously complete, or both should be `200` if the state is written synchronously before responding.

**Suggestion:** Unify to `202` for both, or use `PATCH /runs/{trace_id}/decision` with a body `{"decision": "approve" | "reject"}` to avoid two separate endpoints for the same concept.

---

### 1.3 `POST /trigger` exists on both gateway and orchestrator without a contract
**Files:**
- `services/gateway_ui/src/server.js` lines 155–203 — `POST /trigger`
- `services/brain/main.py` lines 226–246 — `POST /trigger`

The gateway's `/trigger` builds a minimal alert (`type`, `target`, `evidence`, `source`) and forwards it to the orchestrator's `POST /webhook/alert`. The orchestrator also exposes its own `POST /trigger` that constructs a richer payload (with `alert_id`, `severity`, `target` object, `trigger` object). These are completely independent code paths that produce structurally different payloads for the same conceptual action. If the gateway is bypassed and the orchestrator's `/trigger` is called directly, the pipeline receives a different alert shape.

**Suggestion:** The orchestrator's `/trigger` should be the canonical demo trigger. The gateway should proxy to it, not construct its own payload.

---

### 1.4 `/status/{trace_id}` returns the raw `GraphState` object
**File:** `services/brain/main.py` lines 248–257

The `/status` endpoint returns the entire `GraphState` dict from LangGraph's sqlite checkpointer, or falls back to `_early_states` (which contains only `trace_id` and `status`). These are two entirely different shapes:

- Early state: `{"trace_id": "…", "status": "queued"}`
- Post-start state: the full `GraphState` TypedDict with 15 fields including `messages`, `remediation_patch`, `original_source`, `exploit_proof`, `captured_flag`, etc.

The gateway's SSE handler (`server.js` line 126) reads `data.status` from the response, which works for the early-state shape but may fail if the full GraphState's `status` key is missing or nested differently during a node transition.

**Suggestion:** Introduce a dedicated `StatusResponse` Pydantic model. Always return the same shape: `{trace_id, status, iteration_count, current_node, has_flag, human_approval_pending}`. Keep sensitive fields (`exploit_proof`, `captured_flag`, `remediation_patch`) behind a separate `GET /runs/{trace_id}/detail` endpoint.

---

### 1.5 CORS is fully open on the orchestrator
**File:** `services/brain/main.py` lines 41–46

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

The orchestrator (`chimera-orchestrator`) is on `chimera-internal` for service-to-service traffic and `chimera-external` for LLM API egress, but its port 8000 is also mapped to the host (`docker-compose.yml` line 52: `"8000:8000"`). A wildcard CORS policy means any web origin can call the webhook, approve, reject, and trigger endpoints from a browser — which bypasses the HMAC signature check entirely if the browser holds a valid session.

**Suggestion:** Restrict `allow_origins` to the gateway's origin (`http://localhost:3001` in dev, configurable via env var). Remove the host port mapping for the orchestrator if it is intended to be internal-only; expose it only through the gateway.

---

### 1.6 In-memory run registry is not persisted and diverges from orchestrator state
**File:** `services/gateway_ui/src/server.js` lines 22–23, 190–195, 206–211

The gateway maintains its own `runRegistry` Map (limited to the last 20, never flushed to disk). This registry is the only source for `GET /runs`. The orchestrator has `_early_states` and the SQLite checkpointer, neither of which the gateway queries for `GET /runs`. After a gateway restart, all run history is lost and `GET /runs` returns an empty list even though the orchestrator's sqlite database still has all checkpoints.

**Suggestion:** Back `GET /runs` by a proxy call to the orchestrator's `GET /traces` endpoint. Remove the gateway's in-memory registry or keep it only as a short-lived cache with a TTL.

---

### 1.7 WebSocket endpoint discards all inbound messages
**File:** `services/brain/main.py` lines 259–266

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # message thrown away
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

The WebSocket is receive-and-discard. Clients have no mechanism to subscribe to a specific `trace_id`, send a ping, or request a replay of missed events. All connected clients receive every broadcast regardless of which run they are viewing.

**Suggestion:** Parse inbound messages as `{"action": "subscribe", "trace_id": "…"}`. Filter broadcasts so each connection only receives events for its subscribed traces. This is critical when multiple browser tabs are open or multiple operators are monitoring different runs.

---

### 1.8 `_early_states` is an unbounded in-process dict with a TTL-on-access model
**File:** `services/brain/main.py` lines 109–118

`_early_states` is pruned only when a new webhook arrives (`_prune_early_states()` is called inside `/webhook` and `/trigger`). If no new alerts come in for hours, stale entries accumulate. More importantly, once the pipeline advances past `ingress`, the state lives in SQLite — but `/status` still falls back to `_early_states` if the SQLite lookup raises an exception (line 256). This means a crashed sqlite lookup silently returns stale cached data without any indication of degraded operation.

**Suggestion:** Log a warning and return `{"trace_id": "…", "status": "unknown", "error": "state_store_unavailable"}` when the sqlite lookup fails rather than silently returning potentially stale early-state data.

---

## 2. CONSISTENCY ISSUES

### 2.1 Inconsistent alert payload schema between the two SIEM implementations
**Files:**
- `services/victim_sandbox/siem/monitor.py` lines 56–63 — `fire_webhook()`
- `siem_simulator.py` lines 67–91 — `build_payload()`

The Docker-SDK-based SIEM (`monitor.py`) sends:
```json
{"type": "sqli", "target": "victim-service", "timestamp": "…", "evidence": "…"}
```

The file-tail SIEM (`siem_simulator.py`) sends:
```json
{"alert_id": "…", "timestamp": "…", "severity": "HIGH", "source": "siem_simulator",
 "target": {"host": "…", "port": 5000, "service": "…"},
 "trigger": {"log_line": "…", "matched_pattern": "…", "route": "…"},
 "metadata": {"victim_log_path": "…"}}
```

The orchestrator treats `alert_payload` as an untyped `dict` and accesses fields with `.get()` in `_run_pipeline()` (line 140: `alert_payload.get("trigger", {}).get("matched_pattern", "Unknown Alert")`). The monitor.py payload has no `trigger` key, so the broadcast description will always be `"Unknown Alert"` when triggered by the Docker-SDK SIEM.

The `docker-compose.yml` deploys only `siem_simulator.py` (line 111), but `monitor.py` still exists as an alternative. This creates a hidden dead-code / drift risk.

**Suggestion:** Define a single `AlertPayload` Pydantic model in `schemas.py` and validate all inbound webhook payloads against it. Remove or clearly mark `monitor.py` as deprecated.

---

### 2.2 Error response shapes are inconsistent across services

| Service | Error shape example |
|---------|---------------------|
| `brain/main.py` (FastAPI) | `{"detail": "Invalid webhook signature"}` (FastAPI default) |
| `gateway_ui/server.js` | `{"error": "Orchestrator unreachable", "detail": err.message}` |
| `gateway_ui/server.js` (approve/reject on 502) | `{"error": err.message}` — no `detail` key |
| `victim_sandbox/app.py` search 500 | `{"status": "error", "query": "…", "error": "…", "sqlite3.OperationalError": true}` |
| `victim_sandbox/app.py` search 500 (generic) | `{"status": "error", "message": "…"}` — different key (`message` vs `error`) |

The gateway uses `error` + optional `detail`. FastAPI uses `detail`. The victim uses `status` + `error` or `status` + `message`. No service uses a shared envelope.

**Suggestion:** Adopt a single error envelope across all services:
```json
{"error": {"code": "INVALID_SIGNATURE", "message": "Human-readable text"}}
```
Add a FastAPI exception handler in `main.py` to wrap HTTPException into this shape.

---

### 2.3 `status` field values are not documented or validated as an enum
**Files:** `services/brain/schemas.py` line 99, `services/brain/graph.py` nodes

The `GraphState.status` field comment lists: `scouting | investigating | patching | resolved | failed`. But the actual values used across nodes are:

- `"queued"` — set in `main.py` lines 211, 243
- `"scouting"` — `ingress_node` line 116
- `"summarizing"` — `scout_node` line 143
- `"investigating"` — `summarizer_node` line 163
- `"sandbox_running"` — `investigator_node` line 194
- `"evaluating"` — `sandbox_node` line 214
- `"patching"` — `evaluator_node` line 226
- `"awaiting_approval"` — `architect_node` line 257
- `"rollback"` — `verifier_node` line 291
- `"rejected"` — `reject_patch` endpoint line 314
- `"starting"` — gateway `runRegistry` line 194 (not an orchestrator value)
- `"not_found"` — `status()` endpoint line 256

The comment in `schemas.py` is wrong and incomplete. The gateway SSE handler uses `TERMINAL_STATUSES = new Set(['resolved', 'failed'])` (`server.js` line 113), missing `"rejected"` — so a rejected run will loop the SSE poll indefinitely until the 2-second interval times out from the client closing the connection.

**Suggestion:** Add a `StatusEnum` to `schemas.py`. Use it in `GraphState`. Export the terminal set in a shared constant and reference it from both the orchestrator's broadcast logic and the gateway's SSE terminal check.

---

### 2.4 WebSocket broadcast message schema is ad hoc
**File:** `services/brain/main.py` lines 137–188

Four different broadcast event types are emitted with no shared envelope:

```python
# alert_received
{"event": "alert_received", "data": {"type": …, "source": …, "trace_id": …}}

# pipeline_step
{"event": "pipeline_step", "data": <serialized_graph_state_fragment>}

# pipeline_complete
{"event": "pipeline_complete", "data": {"status": …, "trace_id": …}}

# pipeline_error
{"event": "pipeline_error", "error": …, "trace_id": …}  # error is top-level, not in data!

# human_approved / human_rejected
{"event": "human_approved", "data": {"trace_id": …}}
```

`pipeline_error` puts `error` and `trace_id` at the top level, while every other event wraps its payload under `"data"`. A frontend switch on `event` would need special-casing for the error branch.

**Suggestion:** Enforce a uniform envelope: `{"event": "…", "trace_id": "…", "data": {…}}`. The `trace_id` should always be at the top level (not buried in `data`) to allow client-side filtering.

---

### 2.5 SSE endpoint is not under `/api/` prefix
**File:** `services/gateway_ui/src/server.js` lines 104 and 206

`GET /events/:traceId` and `GET /runs` are not prefixed under `/api/`. All other backend routes use `/api/*` (`/api/status/:traceId`, `/api/metrics`, `/api/health`, `/api/approve/:traceId`, `/api/reject/:traceId`). This inconsistency complicates reverse-proxy rules and API documentation.

**Suggestion:** Move to `GET /api/events/:traceId` and `GET /api/runs`.

---

### 2.6 `POST /trigger` on the gateway does not use the `/api/` prefix
**File:** `services/gateway_ui/src/server.js` line 155

`POST /trigger` is at the root, unlike all other non-static endpoints which are under `/api/`. Same issue as 2.5.

**Suggestion:** Move to `POST /api/trigger`.

---

### 2.7 HTTP status codes on victim app are inconsistent with intent
**File:** `services/victim_sandbox/app.py` lines 137–149

The `/health` endpoint returns HTTP 200 even when `db_ok` is `False` (`status: "degraded"`). Kubernetes and Docker health checks (`docker-compose.yml` line 19) use the HTTP status code to determine container health; returning 200 for a degraded state means Docker will never restart a victim container with a broken DB.

**Suggestion:** Return `503 Service Unavailable` when `db_ok is False`.

---

## 3. MISSING FEATURES

### 3.1 No endpoint to list all runs from the orchestrator with pagination
**File:** `services/brain/main.py` line 319

`GET /traces` returns only `_early_states` — runs that have already advanced to the SQLite checkpoint are absent. There is no way to query completed or failed runs from the API. The gateway's `GET /runs` is similarly limited to the in-memory registry of the last 20 triggered runs.

**Suggestion:** Add `GET /runs?status=&limit=&offset=` that queries the SQLite checkpoints database. Returns `{items: [{trace_id, status, started_at, completed_at}], total, limit, offset}`.

---

### 3.2 No webhook ingestion acknowledgement or idempotency key
**File:** `services/brain/main.py` lines 196–214

The webhook endpoint returns a `trace_id` for every call with no deduplication. If the SIEM fires a duplicate alert (the debounce window in `siem_simulator.py` is only 1 second), two independent pipeline runs are created for the same attack event. There is no `alert_id` validation or idempotency key.

**Suggestion:** Accept an `alert_id` field in the payload. If an existing run with that `alert_id` already exists, return the existing `trace_id` with `status: "already_running"` rather than spawning a duplicate pipeline.

---

### 3.3 No endpoint to cancel a running pipeline
**Files:** `services/brain/main.py`, `services/gateway_ui/src/server.js`

Once a pipeline is started, there is no way to cancel it short of restarting the orchestrator container. For a CTF training platform, a trainer needs to be able to abort a runaway pipeline that has hit the 10-iteration guard and is about to fail.

**Suggestion:** Add `POST /runs/{trace_id}/cancel`. Set `status: "cancelled"` in the checkpoint, broadcast a `pipeline_cancelled` WS event, and short-circuit the next node transition check.

---

### 3.4 No replay or history endpoint for WebSocket events
**File:** `services/brain/main.py` lines 259–266

A client that connects to `/ws` after a pipeline has already started sees no history. The SSE `/events/:traceId` polls the current snapshot but does not replay node-by-node steps that already occurred. This makes the dashboard useless for any run that was already in-progress when the operator opened their browser.

**Suggestion:** Store per-trace event history in Redis or in the SQLite checkpoint. Add `GET /runs/{trace_id}/events` returning the full ordered event log for that trace.

---

### 3.5 No authentication on any endpoint
**Files:** All services

The only authentication mechanism in the system is the HMAC webhook signature, which protects only the webhook ingress from external SIEM → orchestrator. Every other endpoint is fully unauthenticated:

- `POST /approve/{trace_id}` — anyone who can reach port 8000 can approve a patch
- `POST /reject/{trace_id}` — same
- `POST /trigger` — anyone can spawn a pipeline
- `GET /status/{trace_id}` — leaks `exploit_proof`, `captured_flag`, `remediation_patch`

The orchestrator's port 8000 is host-mapped (`docker-compose.yml` line 52), making these endpoints reachable from the host without going through the gateway.

**Suggestion:** At minimum, add a static `Authorization: Bearer <ADMIN_TOKEN>` check on mutating endpoints (`/approve`, `/reject`, `/trigger`). The gateway should forward the operator's session token. For the hackathon context, even a simple shared secret env var is better than nothing.

---

### 3.6 No endpoint to retrieve the remediation patch before approval
**File:** `services/brain/main.py`

When the pipeline reaches `awaiting_approval`, the operator must approve or reject blind — there is no `GET /runs/{trace_id}/patch` endpoint that returns the `remediation_patch` and `original_source` for diff review. The full state is technically accessible via `GET /status/{trace_id}` but that conflates the approval-review surface with the general status surface.

**Suggestion:** Add `GET /runs/{trace_id}/patch` returning `{filename, original_source, patched_content, explanation, safe_to_apply}`. This maps directly to the `ArchitectOutput` schema already defined in `schemas.py`.

---

### 3.7 No API versioning
**Files:** All services

None of the services use URL-based (`/v1/`) or header-based (`API-Version: 1`) versioning. For a platform intended to be extended (new vulnerability types, new agent nodes), breaking changes to the API contract will require coordinated deployment of all services simultaneously.

**Suggestion:** Prefix all orchestrator API routes with `/v1/`. Add an `API-Version` response header. The FastAPI `app` constructor already sets `version="1.0.0"` (`main.py` line 38) — use this to generate versioned docs and routes.

---

### 3.8 No schema validation on webhook ingress payload
**File:** `services/brain/main.py` lines 196–214

The webhook handler calls `json.loads(body)` and passes the raw dict directly to `_run_pipeline()` without any Pydantic validation. Any payload shape is accepted. Fields the pipeline depends on (`trigger.matched_pattern`, `source`, `severity`) are accessed with `.get()` defaults throughout the graph, meaning a malformed payload silently runs the entire pipeline with empty/default values.

**Suggestion:** Validate the incoming body against an `AlertPayload` Pydantic model (see also issue 2.1). Return `422 Unprocessable Entity` on validation failure with field-level error details.

---

## 4. GOOD PATTERNS

### 4.1 HMAC webhook signing is well-implemented
**Files:** `services/brain/main.py` lines 120–126, `siem_simulator.py` lines 101–103

The HMAC validation uses `hmac.compare_digest` (constant-time comparison) correctly, preventing timing attacks. The `sha256=` prefix convention follows the GitHub webhook standard. The SIEM refuses to start if `WEBHOOK_SECRET` is the default `"changeme"` (`siem/monitor.py` lines 30–35) — a good fail-safe.

---

### 4.2 Pydantic schemas for all LLM outputs enforce structured contracts
**File:** `services/brain/schemas.py`

Every agent node (`ScoutOutput`, `InvestigatorOutput`, `ArchitectOutput`, `VerifierOutput`) has a Pydantic model with field-level descriptions and constraints (`ge=0.0, le=1.0` on `confidence_score`). The `GraphState` TypedDict documents every field inline. This is the right pattern for multi-agent systems.

---

### 4.3 Structured logging throughout the orchestrator
**File:** `services/brain/main.py` (structlog), `services/gateway_ui/src/server.js` lines 42–44

The orchestrator uses `structlog` with consistent key-value pairs (`trace_id`, `error`). The gateway emits JSON-structured log lines. This makes logs parseable by any log aggregation tool without regex.

---

### 4.4 Background task pattern for long-running pipelines
**File:** `services/brain/main.py` lines 213, 299

Using FastAPI's `BackgroundTasks` to run the LangGraph pipeline means the HTTP response (202 Accepted + `trace_id`) is returned immediately without holding the HTTP connection open for potentially minutes. The client polls or subscribes via SSE/WebSocket. This is the correct pattern for async AI workloads.

---

### 4.5 Path traversal protection in file-writing tools
**File:** `services/brain/tools/security_tools.py` lines 165–169, 199–203

Both `apply_patch_to_victim` and `get_victim_source` validate that the resolved file path starts with the base directory before performing any I/O. This prevents the AI agent from accidentally (or adversarially) writing outside the victim source tree.

---

### 4.6 Network segmentation enforces the security boundary
**File:** `docker-compose.yml` lines 117–126

The `chimera-internal` network is marked `internal: true`, blocking all internet egress from the sandbox container. The orchestrator is on both networks (internal for victim/sandbox access, external for LLM APIs). This is a well-designed two-network topology for a security training environment.

---

### 4.7 Prometheus metrics endpoint is clearly separated from the API
**File:** `services/brain/main.py` lines 323–328

`GET /metrics` returns `text/plain` with `version=0.4` media type (the Prometheus wire format). It is separated from the JSON API surface and the gateway correctly passes the content-type through (`server.js` line 67: `res.type('text/plain')`). The endpoint degrades gracefully (`503`) when `prometheus_client` is unavailable rather than crashing.

---

### 4.8 SSE terminal-state detection avoids unbounded polling
**File:** `services/gateway_ui/src/server.js` lines 113, 129

The SSE endpoint uses a `TERMINAL_STATUSES` set to detect when polling should stop and closes the stream cleanly (`res.end()`). The 500ms final flush delay before `res.end()` avoids race conditions where the last event might not be flushed to the client. (Note: `"rejected"` should be added to this set — see issue 2.3.)

---

*End of API Review*
