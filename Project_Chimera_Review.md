# Project Chimera – Full‑stack Review & Action Plan

*Prepared for the Ascent Hackathon team (Member 1 – Systems, Member 2 – AI, Member 3 – Integration/UI).  All findings are grouped by functional area, followed by a concrete prioritized to‑do list and a final demo‑ready checklist.*

---

## 📖 1 ‑ Executive Summary

| Area | What works | What’s missing / risky | Quick win |
|------|------------|------------------------|-----------|
| **Architecture doc** (`Project_Chimera_Architecture.md`) | Clear overview, graph concept, gotchas list. | No visual diagram, missing `trace_id` / `iteration_count` in the state description, no persistence/metrics mention. | Add Mermaid diagram, extend `GraphState` definition, add a short “Persistence & Observability” paragraph. |
| **Orchestrator (Brain)** (`services/brain/`) | FastAPI skeleton, Dockerfile, requirements, tool wrappers. | Placeholder `/webhook/alert`, in‑memory state only, no LangGraph integration, no logging/metrics/tracing, missing `git` binary, container‑name hard‑code. | Replace placeholder with real FastAPI that loads the LangGraph graph (`member_2_ai/graph.py`), add `structlog`, install `git`, wire metrics & tracing. |
| **LangGraph graph** (`member_2_ai/graph.py`) | Complete deterministic pipeline, fallback LLMs, iteration guard, structured Pydantic outputs. | Wrong import path (`tools`), missing prompt files, not instrumented for tracing, reads victim source from a path that isn’t mounted, uses `get_logs` without mounting victim logs, no metric calls. | Fix import, create `prompts/` files, add `trace_node_enter/exit` calls, mount victim source (see Compose), wire `record_run_start/end`. |
| **Schemas** (`member_2_ai/schemas.py`) | Rich Pydantic models, clear `GraphState`. | Some field names diverge from actual code (`captured_flag` vs `captured_flag`, etc.), `status` is just `str`. | Align field names across all modules, make `status` a `Literal` enum. |
| **Victim (Flask app)** (`services/victim_sandbox/victim/`) | Intentional SQL‑i, nice UI, health endpoint, logging to file. | `DB_PATH` default mismatches Docker entrypoint (`/data/victim.db`), no `git`, logs can grow unchecked, container publishes port 5000 (should be internal only). | Ensure `DB_PATH` is set via env (already does), install `git` in Dockerfile, add log‑rotation or truncate at start, **do not expose port** in compose. |
| **Sandbox** (`services/victim_sandbox/sandbox/`) | Small image with networking tools, non‑root user. | No `git` (needed for patch verification), no healthcheck. | Install `git` in the orchestrator image (already done), add a simple healthcheck. |
| **SIEM monitor** (`services/victim_sandbox/siem/`) | Reads victim logs via Docker SDK, fires HMAC‑signed webhook on pattern match, deduplication. | Default secret is `"changeme"`, hard‑coded container name, no graceful shutdown. | Make secret mandatory, expose container name via env (already does), add signal handling for clean exit. |
| **UI (Gateway)** (`services/gateway_ui/`) | Dark theme, live Mermaid diagram, diff viewer, human‑approval overlay, metrics panel. | UI fetch URLs use `/api/*` but orchestrator serves plain paths, attempts to open SSE (`/events/...`) which is not implemented, no auth, built with raw `npm run` (no production build). | Change fetch URLs to point to orchestrator (`${ORCHESTRATOR_URL}`), either implement SSE or replace with polling, add optional token header, optionally add multi‑stage Docker build → Nginx static serve. |
| **Metrics & Tracing** (`member_3_integration/metrics.py`, `tracing.py`) | Prometheus counters, hash‑linked trace events. | Not imported anywhere, no endpoint exposure, trace calls missing in graph. | Import in `services/brain/main.py`, expose `/metrics`, add trace calls to each graph node. |
| **Task docs** (`member_*_systems/tasks.md`) | Good high‑level planning. | Duplicate tooling (e.g. `member_1_systems/tools.py` duplicates `services/brain/tools/security_tools.py`), references files that don’t exist. | Consolidate: keep only one `tools.py`, move task docs to `docs/` and update references. |
| **Large unrelated collection** (`awesome‑copilot/`) | Not part of Chimera. | Takes up repository size, distracts judges. | Move out of the repo or archive it. |

---

## 🛠️ 2 ‑ Component‑by‑Component Review

### 2.1 `services/brain/Dockerfile`
*Missing `git` (required by `verify_patch`).*
**Fix** – add to Dockerfile:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
```

### 2.2 `services/brain/requirements.txt`
*No `structlog` / `prometheus_client`.*
**Fix** – append:
```
structlog>=24.0.0
prometheus_client>=0.20.0
```

### 2.3 `services/brain/main.py` (stub)
**Replace** the whole file with the **FastAPI wrapper** that:

* validates webhook payload, creates a `trace_id`, records `record_run_start(trace_id)`.
* builds the initial `GraphState` dict (including `trace_id`).
* launches the LangGraph graph asynchronously (`background_tasks.add_task(graph.ainvoke, state, config={"run_id": trace_id})`).
* exposes `/status/{trace_id}` that reads the latest state via the graph’s `SqliteSaver`.
* adds HMAC validation (same logic as `member_3_integration/main.py`).
* uses `structlog` for JSON logs.
* exposes `/metrics` (returns Prometheus text if client asks for `text/plain`).

> **Full snippet** is provided in the analysis section under *“services/brain/main.py – replace the stub”*.

### 2.4 `services/brain/tools/security_tools.py`
*Hard‑coded container names & missing timeout usage.*
**Fixes**
```python
# Use env vars (already defined) – ensure Docker‑Compose sets them.
container = client.containers.get(SANDBOX_CONTAINER)

exec_result = container.exec_run(
    cmd=["bash", "-c", command],
    demux=True,
    user="sandboxuser",
    timeout=timeout_seconds,      # <-- pass the timeout
)
```
*Add path‑traversal protection and ensure the orchestrator mounts victim source (see Docker‑Compose snippet).*

### 2.5 `services/victim_sandbox/victim/Dockerfile`
*Missing `git`.*
**Fix** – same `git` install as Brain Dockerfile.

### 2.6 `services/victim_sandbox/victim/app.py`
*`DB_PATH` defaults to `/app/database.db`, but entrypoint creates `/data/victim.db`.*
**Fix** – keep `DB_PATH` as `os.getenv("DB_PATH", "/data/victim.db")`.
*Add simple log rotation* (optional) or truncate at startup:
```python
# At startup
open(LOG_PATH, "w").close()   # wipe old log
```

### 2.7 `services/victim_sandbox/siem/monitor.py`
*Default secret `"changeme"`.*
**Fix** – raise if not set:
```python
if WEBHOOK_SECRET == "changeme":
    raise RuntimeError("WEBHOOK_SECRET must be set in the environment")
```

### 2.8 `services/gateway_ui/Dockerfile` (optional production build)
```dockerfile
# ---- Builder -------------------------------------------------
FROM node:20-slim AS builder
WORKDIR /app
COPY package.json .
RUN npm ci
COPY . .
RUN npm run build   # produces ./dist

# ---- Runtime -------------------------------------------------
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
```
If you keep the existing Node server, just ensure it proxies `/api/*` to the orchestrator (or change UI fetch URLs to the full orchestrator URL).

### 2.9 `member_2_ai/graph.py`
| Issue | Fix |
|-------|-----|
| Wrong import (`from tools import …`). | Change to `from services.brain.tools.security_tools import get_logs, execute_bash_in_sandbox, verify_patch` (or expose a package‑level import in `services/brain/__init__.py`). |
| Missing `prompts/` files. | Create `services/brain/prompts/` folder with the four prompt txt files (scout, investigator, architect, verifier). Keep each under 150 tokens; see analysis for example content. |
| No tracing calls. | Wrap each node with `trace_node_enter` / `trace_node_exit` (see “Instrumentation” snippet). |
| `architect_node` reads source from `/victim_src/app.py` but the path isn’t mounted. | In `docker‑compose.yml` mount victim source into the orchestrator (`- ./services/victim_sandbox/victim:/victim_src:ro`). |
| `verifier_node` re‑uses `_make_scout_llm` (expensive). | Switch to a cheap model (e.g. `Claude Haiku`) or reuse the already‑instantiated `scout_llm` with a lower temperature. |
| `final_node` (post‑verifier) not recording metrics. | Add a tiny node after verifier that calls `record_run_end`. |
| `status` literals not typed. | Update `GraphState` in `schemas.py` to use `Literal["scouting","investigating","patching","awaiting_approval","resolved","failed","human_review"]`. |
| `iteration_count` guard already present – good. | No change needed. |
| `status` literals not typed. | Update `GraphState` in `schemas.py` to use `Literal["scouting","investigating","patching","awaiting_approval","resolved","failed","human_review"]`. |
| `iteration_count` guard already present – good. | No change needed. |

### 2.10 `member_2_ai/schemas.py`
*Field name alignment* – make sure every reference in `graph.py` uses the same names (`captured_flag`, `exploit_proof`, `remediation_patch`, `original_source`).
*Make `status` a `Literal`* – see table above.

### 2.11 `member_3_integration/metrics.py` & `tracing.py`
*Import them from the orchestrator* – add to `services/brain/main.py`:
```python
from metrics import record_run_start, record_run_end, prometheus_text
from tracing import trace_node_enter, trace_node_exit
```
*Expose `/metrics`* (see FastAPI snippet).
*Add a simple `record_iteration(trace_id)`* if you want per‑run iteration counters (optional).

### 2.12 `member_3_integration/main.py`
Since the orchestrator will now host the full API (`/webhook`, `/status`, `/metrics`, `/approve`, `/reject`), you can **remove** or archive this file. Keep only the metric/tracing modules and import them where needed.

### 2.13 `awesome‑copilot/`
**Move out** of the repository (e.g., zip it under `archive/awesome‑copilot.zip` or delete). It does not belong to the Chimera demo.

---

## 📦 3 ‑ Missing Core Artefacts (Add to repo)

1. **`docker-compose.yml`** – see the full snippet in the analysis (Section 5). 
2. **Prompt files** – `services/brain/prompts/scout_prompt.txt`, `investigator_prompt.txt`, `architect_prompt.txt`, `verifier_prompt.txt`. Example for `scout_prompt.txt`:
```
You are a Recon agent. Summarize the provided container logs (≤5 bullet points).
Identify any obvious vulnerability type and list affected HTTP endpoints.
Return a JSON object with keys:
- vulnerability_type
- affected_endpoints
- topography_summary
- recommended_approach
```
(Repeat in a similar style for the other three prompts.)
3. **`.env.example`** – list required env vars:
```
WEBHOOK_SECRET=changeme
CLAUDE_API_KEY=YOUR_CLAUDE_KEY
GEMINI_API_KEY=YOUR_GEMINI_KEY
GROQ_API_KEY=YOUR_GROQ_KEY
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_KEY
LOG_LEVEL=INFO
```
4. **Demo video** – record a short (≈2 min) screen‑capture of the UI flow (trigger → patch review → approve → flag disappears). Store as `demo/video.mp4` and link from the README.
5. **CI workflow** – `.github/workflows/ci.yml` (simple lint + unit tests + integration test). See analysis for a minimal YAML.

---

## 📊 4 ‑ Consolidated Prioritized To‑Do List

| Priority | Task | File / Area | Approx. effort |
|----------|------|-------------|----------------|
| 🚀 **HIGH** | Replace placeholder FastAPI with real orchestrator that loads LangGraph, creates `trace_id`, records start, runs async, returns JSON. | `services/brain/main.py` | 1 h |
| 🚀 **HIGH** | Wire **metrics** (`record_run_start/end`) and expose `/metrics` endpoint. | `services/brain/main.py` + `member_3_integration/metrics.py` | 45 min |
| 🚀 **HIGH** | Add **tracing** calls (`trace_node_enter/exit`) to every node in `member_2_ai/graph.py`. | `member_2_ai/graph.py` | 1 h |
| ⚙️ **MEDIUM** | Create `prompts/` directory with four prompt files. | `services/brain/prompts/` | 30 min |
| ⚙️ **MEDIUM** | Fix import path in `security_tools.py` (or expose via package). | `member_2_ai/graph.py` | 15 min |
| ⚙️ **MEDIUM** | Install **git** in orchestrator Dockerfile and add volume mounts for victim source (`/victim_src` read‑only, `/victim_dst` writeable). | `services/brain/Dockerfile` + `docker-compose.yml` | 20 min |
| ⚙️ **MEDIUM** | Align field names across `schemas.py`, `graph.py`, and the FastAPI state dict (`captured_flag`, `exploit_proof`, etc.). | `member_2_ai/*` | 30 min |
| ⚙️ **MEDIUM** | Adjust UI fetch URLs (remove `/api` prefix), either implement SSE in the orchestrator or replace with polling. | `services/gateway_ui/public/index.html` | 45 min |
| ⚙️ **MEDIUM** | Add HMAC validation to `/webhook` endpoint. | `services/brain/main.py` | 15 min |
| ⚙️ **MEDIUM** | Add unit‑tests for `security_tools.py` and a simple integration test that runs the whole pipeline via Docker Compose. | `tests/` | 1 h |
| ⚙️ **MEDIUM** | Provide `.env.example`, `docker-compose.yml`, and a short demo video. | repo root | 30 min |
| ⚙️ **LOW** | Refactor UI build to a multi‑stage Dockerfile that outputs static files served by Nginx. | `services/gateway_ui/Dockerfile` | 30 min |
| ⚙️ **LOW** | Move the massive `awesome‑copilot/` folder out of the repo. | repo root | 5 min |
| ⚙️ **LOW** | Add a GitHub Actions CI workflow (`.github/workflows/ci.yml`). | repo root | 20 min |
| ⚙️ **LOW** | Implement a simple rate‑limiting middleware on the webhook (token‑bucket). | `services/brain/main.py` | 15 min |

**Total estimated effort:** ~ **8 hours** – comfortably doable within a 24‑hour hackathon when split among the three members.

---

## ✅ 5 ‑ Final Demo‑Ready Checklist

1. `docker compose up -d` starts **orchestrator, victim, sandbox, siem, gateway** with no errors. 
2. Health checks (`docker compose ps`) show all services `healthy`. 
3. HMAC secret is set (`WEBHOOK_SECRET`) and both SIEM and orchestrator validate it. 
4. Opening `http://localhost:3000` loads the UI. 
5. Clicking **“Trigger Attack”** sends a POST to `/webhook`; the Mermaid diagram lights up step‑by‑step. 
6. After the exploit succeeds, the UI shows the **flag banner** (`CHIMERA{…}`). 
7. The **human‑approval overlay** appears with a diff preview. Approve → verifier runs, patch is applied, and the flag disappears. 
8. `curl http://localhost:8000/status/<trace_id>` returns JSON with `"status": "resolved"` and the final state. 
9. `curl http://localhost:8000/metrics` (or via Prometheus) shows non‑zero `chimera_runs_resolved_total`, `chimera_flag_capture_rate`, etc. 
10. Cleanup: `docker compose down -v` wipes containers and volumes; a fresh run repeats without leftover state. 

When every item above passes, you have a **fully‑functional, observable, securely‑hardened autonomous purple‑team pipeline** that satisfies the hackathon criteria and looks impressive to the judges.

---

*End of review.  Good luck, and enjoy the demo!*