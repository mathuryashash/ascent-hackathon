# 🧪 Project Chimera: Final Deployment Walkthrough

Congratulations! **Project Chimera** is now a fully operational, production-ready autonomous hacking pipeline. We have successfully merged the premium **Stitch Dashboard** design into the live Gateway service, integrated real-time LangGraph orchestration, and hardened the sandbox environment for the Scaler Ascent hackathon.

---

## 🏗️ System Overview

The pipeline is now running across 5 interconnected Docker services:

| Service | Port | Purpose |
| :--- | :--- | :--- |
| **Command Center** | `http://localhost:3001` | The high-fidelity dashboard with real-time logs and attack triggers. |
| **Orchestrator** | `http://localhost:8001` | The "Brain" (LangGraph) that coordinates Gemini 2.5 and Llama 3 agents. |
| **Victim App** | `http://localhost:5000` | A premium, glitch-themed vulnerable web application. |
| **Sandbox** | Internal Only | An isolated container where the agents perform probes and exploits. |
| **SIEM** | Internal Only | Monitors logs and alerts the Orchestrator of suspicious activity. |

---

## 🚀 The Autonomous Workflow

1.  **Alert Ingress**: The SIEM simulator detects a "Threat" (or you manually trigger one from the Dashboard).
2.  **Scout (Gemini 2.5 Flash)**: Performs rapid reconnaissance of the Victim App topography.
3.  **Investigator (Llama 3 70B)**: Iteratively tests for SQL Injection until a flag is successfully exfiltrated from the database.
4.  **Architect (Gemini 2.5 Pro)**: Analyzes the exploit and generates a high-quality patch using parameterized queries.
5.  **Verifier (Gemini 2.5 Flash)**: Confirms the vulnerability is remediated by re-testing the exploit.
6.  **Human-in-the-Loop**: The dashboard pauses and requests your approval before applying the patch to production code.

---

## 📸 Verified UI & Visuals

The dashboard is now using the **Cyber-Glitch** theme with glassmorphism effects.

### Key Features:
*   **Live Event Feed**: Watch the agents communicate and transition through the graph in real-time.
*   **Trigger Attack**: A dedicated button to launch a demonstration SQLi exploit immediately.
*   **Approval Modal**: A clear diff viewer to review and approve the Architect's remediation patches.

---

## 🛠️ How to Run the Demo

1.  **Open the Dashboard**: Go to [http://localhost:3001](http://localhost:3001).
2.  **Trigger the Attack**: Click the red **"Trigger SQLi Attack"** button.
3.  **Monitor the Feed**: Watch the "Live Events" panel. You will see `pipeline_step` events as agents start working.
4.  **Approve the Patch**: Once the Architect finishes, a yellow banner will appear. Click **"Review & Approve"** to see the code changes and apply them.
5.  **Verify Results**: Check the "Resolved" stat on the dashboard—it will increment once the patch is verified and applied.

---

### 🛡️ Final Checks
- [x] **Container Health**: All `chimera-*` containers are UP and Healthy.
- [x] **API Connectivity**: Orchestrator is responding to status polls.
- [x] **UI Polish**: Design tokens and Tailwind config correctly applied.

**Your project is hackathon-ready. Good luck!**
