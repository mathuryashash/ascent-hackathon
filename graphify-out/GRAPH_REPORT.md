# Graph Report - .  (2026-05-16)

## Corpus Check
- 106 files · ~113,398 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 565 nodes · 822 edges · 28 communities detected
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 119 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_FastAPI Brain Service|FastAPI Brain Service]]
- [[_COMMUNITY_LangGraph Agent Nodes|LangGraph Agent Nodes]]
- [[_COMMUNITY_Autonomous Purple Team Pipeline|Autonomous Purple Team Pipeline]]
- [[_COMMUNITY_Chimera Pipeline State Machine|Chimera Pipeline State Machine]]
- [[_COMMUNITY_Gateway UI & Dashboard|Gateway UI & Dashboard]]
- [[_COMMUNITY_Docker Security Tools|Docker Security Tools]]
- [[_COMMUNITY_Agent Fleet Dashboard|Agent Fleet Dashboard]]
- [[_COMMUNITY_AI Prompts & Gateway UI|AI Prompts & Gateway UI]]
- [[_COMMUNITY_Pydantic Schemas|Pydantic Schemas]]
- [[_COMMUNITY_Docker Sandbox Tools|Docker Sandbox Tools]]
- [[_COMMUNITY_Omium UI Design System|Omium UI Design System]]
- [[_COMMUNITY_Victim Flask App (Gupta)|Victim Flask App (Gupta)]]
- [[_COMMUNITY_Victim Flask App (Aditya)|Victim Flask App (Aditya)]]
- [[_COMMUNITY_Brain Service Tests|Brain Service Tests]]
- [[_COMMUNITY_Omium Agent Orchestration|Omium Agent Orchestration]]
- [[_COMMUNITY_SIEM Monitor (Gupta)|SIEM Monitor (Gupta)]]
- [[_COMMUNITY_SIEM Simulator (Aditya)|SIEM Simulator (Aditya)]]
- [[_COMMUNITY_Dashboard UI Design|Dashboard UI Design]]
- [[_COMMUNITY_Dashboard Walkthrough & Review|Dashboard Walkthrough & Review]]
- [[_COMMUNITY_Auth Portal|Auth Portal]]
- [[_COMMUNITY_DB Init (Gupta)|DB Init (Gupta)]]
- [[_COMMUNITY_DB Init (Aditya)|DB Init (Aditya)]]
- [[_COMMUNITY_Tool Registry|Tool Registry]]
- [[_COMMUNITY_Omium Brand|Omium Brand]]
- [[_COMMUNITY_LangGraph Pipeline Dependencies|LangGraph Pipeline Dependencies]]
- [[_COMMUNITY_Aditya Docker Compose|Aditya Docker Compose]]
- [[_COMMUNITY_CTF Mode|CTF Mode]]
- [[_COMMUNITY_Victim Sandbox Requirements|Victim Sandbox Requirements]]

## God Nodes (most connected - your core abstractions)
1. `trace_node_enter()` - 14 edges
2. `trace_node_exit()` - 13 edges
3. `Project Chimera` - 12 edges
4. `Omium Command Design System` - 12 edges
5. `trace_node_error()` - 11 edges
6. `LangGraph Orchestrator` - 11 edges
7. `scout_node()` - 10 edges
8. `get_graph()` - 10 edges
9. `Project Chimera` - 10 edges
10. `Dashboard UI` - 10 edges

## Surprising Connections (you probably didn't know these)
- `image.png (dashboard screenshot)` --conceptually_related_to--> `Dashboard UI`  [INFERRED]
  image.png → DASHBOARD_COMPLETE.md
- `run_pipeline_and_broadcast()` --calls--> `run_chimera_pipeline()`  [INFERRED]
  ascent_gupta\services\brain\main.py → ascent_gupta\member_2_ai\graph.py
- `_MockResponse` --uses--> `GraphState`  [INFERRED]
  services\brain\graph.py → services\brain\schemas.py
- `_MockResponse` --uses--> `ScoutOutput`  [INFERRED]
  services\brain\graph.py → services\brain\schemas.py
- `_MockResponse` --uses--> `InvestigatorOutput`  [INFERRED]
  services\brain\graph.py → services\brain\schemas.py

## Hyperedges (group relationships)
- **LangGraph Pipeline Node Sequence** — Ingress_Node, Scout_Node, Summarizer_Node, Investigator_Node, Architect_Node, Verifier_Node, Evaluator_Node, Rollback_Node [EXTRACTED 1.00]
- **Docker Service Topology** — Victim_Service, Sandbox_Service, Orchestrator_Service, SIEM_Service, Gateway_UI, internal_net, public_net [EXTRACTED 1.00]
- **Team Member Role Assignments** — Member_1_Systems, Member_2_AI, Member_3_Integration_UI, Victim_Sandbox, Brain_Service, Gateway_UI [EXTRACTED 1.00]
- **AI Model Strategy by Node** — Scout_Node, Investigator_Node, Architect_Node, Verifier_Node, Gemini_1_5_Flash, Llama_3_70B_Groq, Gemini_1_5_Pro, Grok_3 [EXTRACTED 1.00]
- **Dashboard Technology Stack** — Dashboard_UI, WebSocket_Integration, Glassmorphism_Design, Tailwind_CSS, Material_Design_3, SSE_Event_Stream [EXTRACTED 1.00]
- **Security Isolation Architecture (Rationale)** — internal_net, Victim_Service, Sandbox_Service, Docker_Socket, Orchestrator_Service [EXTRACTED 1.00]
- **LangGraph Pipeline State Machine** — IngressNode, ScoutNode, SummarizerNode, InvestigatorNode, SandboxNode, EvaluatorNode, ArchitectNode, VerifierNode, RollbackNode [EXTRACTED 1.00]
- **Docker Compose Service Stack** — VictimService, SandboxService, OrchestratorService, SIEMService, GatewayUIService [EXTRACTED 1.00]
- **Team Member Role Assignments** — Member1Systems, Member2AI, Member3Integration [EXTRACTED 1.00]
- **Gateway UI Page Set** — DashboardUI, OrchestrationTimeline, ObservabilityPage, AuthPortal [EXTRACTED 1.00]
- **Chimera Multi-Agent Pipeline** — scout_role, summarizer_role, investigator_role, architect_role, verifier_role, human_approval_gate [EXTRACTED 1.00]
- **Chimera Three Service Members** — brain_readme, gateway_ui_readme, victim_sandbox_readme [EXTRACTED 1.00]
- **SQL Injection Detection to Patching Workflow** — scout_prompt, investigator_prompt, architect_prompt, verifier_prompt, sql_injection, parameterised_queries [EXTRACTED 1.00]
- **CHIMERA Dashboard Pages (Gateway UI)** — gateway_ui_index, gateway_ui_logs, gateway_ui_observability, gateway_ui_orchestration [EXTRACTED 1.00]
- **CHIMERA Dashboard Pages (Stitch)** — stitch_index, stitch_logs, stitch_observability, stitch_orchestration [EXTRACTED 1.00]
- **Omium Platform Screen Set** — dashboard_overview_screen, agent_orchestration_screen, observability_screen, secure_access_screen [EXTRACTED 1.00]
- **DataHarvest_V2 Agent Pipeline Flow** — source_webhook_node, search_agent_node, reasoning_agent_node, action_agent_node [EXTRACTED 1.00]
- **Omium Side Navigation Structure** — dashboard_nav_item, orchestration_nav_item, observability_nav_item, system_logs_nav_item, security_nav_item, support_nav_item [EXTRACTED 1.00]
- **Omium Typography System** — geist_typography, inter_typography, jetbrains_mono_typography [EXTRACTED 1.00]
- **Omium Trace Lineage Flow** — root_trigger_trace, decision_layer_trace, sql_extraction_trace, active_task_trace [EXTRACTED 1.00]
- **Omium Dashboard Hero Stats** — system_uptime_stat, avg_latency_stat, webhook_success_stat, active_tokens_stat [EXTRACTED 1.00]
- **Omium Active Pipelines** — automated_market_research_pipeline, security_audit_pipeline, supply_chain_optimization_pipeline, data_cleanse_alpha_pipeline [EXTRACTED 1.00]
- **Omium Agent Fleet** — agent_alpha_9_observer, agent_deep_reason_v4, agent_logicgate_02, agent_securitynode_x, agent_fleetmanager_core [EXTRACTED 1.00]
- **Omium Live Trace Console Events** — system_boot_event, llm_reasoning_step, tool_call_event, webhook_ingress_event [EXTRACTED 1.00]
- **Omium Design System Tokens** — omium_blue_color, surface_palette, status_tones, geist_typography, inter_typography, jetbrains_mono_typography, twelve_column_grid, tonal_elevation, soft_rectangular_shapes [EXTRACTED 1.00]

## Communities

### Community 0 - "FastAPI Brain Service"
Cohesion: 0.05
Nodes (59): FastAPI, get_graph(), approve_patch(), ConnectionManager, download_report(), full_state(), get_status(), handle_webhook() (+51 more)

### Community 1 - "LangGraph Agent Nodes"
Cohesion: 0.07
Nodes (47): architect_node(), build_graph(), _demo_invoke(), evaluator_node(), human_approval_node(), ingress_node(), investigator_node(), _invoke_with_retry() (+39 more)

### Community 2 - "Autonomous Purple Team Pipeline"
Cohesion: 0.07
Nodes (41): Architect Node, Autonomous Purple Team Pipeline, Brain Service, CTF Mode, Deterministic State Graph, Docker Socket, Evaluator Node, Flag (CTF Proof) (+33 more)

### Community 3 - "Chimera Pipeline State Machine"
Cohesion: 0.07
Nodes (36): build_graph(), Chimera Pipeline — LangGraph State Machine Wires up every node and defines cond, Kick off the autonomous pipeline.      Usage by Member 3:         async for e, Evaluator decides: loop back, move to patching, or give up., Verifier decides: resolved, retry patch, or rollback., Assemble and compile the full Chimera state machine., route_after_evaluator(), route_after_verifier() (+28 more)

### Community 4 - "Gateway UI & Dashboard"
Cohesion: 0.06
Nodes (37): Architect Node, Auth Portal Page, Brain Service (MCP Server), Dashboard UI, Deterministic State Graph Design Decision, Docker Sandboxing, Evaluator Node, FastAPI WebSocket Integration (+29 more)

### Community 5 - "Docker Security Tools"
Cohesion: 0.09
Nodes (27): Docker, Docker Compose, classify_line(), fire_webhook(), monitor(), SIEM Simulator — monitors victim container logs via Docker SDK. When a SQL inje, _sign(), tools/__init__.py — Unified tool interface for Project Chimera. Aliases physica (+19 more)

### Community 6 - "Agent Fleet Dashboard"
Cohesion: 0.06
Nodes (33): Active Pipelines Section, Active Task Trace Node (file_writer), Active Tokens 1.2M/h, Alpha-9 Observer Agent, DeepReason v4 Agent, Agent Fleet Section, FleetManager Core Agent, LogicGate 02 Agent (+25 more)

### Community 7 - "AI Prompts & Gateway UI"
Cohesion: 0.12
Nodes (30): Architect Agent Prompt (Blue Team), Architect Agent Role (Blue Team), Brain Service (AI & Reasoning), Flag Capture (HTB{...} / CHIMERA{...}), CHIMERA Command Center Dashboard, CHIMERA Event Stream Page, CHIMERA Metrics Dashboard, CHIMERA Pipeline View (+22 more)

### Community 8 - "Pydantic Schemas"
Cohesion: 0.09
Nodes (27): BaseModel, ArchitectOutput, GraphState, _GraphStateRequired, InvestigatorOutput, schemas.py — Pydantic models for all LangGraph agent interactions in Project Chi, Output from the Scout node., Output from the Investigator node. (+19 more)

### Community 9 - "Docker Sandbox Tools"
Cohesion: 0.1
Nodes (23): _docker(), execute_bash_sandboxed(), get_logs(), _patch_fallback(), tools.py — Low-level bridge between LangGraph agents and the Docker infrastructu, Fallback: apply diff with the POSIX `patch` command., Fetch the last `lines` log lines from a named Docker container.      Returns t, Execute a bash command inside the isolated sandbox container.      The sandbox (+15 more)

### Community 10 - "Omium UI Design System"
Cohesion: 0.09
Nodes (23): Autonomous v2.4, Dashboard Navigation Item, Deploy Agent Button, Enterprise Dark Mode Aesthetic, Omium Core Auth Portal, Geist Typography (Display/Headings), Subtle Glassmorphism UI Pattern, Inter Typography (Body Text) (+15 more)

### Community 11 - "Victim Flask App (Gupta)"
Cohesion: 0.16
Nodes (16): get_db(), health(), index(), log_request(), Project Chimera — Victim Flask App ==================================== INTENT, Health check endpoint used by Docker and the Orchestrator., Appends a structured log line to the access.log file., Returns a SQLite connection. (+8 more)

### Community 12 - "Victim Flask App (Aditya)"
Cohesion: 0.18
Nodes (15): get_db(), health(), index(), list_users(), log_request(), login(), Project Chimera — Victim Flask App ==================================== INTENTIO, Appends a structured log line to the access.log file. (+7 more)

### Community 13 - "Brain Service Tests"
Cohesion: 0.14
Nodes (5): Unit tests for services/brain/tools/security_tools.py. Docker SDK calls are mock, Patched file content must never invoke git apply., TestExecuteBashInSandbox, TestGetLogs, TestVerifyPatch

### Community 14 - "Omium Agent Orchestration"
Cohesion: 0.21
Nodes (15): ActionAgent Node, Agent DNA Configuration Panel, Agent Orchestration Screen, Cost Estimation Card ($0.042/run), DataHarvest_V2 Pipeline, Pipeline Flow Designer, Pipeline Metrics Bar (Latency, Tokens/Min), ReasoningAgent Node (+7 more)

### Community 15 - "SIEM Monitor (Gupta)"
Cohesion: 0.24
Nodes (13): build_payload(), check_line(), fire_webhook(), Sends the alert payload as a POST request to the orchestrator webhook., Checks a single log line against all suspicious patterns., Blocks until the log file exists, printing a status every 5 seconds., Tails the log file indefinitely, processing new lines as they appear., Returns True if we haven't fired for this pattern within the debounce window. (+5 more)

### Community 16 - "SIEM Simulator (Aditya)"
Cohesion: 0.22
Nodes (12): build_payload(), check_line(), fire_webhook(), Checks a single log line against all suspicious patterns., Blocks until the log file exists, printing a status every 5 seconds., Tails the log file indefinitely, processing new lines as they appear., Returns True if we haven't fired for this pattern within the debounce window., Constructs the standardized webhook alert payload. (+4 more)

### Community 17 - "Dashboard UI Design"
Cohesion: 0.18
Nodes (10): Dashboard UI, Glassmorphism Design, Material Design 3, Member 3 (Full-Stack & Integration), Orchestration Timeline Page, Tailwind CSS, WebSocket Integration, image.png (dashboard screenshot) (+2 more)

### Community 18 - "Dashboard Walkthrough & Review"
Cohesion: 0.29
Nodes (5): Cyber-Glitch Theme, HMAC Webhook Signing, SSE Event Stream, Trigger Attack Button, services/gateway_ui/src/server.js

### Community 19 - "Auth Portal"
Cohesion: 0.4
Nodes (5): AES-256 Encryption Badge, Enterprise Auth Portal, Federated Auth SSO (Google + GitHub), Login Form (Email + Access Key), Secure Access Auth Screen

### Community 20 - "DB Init (Gupta)"
Cohesion: 0.67
Nodes (2): init_db(), Project Chimera — Victim Database Initializer =================================

### Community 21 - "DB Init (Aditya)"
Cohesion: 0.67
Nodes (1): Project Chimera — Victim Database Initializer =================================

### Community 24 - "Tool Registry"
Cohesion: 1.0
Nodes (2): TOOL_REGISTRY, services/brain/tools/security_tools.py

### Community 25 - "Omium Brand"
Cohesion: 1.0
Nodes (2): Omium Core Brand, Omium SDK

### Community 26 - "LangGraph Pipeline Dependencies"
Cohesion: 1.0
Nodes (2): Brain Dependencies (FastAPI, LangChain, LangGraph), LangGraph Pipeline

### Community 32 - "Aditya Docker Compose"
Cohesion: 1.0
Nodes (1): ascent_aditya/docker-compose.yml

### Community 33 - "CTF Mode"
Cohesion: 1.0
Nodes (1): CTF Mode

### Community 34 - "Victim Sandbox Requirements"
Cohesion: 1.0
Nodes (1): Victim Sandbox Root Requirements

## Knowledge Gaps
- **224 isolated node(s):** `Returns True if we haven't fired for this pattern within the debounce window.`, `Constructs the standardized webhook alert payload.`, `Sends the alert payload as a POST request to the orchestrator webhook.`, `Checks a single log line against all suspicious patterns.`, `Blocks until the log file exists, printing a status every 5 seconds.` (+219 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `DB Init (Gupta)`** (4 nodes): `init_db.py`, `init_db.py`, `init_db()`, `Project Chimera — Victim Database Initializer =================================`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `DB Init (Aditya)`** (3 nodes): `init_db.py`, `init_db()`, `Project Chimera — Victim Database Initializer =================================`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Tool Registry`** (2 nodes): `TOOL_REGISTRY`, `services/brain/tools/security_tools.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Omium Brand`** (2 nodes): `Omium Core Brand`, `Omium SDK`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `LangGraph Pipeline Dependencies`** (2 nodes): `Brain Dependencies (FastAPI, LangChain, LangGraph)`, `LangGraph Pipeline`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Aditya Docker Compose`** (1 nodes): `ascent_aditya/docker-compose.yml`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `CTF Mode`** (1 nodes): `CTF Mode`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Victim Sandbox Requirements`** (1 nodes): `Victim Sandbox Root Requirements`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GraphState` connect `Autonomous Purple Team Pipeline` to `Gateway UI & Dashboard`?**
  _High betweenness centrality (0.108) - this node is a cross-community bridge._
- **Why does `Project Chimera` connect `Gateway UI & Dashboard` to `Autonomous Purple Team Pipeline`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Why does `FastAPI` connect `FastAPI Brain Service` to `Autonomous Purple Team Pipeline`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Are the 32 inferred relationships involving `str` (e.g. with `build_payload()` and `build_payload()`) actually correct?**
  _`str` has 32 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `trace_node_enter()` (e.g. with `ingress_node()` and `scout_node()`) actually correct?**
  _`trace_node_enter()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `trace_node_exit()` (e.g. with `ingress_node()` and `scout_node()`) actually correct?**
  _`trace_node_exit()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Returns True if we haven't fired for this pattern within the debounce window.`, `Constructs the standardized webhook alert payload.`, `Sends the alert payload as a POST request to the orchestrator webhook.` to the rest of the system?**
  _224 weakly-connected nodes found - possible documentation gaps or missing edges._