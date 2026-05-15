# Tasks for Member 1: Systems & Security Specialist (Lead: Victim & Sandbox)

## Primary Responsibility
Building the vulnerable environment (Victim), the isolated execution environment (Sandbox), and the low-level Python tools that bridge the AI to the system.

---

## Phase 1: Environment Setup (Hour 0 - 6)
- [ ] **Victim Application:**
    - Create a Python/Flask or Node.js web application.
    - Implement a `/search` or `/login` endpoint with a clear SQL Injection vulnerability (use raw string formatting for queries).
    - Connect it to an SQLite or Postgres database with mock user data and "secrets" for the AI to find.
- [ ] **Docker-Compose Architecture:**
    - Define three services: `orchestrator`, `sandbox`, and `victim`.
    - **Isolation:** Put `sandbox` and `victim` on a private bridge network (`internal_net`).
    - **Resource Constraints:** Limit the `sandbox` container to 0.5 CPU and 256MB RAM.
    - **User Mapping:** Ensure containers run as non-root users.
- [ ] **Image Pinning:** Use specific version tags (e.g., `python:3.11-slim@sha256:...`) in the Dockerfile and Compose file.

## Phase 2: Tool Development (Hour 6 - 16)
- [ ] **Python Tool Wrappers:**
    - `get_logs(service_name, lines)`: Fetches logs from Docker containers.
    - `execute_bash_sandboxed(command)`: Uses `docker exec` to run commands in the `sandbox` container with a 10s timeout.
    - `verify_patch(file_path, diff)`: Applies a diff and returns a success/fail status.
- [ ] **SIEM Simulator:**
    - Write a script that monitors the Victim's access logs.
    - When it detects a pattern (e.g., `' OR '1'='1`), it fires a JSON POST request (Webhook) to the Orchestrator's `/webhook` endpoint.

## Phase 3: Hardening & Support (Hour 16 - 24)
- [ ] **Secrets Protection:**
    - Set up the `.env` file structure.
    - Ensure no secrets are mounted into the `sandbox` container.
- [ ] **Demo Validation:**
    - Assist Member 2 in testing the "Exploit Proof" payload.
    - Confirm that the final patch actually prevents the exploit.

## Handover Deliverables
1. `docker-compose.yml` defining the stack.
2. Python module `tools.py` with validated tool functions for the LangGraph agents.
3. Vulnerable source code for the Architect agent to analyze.
