# Project Chimera 🔴
**Autonomous Purple Team Pipeline** — 24-Hour Hackathon Build

---

## 1. Quick Start

```bash
# 1. Copy and fill in your environment variables
cp .env.example .env
# Edit .env and set XAI_API_KEY (get it at https://console.x.ai/)

# 2. Spin up all containers
docker compose up --build -d

# 3. Watch the logs (optional)
docker compose logs -f

# 4. Start the SIEM simulator (on your host machine, in a separate terminal)
python siem_simulator.py
```

---

## 2. Testing the Victim App

The Victim App is **NOT** exposed on a host port by design. All access is through the Docker internal network.  
**Exception:** To test directly during development, temporarily add `ports: ["5000:5000"]` to the `victim` service in `docker-compose.yml`.

```bash
# Benign search (returns 2 laptop products)
docker exec chimera-sandbox curl -s "http://chimera-victim:5000/search?q=laptop"

# SQL Injection — URL-encoded payload (curl 8.x+ requires this)
# Payload: ' UNION SELECT 1,2,3,4--
docker exec chimera-sandbox curl -s "http://chimera-victim:5000/search?q=%27%20UNION%20SELECT%201%2C2%2C3%2C4--"

# Health check
docker exec chimera-sandbox curl -s "http://chimera-victim:5000/health"
```

> [!NOTE]
> **PowerShell quoting:** Always use URL-encoded payloads when testing from a Windows terminal.
> `'` → `%27`, space → `%20`, `,` → `%2C`. The AI agents use `urllib.parse.urlencode()` internally so they handle this automatically.

---

## 3. Tool API Reference (for Member 2)

All tools are in `services/brain/tools/security_tools.py` and importable via:

```python
from tools.security_tools import TOOL_REGISTRY
```

| Tool | Args | Returns |
|------|------|---------|
| `get_logs` | `tail_lines: int = 50` | `{status, log_lines[], suspicious_entries[]}` |
| `execute_bash_in_sandbox` | `command: str, timeout_seconds: int = 30` | `{status, stdout, stderr, exit_code, command_executed}` |
| `run_http_probe` | `path: str, params: dict = None, method: str = "GET"` | `{status, http_status_code, response_body, response_length, contains_sql_error, payload_used}` |
| `apply_patch_to_victim` | `filename: str, patched_content: str` | `{status, filename, bytes_written, backup_created, backup_path}` |
| `get_victim_source` | `filename: str = "app.py"` | `{status, filename, content, line_count}` |

---

## 4. Network Map

```
┌─────────────────────────────────────────────────────────────┐
│                     HOST MACHINE                            │
│                                                             │
│  python siem_simulator.py  ──────►  localhost:8000          │
│                                                             │
│  ┌────────────────── chimera-external ──────────────────┐   │
│  │                                                      │   │
│  │  ┌──────────────────────────────────────────────┐   │   │
│  │  │            chimera-internal                  │   │   │
│  │  │                                              │   │   │
│  │  │  [chimera-victim:5000]  ◄──────────────────┐│   │   │
│  │  │       Flask App                             ││   │   │
│  │  │                                             ││   │   │
│  │  │  [chimera-sandbox]  ────────────────────────┘│   │   │
│  │  │    exec environment                          │   │   │
│  │  │       (no internet)                          │   │   │
│  │  │                                              │   │   │
│  │  └──────────────────────────────────────────────┘   │   │
│  │                                                      │   │
│  │  [chimera-orchestrator:8000] ──► Claude API (internet)   │
│  │       FastAPI + LangGraph                            │   │
│  │       (on both networks)                             │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

KEY: internal=true → No internet access for victim + sandbox
```

> [!TIP]
> Get your Grok API key at **[console.x.ai](https://console.x.ai/)**. The model to use is `grok-3`.
> Grok is OpenAI-API-compatible — initialize with `ChatXAI` from `langchain-xai` in Member 2's code.

---

## 5. Handover Notes for Member 2 (LangGraph / Orchestrator)

- **Import path:** `from tools.security_tools import TOOL_REGISTRY`
- **All 5 tools** are in `services/brain/tools/security_tools.py`
- **Docker socket** is mounted at `/var/run/docker.sock` in the orchestrator container
- **Sandbox container name:** `chimera-sandbox`
- **Victim host (from sandbox):** `http://chimera-victim:5000`
- **Log path (mounted into orchestrator):** `/app/victim-logs/access.log`
- **Victim source (mounted into orchestrator):** `/app/victim-src/app.py`
- **Placeholder FastAPI app** is at `services/brain/main.py` — replace `/webhook/alert` logic with `run_chimera_pipeline()`

---

## 6. Handover Notes for Member 3 (Frontend & Integration)

- **Webhook URL:** `POST http://localhost:8000/webhook/alert`
- **Status polling:** `GET http://localhost:8000/status/{trace_id}`
- **All traces:** `GET http://localhost:8000/traces`

**Webhook Payload Schema (fired by `siem_simulator.py`):**

```json
{
  "alert_id": "uuid4-string",
  "timestamp": "2024-01-15T10:23:45Z",
  "severity": "HIGH",
  "source": "siem_simulator",
  "target": {
    "host": "chimera-victim",
    "port": 5000,
    "service": "flask-app"
  },
  "trigger": {
    "log_line": "the raw suspicious log line",
    "matched_pattern": "UNION SELECT",
    "route": "/search"
  },
  "metadata": {
    "victim_log_path": "./services/victim_sandbox/logs/access.log"
  }
}
```

---

## 7. Verification Checklist

```bash
# Verify orchestrator is up
curl http://localhost:8000/health

# Verify sandbox has NO internet (should fail/timeout)
docker exec chimera-sandbox ping -c 1 8.8.8.8

# Verify sandbox CAN reach victim (should return {"status": "ok"})
docker exec chimera-sandbox curl http://chimera-victim:5000/health

# Verify TOOL_REGISTRY is importable
docker exec chimera-orchestrator python -c "from tools.security_tools import TOOL_REGISTRY; print(list(TOOL_REGISTRY.keys()))"
```
