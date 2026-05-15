# Tasks for Member 2: AI & Reasoning Specialist (Lead: LangGraph & Agents)

## Primary Responsibility
Designing the "Brain" of Project Chimera. You are responsible for the LangGraph state machine, the reasoning logic, and the high-quality prompts that drive the agents.

---

## Phase 1: Graph Orchestration (Hour 0 - 6)
- [ ] **LangGraph Scaffold:**
    - Define the `GraphState` TypedDict (include `iteration_count`, `trace_id`, `status`).
    - Set up the SQLite `MemorySaver` for state persistence.
- [ ] **Multi-Model Setup:**
    - Configure **Groq (Llama 3 70B)** for the Investigator node (High Speed).
    - Configure **Gemini 1.5 Pro (Google AI Studio)** for the Architect node (High Context).
    - Configure **Gemini 1.5 Flash** for the Summarizer sub-routine.
- [ ] **Structured Outputs:**
    - Use Pydantic models to force Groq/Gemini to return strict JSON for tool calls.

## Phase 2: Agent Logic (Hour 6 - 16)
- [ ] **Prompt Engineering:**
    - **Scout:** Prompt to analyze logs and identify vulnerability types.
    - **Investigator:** Deep reasoning prompt for hypothesis-based exploit generation.
    - **Architect:** Prompt to read source code and generate a surgical Git diff/patch.
- [ ] **Summarizer Sub-routine:**
    - Implement a "Pre-processor" node that uses a cheap model (Claude Haiku) to condense raw logs/network scans before the main agents see them.
- [ ] **Fallback Mechanism:**
    - Wrap LLM calls in a provider that tries Claude 3.5 Sonnet first, then falls back to OpenRouter or local Ollama if the API is down.

## Phase 3: Refinement & Validation (Hour 16 - 24)
- [ ] **Reflection Loop:**
    - Refine the logic that tells the Investigator *why* an exploit failed so it can pivot its strategy.
- [ ] **Human-in-the-Loop:**
    - Implement the `UserApprovalNode` that allows pausing the graph for a manual "Yes/No" before applying a patch.
- [ ] **System Prompt Hardening:**
    - Add "Safety Instructions" to prompts to prevent the AI from attempting `rm -rf` or other out-of-scope commands.

## Handover Deliverables
1. `graph.py` containing the compiled LangGraph workflow.
2. `prompts/` directory with versioned system prompts.
3. `schemas.py` with Pydantic models for all agent interactions.
