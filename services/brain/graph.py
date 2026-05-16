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
import structlog
from tracing import trace_node_enter, trace_node_exit, trace_node_error
from metrics import record_iteration

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

# Local imports
from tools.security_tools import (
    get_logs,
    execute_bash_in_sandbox as execute_bash_sandboxed,
    verify_patch,
    run_http_probe,
    get_victim_source,
)
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

# Correct model names for the Groq library
_GROQ_FAST_MODEL = "llama-3.1-8b-instant"
_GROQ_PRO_MODEL  = "llama-3.3-70b-versatile"

def _make_scout_llm():
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=_GROQ_FAST_MODEL,
        groq_api_key=os.environ["GROQ_API_KEY"],
        temperature=0,
    )

def _make_investigator_llm():
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=_GROQ_FAST_MODEL,
        groq_api_key=os.environ["GROQ_API_KEY"],
        temperature=0,
    )

def _make_architect_llm():
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=_GROQ_PRO_MODEL,
        groq_api_key=os.environ["GROQ_API_KEY"],
        temperature=0,
    )

# ---------------------------------------------------------------------------
# Demo-mode stubs — realistic hardcoded outputs for when quotas are exhausted
# ---------------------------------------------------------------------------
_DEMO_SCOUT = """{
  "vulnerability_type": "SQL Injection",
  "affected_endpoints": ["/search", "/login", "/api/users"],
  "topography_summary": "The victim app exposes a Flask REST API on port 5000. Log analysis reveals unparameterized SQL queries in the /search route via the 'q' parameter.",
  "recommended_approach": "Use a UNION-based SQL injection payload on /search?q= to retrieve the contents of the secrets table."
}"""

_DEMO_INVESTIGATOR = """{
  "hypothesis": "The /search endpoint concatenates user input directly into a SQL query. A UNION injection can pivot to the secrets table using the correct 4-column schema.",
  "exploit_payload": "curl -s 'http://chimera-victim-1:5000/search?q=%27+UNION+SELECT+1%2Cvalue%2C3%2C4+FROM+secrets+WHERE+key%3D%27flag%27--'",
  "reasoning_steps": ["Identify vulnerable endpoint", "Determine products table has 4 columns", "Use key/value column names from secrets table", "URL-encode for curl"],
  "confidence_score": 0.95
}"""

_DEMO_ARCHITECT = """{
  "patched_content": "from flask import Flask, request, jsonify\\nimport sqlite3, os\\napp = Flask(__name__)\\nDB_PATH = os.getenv('DB_PATH', '/data/victim.db')\\n\\ndef get_db():\\n    conn = sqlite3.connect(DB_PATH)\\n    conn.row_factory = sqlite3.Row\\n    return conn\\n\\n@app.route('/search')\\ndef search():\\n    q = request.args.get('q', '')\\n    conn = get_db()\\n    rows = conn.execute('SELECT * FROM products WHERE name LIKE ?', (f'%{q}%',)).fetchall()\\n    conn.close()\\n    return jsonify([dict(r) for r in rows])\\n\\nif __name__ == '__main__':\\n    app.run(host='0.0.0.0', port=5000)\\n",
  "explanation": "Replaced string concatenation in the SQL query with a parameterized query using placeholders."
}"""

class _MockResponse:
    def __init__(self, content): self.content = content

async def _demo_invoke(stub: str) -> _MockResponse:
    await asyncio.sleep(1.2)
    return _MockResponse(stub)

# ---------------------------------------------------------------------------
# Resilient LLM invoke: tries real LLMs then falls back to demo mode
# ---------------------------------------------------------------------------
_QUOTA_ERRORS = ("429", "quota", "rate_limit", "too many requests", "resource_exhausted", "404", "not_found")

def _is_quota_or_model_error(err: str) -> bool:
    low = err.lower()
    return any(k in low for k in _QUOTA_ERRORS)

async def _invoke_with_retry(llm, messages, timeout=60.0, max_retries=2, demo_stub: str | None = None):
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
                    log.warning("llm_rate_limit_retry", attempt=attempt+1, wait_s=delay, error=err_str[:120])
                    await asyncio.sleep(delay)
                    delay *= 2
                else: break
            else: raise
    
    if demo_stub:
        log.warning("llm_quota_fallback_to_demo", error=(last_err or "")[:120])
        return await _demo_invoke(demo_stub)
    raise RuntimeError(f"LLM call failed: {last_err}")

def _load_prompt(name: str) -> str:
    prompt_dir = Path(__file__).parent / "prompts"
    file_path = prompt_dir / f"{name}_prompt.txt"
    if not file_path.exists():
        raise FileNotFoundError(f"Required prompt file not found: {file_path}")
    return file_path.read_text(encoding="utf-8")

def _repair_json(s: str) -> str:
    in_string, escape_next, opens = False, False, []
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
    res = s + ('"' if in_string else "")
    while opens:
        res += opens.pop()
    return res

def _to_snake(s: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '_', s).lower()

def _parse_json_response(content: str, model_cls):
    clean = re.sub(r"```(?:json)?\s*", "", content).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match: raise ValueError(f"No JSON object found: {content[:200]}")
    json_str = match.group(0)
    try: data = json.loads(json_str, strict=False)
    except json.JSONDecodeError: data = json.loads(_repair_json(json_str), strict=False)

    def normalize_keys(obj):
        if isinstance(obj, dict): return {_to_snake(k): normalize_keys(v) for k, v in obj.items()}
        if isinstance(obj, list): return [normalize_keys(v) for v in obj]
        return obj

    data = normalize_keys(data)
    try: return model_cls.model_validate(data)
    except Exception:
        from collections import deque
        q = deque([v for v in data.values() if isinstance(v, dict)]) if isinstance(data, dict) else deque()
        while q:
            cand = q.popleft()
            try: return model_cls.model_validate(cand)
            except Exception: q.extend(v for v in cand.values() if isinstance(v, dict))
    raise ValueError(f"Could not parse {model_cls.__name__} from LLM response.")

def _truncate(text: str, max_chars: int = 2000) -> str:
    return text[:max_chars] + "\n...[TRUNCATED]" if len(text) > max_chars else text

# Allowlist of security tools the investigator may use in exploit payloads.
# Shell meta-characters (;&|`$<>\n) are blocked to prevent injection.
_EXPLOIT_ALLOW_RE = re.compile(
    r'\A(curl|nmap|gobuster|sqlmap|hydra|ffuf|nikto|wfuzz|searchsploit|dirb|enum4linux|smbclient)[ \t][^;&|`$<>\n]*\Z',
    re.ASCII,
)

# Flag format — override via FLAG_PATTERN env var for non-Chimera targets (e.g. HTB).
_FLAG_PATTERN = re.compile(
    os.getenv("FLAG_PATTERN", r"(?:HTB|CHIMERA)\{[^}]+\}"),
    re.IGNORECASE,
)

def _validate_exploit_payload(payload: str) -> bool:
    # \A/\Z anchors + shell meta-char exclusion prevents multiline/injection attacks.
    return bool(_EXPLOIT_ALLOW_RE.match(payload.strip()))

# ---------------------------------------------------------------------------
# Node 1: Ingress
# ---------------------------------------------------------------------------
async def ingress_node(state: GraphState) -> GraphState:
    trace_id = state.get("trace_id") or str(uuid.uuid4())
    start = trace_node_enter(trace_id, "ingress", dict(state))
    raw_target = state.get("alert_payload", {}).get("target", "chimera-victim-1")
    target_ip = raw_target if isinstance(raw_target, str) else raw_target.get("host", "chimera-victim-1")
    log.info("ingress", trace_id=trace_id, target_ip=target_ip)
    result = {**state, "trace_id": trace_id, "target_ip": target_ip, "messages": [], "status": "scouting", "iteration_count": 0}
    trace_node_exit(trace_id, "ingress", dict(result), start)
    return result

# ---------------------------------------------------------------------------
# Node 2: Scout
# ---------------------------------------------------------------------------
def _preprocess_logs(log_data: dict) -> str:
    if log_data.get("status") != "success": return "No logs available."
    lines = log_data.get("log_lines", [])
    keywords = ["union", "select", "error", "syntax", "sqlite", "500", "403"]
    imp = [l for line in lines if (l := line.strip()) and any(k in l.lower() for k in keywords)]
    return "\n".join(imp[:10]) if imp else "No suspicious activity found."

async def scout_node(state: GraphState) -> GraphState:
    start = trace_node_enter(state["trace_id"], "scout", dict(state))
    await asyncio.sleep(4)
    target_ip = state.get("target_ip", "chimera-victim-1")
    log.info("scout_start", trace_id=state["trace_id"], target_ip=target_ip)
    try:
        # Always run nmap for service discovery against the target.
        nmap_result = await asyncio.to_thread(
            execute_bash_sandboxed,
            f"nmap -sV --open -T4 {target_ip}"
        )
        nmap_output = _truncate(nmap_result.get("stdout", "nmap produced no output"), 3000)

        # For the internal victim, supplement with log analysis.
        log_context = ""
        if "chimera-victim" in target_ip:
            log_context = f"\nAccess Logs:\n{_preprocess_logs(get_logs(tail_lines=30))}"

        recon_summary = f"Nmap scan of {target_ip}:\n{nmap_output}{log_context}"

        llm = None if _DEMO_MODE else _make_scout_llm()
        messages = [
            SystemMessage(content=_load_prompt("scout")),
            HumanMessage(content=f"Alert: {json.dumps(state['alert_payload'])}\nRecon:\n{recon_summary}"),
        ]
        resp = await _invoke_with_retry(llm, messages, demo_stub=_DEMO_SCOUT)
        out = _parse_json_response(resp.content, ScoutOutput)
        result = {**state, "target_topography": out.topography_summary, "current_hypothesis": out.recommended_approach,
                "scout_findings": out.model_dump_json(), "status": "summarizing"}
        trace_node_exit(state["trace_id"], "scout", dict(result), start)
        return result
    except Exception as exc:
        trace_node_error(state["trace_id"], "scout", dict(state), exc)
        raise

# ---------------------------------------------------------------------------
# Node 3: Summarizer
# ---------------------------------------------------------------------------
async def summarizer_node(state: GraphState) -> GraphState:
    start = trace_node_enter(state["trace_id"], "summarizer", dict(state))
    await asyncio.sleep(4)
    log.info("summarizer_start", trace_id=state["trace_id"])
    try:
        prompt = _load_prompt("summarizer").format(raw_output=_truncate(state["scout_findings"], 4000))
        llm = None if _DEMO_MODE else _make_scout_llm()
        resp = await _invoke_with_retry(llm, [HumanMessage(content=prompt)], demo_stub="Vulnerable Flask app on port 5000.")
        result = {**state, "target_topography": resp.content, "status": "investigating"}
        trace_node_exit(state["trace_id"], "summarizer", dict(result), start)
        return result
    except Exception as exc:
        trace_node_error(state["trace_id"], "summarizer", dict(state), exc)
        raise

# ---------------------------------------------------------------------------
# Node 4: Investigator
# ---------------------------------------------------------------------------
async def investigator_node(state: GraphState) -> GraphState:
    start = trace_node_enter(state["trace_id"], "investigator", dict(state))
    await asyncio.sleep(4)
    log.info("investigator_start", trace_id=state["trace_id"], iter=state["iteration_count"])
    try:
        target_ip = state.get("target_ip", "chimera-victim-1")
        context = f"Target: {target_ip}\nTopography: {state['target_topography']}\n"
        if state.get("failure_reason"): context += f"Last Failure: {state['failure_reason']}\n"
        llm = None if _DEMO_MODE else _make_investigator_llm()
        messages = [
            SystemMessage(content=_load_prompt("investigator") + "\n\nIMPORTANT: Return ONLY a valid JSON object."),
            HumanMessage(content=context),
        ]
        resp = await _invoke_with_retry(llm, messages, demo_stub=_DEMO_INVESTIGATOR)
        out = _parse_json_response(resp.content, InvestigatorOutput)
        result = {**state, "exploit_proof": out.exploit_payload, "current_hypothesis": out.hypothesis, "status": "sandbox_running"}
        trace_node_exit(state["trace_id"], "investigator", dict(result), start)
        return result
    except Exception as exc:
        trace_node_error(state["trace_id"], "investigator", dict(state), exc)
        raise

# ---------------------------------------------------------------------------
# Node 5: Sandbox
# ---------------------------------------------------------------------------
async def sandbox_node(state: GraphState) -> GraphState:
    start = trace_node_enter(state["trace_id"], "sandbox", dict(state))
    payload = state["exploit_proof"]
    log.info("sandbox_start", trace_id=state["trace_id"])
    if not _validate_exploit_payload(payload):
        result = {**state, "captured_flag": "", "failure_reason": "Payload invalid", "status": "evaluating", "iteration_count": state["iteration_count"]+1}
        trace_node_exit(state["trace_id"], "sandbox", dict(result), start)
        return result

    exec_result = await asyncio.to_thread(execute_bash_sandboxed, payload)
    output = exec_result.get("stdout", "") or exec_result.get("stderr", "")
    log.info("sandbox_output", trace_id=state["trace_id"], output_preview=output[:300])
    match = _FLAG_PATTERN.search(output)
    flag = match.group(0) if match else ""
    failure_reason = f"Flag not found. Command output: {output[:500]}" if not flag else ""
    result = {**state, "captured_flag": flag, "failure_reason": failure_reason,
            "status": "evaluating", "iteration_count": state["iteration_count"]+1}
    trace_node_exit(state["trace_id"], "sandbox", dict(result), start)
    return result

# ---------------------------------------------------------------------------
# Routing & Termination Nodes
# ---------------------------------------------------------------------------
def evaluator_node(state: GraphState) -> GraphState:
    start = trace_node_enter(state["trace_id"], "evaluator", dict(state))
    if state.get("captured_flag"): result = {**state, "status": "patching"}
    elif state.get("iteration_count", 0) >= 10: result = {**state, "status": "failed"}
    else: result = {**state, "status": "investigating"}
    trace_node_exit(state["trace_id"], "evaluator", dict(result), start)
    return result

async def architect_node(state: GraphState) -> GraphState:
    start = trace_node_enter(state["trace_id"], "architect", dict(state))
    await asyncio.sleep(4)
    log.info("architect_start", trace_id=state["trace_id"])
    try:
        src = (await asyncio.to_thread(get_victim_source, "app.py")).get("content", "")
        messages = [SystemMessage(content=_load_prompt("architect")), HumanMessage(content=f"Code:\n{src}\nExploit:\n{state['exploit_proof']}")]
        llm = None if _DEMO_MODE else _make_architect_llm()
        resp = await _invoke_with_retry(llm, messages, demo_stub=_DEMO_ARCHITECT)
        out = _parse_json_response(resp.content, ArchitectOutput)
        result = {**state, "remediation_patch": out.patched_content, "original_source": src, "status": "awaiting_approval"}
        trace_node_exit(state["trace_id"], "architect", dict(result), start)
        return result
    except Exception as exc:
        trace_node_error(state["trace_id"], "architect", dict(state), exc)
        raise

def human_approval_node(state: GraphState) -> GraphState:
    trace_node_enter(state["trace_id"], "human_approval", dict(state))
    return state

async def verifier_node(state: GraphState) -> GraphState:
    start = trace_node_enter(state["trace_id"], "verifier", dict(state))
    log.info("verifier_start", trace_id=state["trace_id"])
    
    try:
        # Apply patch
        apply_res = await asyncio.to_thread(verify_patch, "app.py", state["remediation_patch"])
        if apply_res.get("status") != "success":
            result = {**state, "status": "rollback", "failure_reason": f"Apply failed: {apply_res.get('message')}"}
            trace_node_exit(state["trace_id"], "verifier", dict(result), start)
            return result

        await asyncio.sleep(3) # Wait for reload

        # Verification Probe
        exec_result = await asyncio.to_thread(execute_bash_sandboxed, state["exploit_proof"])
        
        # CRITICAL: Treat tool errors as verification failure
        if exec_result.get("status") == "error":
            result = {**state, "status": "rollback", "failure_reason": f"Verification tool error: {exec_result.get('message')}"}
            trace_node_exit(state["trace_id"], "verifier", dict(result), start)
            return result

        output = exec_result.get("stdout", "")
        flag_still_present = bool(_FLAG_PATTERN.search(output))
        
        if flag_still_present:
            result = {**state, "status": "rollback", "failure_reason": "Patch did not block exploit — flag still visible"}
        else:
            result = {**state, "status": "resolved"}
            
        trace_node_exit(state["trace_id"], "verifier", dict(result), start)
        return result
    except Exception as exc:
        trace_node_error(state["trace_id"], "verifier", dict(state), exc)
        raise

async def rollback_node(state: GraphState) -> GraphState:
    start = trace_node_enter(state["trace_id"], "rollback", dict(state))
    if state.get("original_source"): await asyncio.to_thread(verify_patch, "app.py", state["original_source"])
    result = {**state, "status": "failed"}
    trace_node_exit(state["trace_id"], "rollback", dict(result), start)
    return result

# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------
def build_graph(checkpointer=None):
    b = StateGraph(GraphState)
    for n in ["ingress","scout","summarizer","investigator","sandbox"]: b.add_node(n, globals()[f"{n}_node"])
    b.add_node("evaluator", evaluator_node); b.add_node("architect", architect_node); b.add_node("human_approval", human_approval_node)
    b.add_node("verifier", verifier_node); b.add_node("rollback", rollback_node)
    b.set_entry_point("ingress")
    b.add_edge("ingress", "scout"); b.add_edge("scout", "summarizer"); b.add_edge("summarizer", "investigator"); b.add_edge("investigator", "sandbox"); b.add_edge("sandbox", "evaluator")
    b.add_conditional_edges("evaluator", lambda x: x["status"], {"investigating": "investigator", "patching": "architect", "failed": END})
    b.add_edge("architect", "human_approval")
    b.add_conditional_edges("human_approval", lambda x: "verifier" if x.get("human_approved") else END, {"verifier": "verifier", END: END})
    b.add_conditional_edges("verifier", lambda x: x["status"], {"resolved": END, "rollback": "rollback"})
    b.add_edge("rollback", END)
    return b.compile(checkpointer=checkpointer, interrupt_before=["human_approval"])

_graph, _lock = None, threading.Lock()
def get_graph(checkpointer=None):
    global _graph; 
    with _lock:
        if _graph is None: _graph = build_graph(checkpointer)
    return _graph
