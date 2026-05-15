"""
graph.py — LangGraph state machine for Project Chimera.

Workflow:
  ingress → scout → summarizer → investigator → sandbox → evaluator
                        ↑                                    |
                        └──── (retry, iter<10) ──────────────┘
                                                             |
                        (flag captured) ─────────────────────┤
                                                             ↓
                                                       architect → human_approval → verifier → resolved
                                                                                            ↓ (fail)
                                                                                         rollback

State persistence: SQLite via LangGraph SqliteSaver.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
import asyncio
from pathlib import Path
from typing import Literal, Dict, Any, Optional

import structlog
from tracing import configure_logging
configure_logging()

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END

# Local imports
from tools.security_tools import (
    get_logs,
    execute_bash_in_sandbox as execute_bash_sandboxed,
    apply_patch_to_victim as verify_patch,
    run_http_probe,
    get_victim_source,
)
from metrics import record_run_start, record_run_end
from tracing import trace_node_enter, trace_node_exit, trace_node_error
from schemas import (
    GraphState,
    ScoutOutput,
    InvestigatorOutput,
    ArchitectOutput,
    VerifierOutput,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# LLM Setup
# ---------------------------------------------------------------------------

def _make_scout_llm():
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_FLASH_MODEL", "gemini-1.5-flash"),
        google_api_key=os.environ["GEMINI_API_KEY"],
        temperature=0,
    )

def _make_investigator_llm():
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        groq_api_key=os.environ["GROQ_API_KEY"],
        temperature=0,
    )

def _make_architect_llm():
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_PRO_MODEL", "gemini-1.5-pro"),
        google_api_key=os.environ["GEMINI_API_KEY"],
        temperature=0,
    )

def _load_prompt(name: str) -> str:
    prompt_dir = Path(__file__).parent / "prompts"
    file_path = prompt_dir / f"{name}_prompt.txt"
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")

def _parse_json_response(content: str, model_cls):
    clean = re.sub(r"```(?:json)?\s*", "", content).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response: {content[:200]}")
    data = json.loads(match.group(0), strict=False)
    return model_cls.model_validate(data)

def _truncate(text: str, max_chars: int = 2000) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[TRUNCATED]"
    return text

# ---------------------------------------------------------------------------
# Node 1: Ingress
# ---------------------------------------------------------------------------

def ingress_node(state: GraphState) -> GraphState:
    trace_id = state.get("trace_id") or str(uuid.uuid4())
    log.info("ingress", trace_id=trace_id)
    new_state = {
        **state,
        "trace_id": trace_id,
        "messages": [],
        "status": "scouting",
        "iteration_count": 0,
    }
    return new_state

# ---------------------------------------------------------------------------
# Node 2: Scout
# ---------------------------------------------------------------------------

async def scout_node(state: GraphState) -> GraphState:
    trace_id = state["trace_id"]
    log.info("scout_start", trace_id=trace_id)
    
    raw_logs = get_logs(tail_lines=100)
    system_prompt = _load_prompt("scout")
    llm = _make_scout_llm()
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Alert: {json.dumps(state['alert_payload'])}\nLogs: {json.dumps(raw_logs)}"),
    ]
    
    response = await llm.ainvoke(messages)
    scout_out = _parse_json_response(response.content, ScoutOutput)
    
    return {
        **state,
        "target_topography": scout_out.topography_summary,
        "current_hypothesis": scout_out.recommended_approach,
        "scout_findings": scout_out.model_dump_json(),
        "status": "summarizing",
        "messages": state["messages"] + [{"role": "scout", "content": scout_out.topography_summary}],
    }

# ---------------------------------------------------------------------------
# Node 3: Summarizer
# ---------------------------------------------------------------------------

async def summarizer_node(state: GraphState) -> GraphState:
    log.info("summarizer_start", trace_id=state["trace_id"])
    raw_content = state["scout_findings"]
    prompt = _load_prompt("summarizer").format(raw_output=_truncate(raw_content, 4000))
    
    llm = _make_scout_llm()
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    
    return {
        **state,
        "target_topography": response.content,
        "status": "investigating",
    }

# ---------------------------------------------------------------------------
# Node 4: Investigator
# ---------------------------------------------------------------------------

async def investigator_node(state: GraphState) -> GraphState:
    trace_id = state["trace_id"]
    log.info("investigator_start", trace_id=trace_id, iter=state["iteration_count"])
    
    system_prompt = _load_prompt("investigator")
    llm = _make_investigator_llm()
    
    context = f"Topography: {state['target_topography']}\n"
    if state.get("failure_reason"):
        context += f"Last Failure: {state['failure_reason']}\n"
        
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=context),
    ]
    
    response = await llm.ainvoke(messages)
    inv_out = _parse_json_response(response.content, InvestigatorOutput)
    
    return {
        **state,
        "exploit_proof": inv_out.exploit_payload,
        "current_hypothesis": inv_out.hypothesis,
        "messages": state["messages"] + [{"role": "investigator", "content": inv_out.hypothesis}],
        "status": "sandbox_running"
    }

# ---------------------------------------------------------------------------
# Node 5: Sandbox
# ---------------------------------------------------------------------------

async def sandbox_node(state: GraphState) -> GraphState:
    payload = state["exploit_proof"]
    log.info("sandbox_start", trace_id=state["trace_id"])
    
    result = execute_bash_sandboxed(payload)
    output = result.get("stdout", "")
    
    flag_match = re.search(r"CHIMERA\{[^}]+\}", output, re.IGNORECASE)
    captured_flag = flag_match.group(0) if flag_match else ""
    
    return {
        **state,
        "captured_flag": captured_flag,
        "failure_reason": "Flag not found in output" if not captured_flag else "",
        "status": "evaluating",
        "iteration_count": state["iteration_count"] + 1,
        "messages": state["messages"] + [{"role": "sandbox", "content": f"Exit: {result.get('exit_code')}, Flag: {'Captured' if captured_flag else 'Failed'}"}]
    }

# ---------------------------------------------------------------------------
# Node 6: Evaluator
# ---------------------------------------------------------------------------

def evaluator_node(state: GraphState) -> GraphState:
    if state["captured_flag"]:
        return {**state, "status": "patching"}
    if state["iteration_count"] >= 10:
        return {**state, "status": "failed"}
    return {**state, "status": "investigating"}

def route_after_evaluator(state: GraphState) -> str:
    return state["status"]

# ---------------------------------------------------------------------------
# Node 7: Architect
# ---------------------------------------------------------------------------

async def architect_node(state: GraphState) -> GraphState:
    log.info("architect_start", trace_id=state["trace_id"])
    
    source_code = get_victim_source("app.py").get("content", "")
    system_prompt = _load_prompt("architect")
    llm = _make_architect_llm()
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Code:\n{source_code}\n\nExploit:\n{state['exploit_proof']}"),
    ]
    
    response = await llm.ainvoke(messages)
    arch_out = _parse_json_response(response.content, ArchitectOutput)
    
    return {
        **state,
        "remediation_patch": arch_out.patched_content,
        "original_source": source_code,
        "status": "awaiting_approval",
        "messages": state["messages"] + [{"role": "architect", "content": arch_out.explanation}]
    }

# ---------------------------------------------------------------------------
# Node 8: Human Approval
# ---------------------------------------------------------------------------

def human_approval_node(state: GraphState) -> GraphState:
    return state

def route_after_human_approval(state: GraphState) -> str:
    if state.get("human_approved") is True:
        return "verifier"
    return END

# ---------------------------------------------------------------------------
# Node 9: Verifier
# ---------------------------------------------------------------------------

async def verifier_node(state: GraphState) -> GraphState:
    log.info("verifier_start", trace_id=state["trace_id"])

    # Apply patch
    apply_res = verify_patch("app.py", state["remediation_patch"])
    if apply_res.get("status") != "success":
        return {**state, "status": "rollback", "failure_reason": apply_res.get("message")}

    # Re-run the exact same exploit — deterministically check if flag is still leaking
    result = execute_bash_sandboxed(state["exploit_proof"])
    output = result.get("stdout", "")

    flag_still_present = bool(re.search(r"CHIMERA\{[^}]+\}", output, re.IGNORECASE))
    if flag_still_present:
        return {**state, "status": "rollback", "failure_reason": "Patch did not block exploit — flag still visible in output"}
    return {**state, "status": "resolved"}

def route_after_verifier(state: GraphState) -> str:
    return state["status"]

# ---------------------------------------------------------------------------
# Node 10: Rollback
# ---------------------------------------------------------------------------

def rollback_node(state: GraphState) -> GraphState:
    if state.get("original_source"):
        verify_patch("app.py", state["original_source"])
    return {**state, "status": "failed"}

# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------

def build_graph(checkpointer=None):
    builder = StateGraph(GraphState)
    
    builder.add_node("ingress", ingress_node)
    builder.add_node("scout", scout_node)
    builder.add_node("summarizer", summarizer_node)
    builder.add_node("investigator", investigator_node)
    builder.add_node("sandbox", sandbox_node)
    builder.add_node("evaluator", evaluator_node)
    builder.add_node("architect", architect_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("verifier", verifier_node)
    builder.add_node("rollback", rollback_node)
    
    builder.set_entry_point("ingress")
    
    builder.add_edge("ingress", "scout")
    builder.add_edge("scout", "summarizer")
    builder.add_edge("summarizer", "investigator")
    builder.add_edge("investigator", "sandbox")
    builder.add_edge("sandbox", "evaluator")
    
    builder.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        {
            "investigating": "investigator",
            "patching": "architect",
            "failed": END
        }
    )
    
    builder.add_edge("architect", "human_approval")
    
    builder.add_conditional_edges(
        "human_approval",
        route_after_human_approval,
        {
            "verifier": "verifier",
            END: END
        }
    )
    
    builder.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {
            "resolved": END,
            "rollback": "rollback"
        }
    )
    
    builder.add_edge("rollback", END)
    
    return builder.compile(checkpointer=checkpointer, interrupt_before=["human_approval"])

_graph = None
_graph_checkpointer = None

def get_graph(checkpointer=None):
    """Return the compiled graph. Rebuilds only when a new checkpointer is provided for the first time."""
    global _graph, _graph_checkpointer
    if _graph is None or (checkpointer is not None and checkpointer is not _graph_checkpointer):
        _graph = build_graph(checkpointer)
        _graph_checkpointer = checkpointer
    return _graph
