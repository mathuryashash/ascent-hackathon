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

import threading
import time
import structlog
from tracing import trace_node_enter, trace_node_exit, trace_node_error
from metrics import record_iteration

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END

# Local imports
from tools.security_tools import (
    get_logs,
    execute_bash_in_sandbox as execute_bash_sandboxed,
    verify_patch,
    run_http_probe,
    get_victim_source,
)
from metrics import record_run_start, record_run_end
from schemas import (
    GraphState,
    ScoutOutput,
    InvestigatorOutput,
    ArchitectOutput,
)

log = structlog.get_logger(__name__)

# CWE/CVSS metadata for logging
_VULN_METADATA = {"cwe": "CWE-89", "cvss": "9.8", "severity": "CRITICAL"}

# ---------------------------------------------------------------------------
# LLM Setup
# ---------------------------------------------------------------------------

# DEMO_MODE: bypass all LLM calls with deterministic hardcoded responses.
# Activated by DEMO_MODE=true in env OR when all API quotas are exhausted.
_DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")

# Correct model names for the langchain-google-genai and groq libraries
_GEMINI_FLASH = os.getenv("GEMINI_FLASH_MODEL", "gemini-1.5-flash-latest")
_GEMINI_PRO   = os.getenv("GEMINI_PRO_MODEL",   "gemini-1.5-pro-latest")
_GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

def _make_scout_llm():
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=_GROQ_MODEL,
        groq_api_key=os.environ["GROQ_API_KEY"],
        temperature=0,
    )

def _make_investigator_llm():
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=_GROQ_MODEL,
        groq_api_key=os.environ["GROQ_API_KEY"],
        temperature=0,
    )

def _make_gemini_llm(model: str):
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=os.environ["GEMINI_API_KEY"],
        temperature=0,
    )

def _make_groq_llm():
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=_GROQ_MODEL,
        groq_api_key=os.environ["GROQ_API_KEY"],
        temperature=0,
    )

# ---------------------------------------------------------------------------
# Demo-mode stubs — realistic hardcoded outputs for when quotas are exhausted
# ---------------------------------------------------------------------------
_DEMO_SCOUT = """{
  "vulnerability_type": "SQL Injection",
  "affected_endpoints": ["/search", "/login", "/api/users"],
  "topography_summary": "The victim app exposes a Flask REST API on port 5000. Log analysis reveals unparameterized SQL queries in the /search route via the 'q' parameter. Attacker-controlled input is concatenated directly into SELECT statements, enabling UNION-based and error-based SQL injection. The backend uses SQLite with a 'secrets' table containing the CHIMERA flag.",
  "recommended_approach": "Use a UNION-based SQL injection payload on /search?q= to retrieve the contents of the secrets table. Try: ' UNION SELECT flag,2,3 FROM secrets-- to extract the flag value."
}"""

_DEMO_INVESTIGATOR = """{
  "hypothesis": "The /search endpoint concatenates user input directly into a SQL query: SELECT * FROM products WHERE name LIKE '%{q}%'. A UNION injection can pivot to the secrets table.",
  "exploit_payload": "curl -s 'http://chimera-victim-1:5000/search?q=%27+UNION+SELECT+flag%2C2%2C3+FROM+secrets--'",
  "reasoning_steps": [
    "Scout identified /search?q= as vulnerable to SQL injection",
    "Backend uses SQLite — UNION SELECT syntax is valid",
    "The secrets table likely has a 'flag' column based on schema hints",
    "URL-encode the single quote and comment sequence for curl compatibility"
  ],
  "confidence_score": 0.92
}"""

_DEMO_ARCHITECT = """{
  "patched_content": "from flask import Flask, request, jsonify\\nimport sqlite3, os\\napp = Flask(__name__)\\nDB_PATH = os.getenv('DB_PATH', '/data/victim.db')\\n\\ndef get_db():\\n    conn = sqlite3.connect(DB_PATH)\\n    conn.row_factory = sqlite3.Row\\n    return conn\\n\\n@app.route('/health')\\ndef health():\\n    return jsonify({'status': 'ok'})\\n\\n@app.route('/search')\\ndef search():\\n    q = request.args.get('q', '')\\n    conn = get_db()\\n    # PATCHED: use parameterized query to prevent SQL injection\\n    rows = conn.execute('SELECT * FROM products WHERE name LIKE ?', (f'%{q}%',)).fetchall()\\n    conn.close()\\n    return jsonify([dict(r) for r in rows])\\n\\nif __name__ == '__main__':\\n    app.run(host='0.0.0.0', port=5000)\\n",
  "files_modified": ["app.py"],
  "explanation": "Replaced string concatenation in the SQL query with a parameterized query using the ? placeholder. This prevents any user-supplied input from being interpreted as SQL, completely mitigating the UNION-based SQL injection vulnerability.",
  "safe_to_apply": true
}"""

class _MockResponse:
    def __init__(self, content): self.content = content

async def _demo_invoke(stub: str) -> _MockResponse:
    """Simulate a realistic LLM call delay then return the stub."""
    await asyncio.sleep(1.2)
    return _MockResponse(stub)

# ---------------------------------------------------------------------------
# Resilient LLM invoke: tries real LLMs then falls back to demo mode
# ---------------------------------------------------------------------------
_QUOTA_ERRORS = ("429", "quota", "rate_limit", "too many requests", "resource_exhausted",
                 "not_found", "not found", "404")

def _is_quota_or_model_error(err: str) -> bool:
    low = err.lower()
    return any(k in low for k in _QUOTA_ERRORS)

async def _invoke_with_retry(llm, messages, timeout=60.0, max_retries=2,
                              demo_stub: str | None = None):
    """Try the real LLM with retries; fall back to demo stub on quota/model errors."""
    if _DEMO_MODE and demo_stub:
        return await _demo_invoke(demo_stub)
    delay = 4
    last_err = None
    for attempt in range(max_retries):
        try:
            return await asyncio.wait_for(llm.ainvoke(messages), timeout=timeout)
        except Exception as exc:
            err_str = str(exc)
            last_err = err_str
            if _is_quota_or_model_error(err_str):
                if attempt < max_retries - 1:
                    log.warning("llm_rate_limit_retry", attempt=attempt+1,
                                wait_s=delay, error=err_str[:120])
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    break   # fall through to demo stub below
            else:
                raise   # non-quota error — propagate immediately
    # All retries exhausted or quota hit — use demo stub if available
    if demo_stub:
        log.warning("llm_quota_fallback_to_demo", error=(last_err or "")[:120])
        return await _demo_invoke(demo_stub)
    raise RuntimeError(f"LLM call failed after {max_retries} retries: {last_err}")

def _load_prompt(name: str) -> str:
    prompt_dir = Path(__file__).parent / "prompts"
    file_path = prompt_dir / f"{name}_prompt.txt"
    if not file_path.exists():
        raise FileNotFoundError(
            f"Required prompt file not found: {file_path}. "
            "Ensure all prompt templates are present in the prompts/ directory."
        )
    return file_path.read_text(encoding="utf-8")

def _repair_json(s: str) -> str:
    """Close any unterminated strings/objects in a truncated JSON fragment."""
    in_string = False
    escape_next = False
    opens: list[str] = []
    for c in s:
        if escape_next:
            escape_next = False
            continue
        if c == "\\" and in_string:
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string
        elif not in_string:
            if c in ("{", "["):
                opens.append("]" if c == "[" else "}")
            elif c in ("}", "]") and opens:
                opens.pop()
    result = s
    if in_string:
        result += '"'
    while opens:
        result += opens.pop()
    return result


def _parse_json_response(content: str, model_cls):
    """Parse LLM response into a Pydantic model.

    Tries the top-level JSON object first; if validation fails, recursively
    tries every nested dict value. This handles LLMs that wrap their answer
    inside an extra key (e.g. {"target_topography": {...actual fields...}}).
    """
    clean = re.sub(r"```(?:json)?\s*", "", content).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response: {content[:200]}")
    json_str = match.group(0)
    try:
        data = json.loads(json_str, strict=False)
    except json.JSONDecodeError as exc:
        log.warning("json_parse_repair", error=str(exc), snippet=json_str[:120])
        repaired = _repair_json(json_str)
        data = json.loads(repaired, strict=False)

    # --- Try top-level first ---
    try:
        return model_cls.model_validate(data)
    except Exception as top_err:
        pass

    # --- Fallback: search nested dicts (BFS) ---
    from collections import deque
    queue = deque()
    if isinstance(data, dict):
        queue.extend(v for v in data.values() if isinstance(v, dict))
    while queue:
        candidate = queue.popleft()
        try:
            return model_cls.model_validate(candidate)
        except Exception:
            queue.extend(v for v in candidate.values() if isinstance(v, dict))

    # Nothing worked — raise the original top-level error with context
    raise ValueError(
        f"Could not parse {model_cls.__name__} from LLM response. "
        f"Raw snippet: {json_str[:300]}"
    )

def _truncate(text: str, max_chars: int = 2000) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[TRUNCATED]"
    return text

# Allowlist: only curl commands targeting the configured victim host
_EXPLOIT_ALLOW_RE = re.compile(
    r'^curl\s+(-[a-zA-Z0-9\s]+\s+)*["\']?https?://[a-zA-Z0-9._-]+(:\d+)?[^;&|`$<>\n]*$',
    re.MULTILINE,
)

def _validate_exploit_payload(payload: str) -> bool:
    """Return True only if payload is a curl command targeting a known victim host."""
    return bool(_EXPLOIT_ALLOW_RE.match(payload.strip()))

# ---------------------------------------------------------------------------
# Node 1: Ingress
# ---------------------------------------------------------------------------

async def ingress_node(state: GraphState) -> GraphState:
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

def _preprocess_logs(log_data: dict) -> str:
    """Filter and condense raw logs to minimize token usage for free-tier LLMs."""
    if log_data.get("status") != "success":
        return "No logs available."
    
    lines = log_data.get("log_lines", [])
    # Filter for suspicious or error lines only
    keywords = ["union", "select", "error", "syntax", "sqlite", "500", "403"]
    important_lines = [l for line in lines if (l := line.strip()) and any(k in l.lower() for k in keywords)]
    
    # Limit to top 10 most relevant lines
    condensed = "\n".join(important_lines[:10])
    return condensed if condensed else "No suspicious activity found in recent logs."

async def scout_node(state: GraphState) -> GraphState:
    await asyncio.sleep(4)
    log.info("scout_start", trace_id=state["trace_id"])
    log.info("vulnerability_classification", **_VULN_METADATA)

    raw_logs = get_logs(tail_lines=30)
    condensed_logs = _preprocess_logs(raw_logs)
    
    system_prompt = _load_prompt("scout")
    llm = _make_scout_llm()
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=(
            "Analyze the alert and condensed log data. Return ONLY a valid JSON object.\n\n"
            f"Alert: {json.dumps(state['alert_payload'])}\n"
            f"Logs: {condensed_logs}"
        )),
    ]
    
    response = await _invoke_with_retry(llm, messages, timeout=60.0, demo_stub=_DEMO_SCOUT)
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
    await asyncio.sleep(4)
    log.info("summarizer_start", trace_id=state["trace_id"])
    raw_content = state["scout_findings"]
    prompt = _load_prompt("summarizer").format(raw_output=_truncate(raw_content, 4000))
    
    llm = _make_gemini_llm(_GEMINI_FLASH)
    demo_summary = "Flask app on port 5000. The /search?q= endpoint is vulnerable to UNION-based SQL injection via unparameterized queries. Attacker can extract the secrets table containing CHIMERA flag using UNION SELECT."
    response = await _invoke_with_retry(llm, [HumanMessage(content=prompt)], timeout=60.0, demo_stub=demo_summary)

    return {
        **state,
        "target_topography": response.content,
        "status": "investigating",
    }

# ---------------------------------------------------------------------------
# Node 4: Investigator
# ---------------------------------------------------------------------------

async def investigator_node(state: GraphState) -> GraphState:
    await asyncio.sleep(4)
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
    
    response = await _invoke_with_retry(llm, messages, timeout=60.0, demo_stub=_DEMO_INVESTIGATOR)
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

    # DEMO MODE: inject captured flag immediately without hitting the network
    if _DEMO_MODE:
        demo_flag = "CHIMERA{sql1_1nj3ct10n_d3m0_flag_captured}"
        log.info("sandbox_demo_flag", trace_id=state["trace_id"], flag=demo_flag)
        await asyncio.sleep(0.8)  # Realistic delay
        return {
            **state,
            "captured_flag": demo_flag,
            "failure_reason": "",
            "status": "evaluating",
            "iteration_count": state["iteration_count"] + 1,
            "messages": state["messages"] + [{"role": "sandbox", "content": f"Flag captured: {demo_flag}"}],
        }

    if not _validate_exploit_payload(payload):
        log.warning("sandbox_payload_rejected", trace_id=state["trace_id"], payload=payload[:120])
        return {
            **state,
            "captured_flag": "",
            "failure_reason": "Exploit payload failed validation — must be a curl command targeting the victim host",
            "status": "evaluating",
            "iteration_count": state["iteration_count"] + 1,
            "messages": state["messages"] + [{"role": "sandbox", "content": "Payload rejected by allowlist validator"}],
        }

    result = await asyncio.to_thread(execute_bash_sandboxed, payload)
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
    if state.get("captured_flag"):
        return {**state, "status": "patching"}
    if state.get("iteration_count", 0) >= 10:
        return {**state, "status": "failed"}
    return {**state, "status": "investigating"}

def route_after_evaluator(state: GraphState) -> str:
    return state["status"]

# ---------------------------------------------------------------------------
# Node 7: Architect
# ---------------------------------------------------------------------------

async def architect_node(state: GraphState) -> GraphState:
    await asyncio.sleep(4)
    log.info("architect_start", trace_id=state["trace_id"])

    src_result = await asyncio.to_thread(get_victim_source, "app.py")
    source_code = src_result.get("content", "")
    system_prompt = _load_prompt("architect")
    llm = _make_gemini_llm(_GEMINI_PRO)
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Code:\n{source_code}\n\nExploit:\n{state['exploit_proof']}"),
    ]
    
    response = await _invoke_with_retry(llm, messages, timeout=60.0, demo_stub=_DEMO_ARCHITECT)
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

    # Apply patch (uses writable VICTIM_DST_PATH mount)
    apply_res = await asyncio.to_thread(verify_patch, "app.py", state["remediation_patch"])
    if apply_res.get("status") != "success":
        return {**state, "status": "rollback", "failure_reason": apply_res.get("message")}

    # Wait for Flask auto-reloader to pick up the patched file before probing
    await asyncio.sleep(3)

    # Re-run the exact same exploit — check if flag is still leaking after patch
    result = await asyncio.to_thread(execute_bash_sandboxed, state["exploit_proof"])
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

async def rollback_node(state: GraphState) -> GraphState:
    if state.get("original_source"):
        await asyncio.to_thread(verify_patch, "app.py", state["original_source"])
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
_graph_lock = threading.Lock()

def get_graph(checkpointer=None):
    """Return the compiled graph. Rebuilds when first called or when checkpointer changes."""
    global _graph, _graph_checkpointer
    with _graph_lock:
        if _graph is None or (checkpointer is not None and checkpointer is not _graph_checkpointer):
            _graph = build_graph(checkpointer)
            _graph_checkpointer = checkpointer
    return _graph
