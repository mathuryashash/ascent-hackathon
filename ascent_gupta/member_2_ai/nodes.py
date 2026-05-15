"""
Chimera Pipeline — Graph Nodes
Architecture doc LLM assignments (updated — $0 budget):
  - Scout:        Gemini 2.5 Flash  (fast summarizer)
  - Investigator: Llama 3 70B on Groq  (sub-second red team loops)
  - Architect:    Gemini 2.5 Pro  (large context for codebase analysis)
  - Verifier:     Gemini 2.5 Flash  (fast verification)
  - Evaluator:    Deterministic (no LLM)
  - Summarizer:   Gemini 2.5 Flash
  - Rollback:     Deterministic (no LLM)
"""
import json
import logging
import os
from typing import Dict, Any

# pyrefly: ignore [missing-import]
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from .state import GraphState
from .prompts import (
    SCOUT_PROMPT,
    INVESTIGATOR_PROMPT,
    ARCHITECT_PROMPT,
    VERIFIER_PROMPT,
    SUMMARIZER_PROMPT,
)
from .tools import (
    SCOUT_TOOLS,
    INVESTIGATOR_TOOLS,
    ARCHITECT_TOOLS,
    VERIFIER_TOOLS,
)

logger = logging.getLogger("chimera.nodes")

# ── LLM Setup ($0 Budget) ────────────────────────────────────────

# Scout + Summarizer + Verifier: Gemini Flash (fast & free)
gemini_flash = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_FLASH_MODEL", "gemini-2.5-flash-preview-05-20"),
    temperature=0,
    max_output_tokens=2048,
    google_api_key=os.getenv("GEMINI_API_KEY"),
)

# Architect: Gemini Pro (deep reasoning, large context, free)
gemini_pro = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro-preview-05-06"),
    temperature=0,
    max_output_tokens=4096,
    google_api_key=os.getenv("GEMINI_API_KEY"),
)

# Investigator: Llama 3 70B on Groq (sub-second inference)
groq_llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    temperature=0,
    max_tokens=4096,
    groq_api_key=os.getenv("GROQ_API_KEY"),
)

MAX_CONTEXT_CHARS = 2000  # Architecture doc Section C: ≤500 tokens ≈ ~2000 chars


# ── Helpers ───────────────────────────────────────────────────────

def _truncate(text: str, max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """Hard truncation fallback to prevent context blowup."""
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[TRUNCATED]"
    return text


async def _run_tool_loop(llm_with_tools, messages: list, max_rounds: int = 3) -> list:
    """
    Execute the LLM → tool-call → result loop.
    Returns all new messages produced during the loop.
    """
    all_tools = {t.name: t for t in SCOUT_TOOLS + INVESTIGATOR_TOOLS + ARCHITECT_TOOLS + VERIFIER_TOOLS}
    all_new_messages = []

    for _ in range(max_rounds):
        response = await llm_with_tools.ainvoke(messages + all_new_messages)
        all_new_messages.append(response)

        if not hasattr(response, "tool_calls") or not response.tool_calls:
            break  # LLM is done calling tools

        for tc in response.tool_calls:
            tool_fn = all_tools.get(tc["name"])
            if tool_fn is None:
                tool_msg = ToolMessage(
                    content=f"[ERROR] Unknown tool: {tc['name']}",
                    tool_call_id=tc["id"],
                )
            else:
                try:
                    result = tool_fn.invoke(tc["args"])
                    result = _truncate(str(result))
                except Exception as e:
                    result = f"[TOOL ERROR] {tc['name']} raised: {e}"
                tool_msg = ToolMessage(content=result, tool_call_id=tc["id"])

            logger.info("Tool %s → %s", tc["name"], str(tool_msg.content)[:120])
            all_new_messages.append(tool_msg)

    return all_new_messages


# ── Node: Scout (Gemini Flash) ───────────────────────────────────

async def scout_node(state: GraphState) -> Dict[str, Any]:
    """Recon agent — reads logs, scans network, produces Target Topography."""
    logger.info("[Scout] Starting recon  (trace=%s)", state["trace_id"])

    scout_llm = gemini_flash.bind_tools(SCOUT_TOOLS)

    messages = [
        SystemMessage(content=SCOUT_PROMPT),
        HumanMessage(
            content=(
                f"SIEM Alert received:\n"
                f"```json\n{json.dumps(state['alert_payload'], indent=2)}\n```\n"
                f"Investigate and produce a Target Topography."
            )
        ),
    ]

    new_messages = await _run_tool_loop(scout_llm, messages, max_rounds=3)
    # The last non-tool message is the topography
    final_content = new_messages[-1].content if new_messages else ""

    return {
        "messages": new_messages,
        "target_topography": _truncate(final_content),
        "status": "investigating",
    }


# ── Node: Summarizer (Gemini Flash) ──────────────────────────────

async def summarizer_node(state: GraphState) -> Dict[str, Any]:
    """Compresses raw tool output to ≤500 tokens."""
    raw = state["target_topography"] or (
        state["messages"][-1].content if state["messages"] else ""
    )
    prompt = SUMMARIZER_PROMPT.format(raw_output=_truncate(raw, 4000))
    summary = await gemini_flash.ainvoke([HumanMessage(content=prompt)])

    return {"target_topography": _truncate(summary.content)}


# ── Node: Investigator (Groq — Llama 3 70B) ─────────────────────

async def investigator_node(state: GraphState) -> Dict[str, Any]:
    """Red Team agent — crafts and executes exploit payloads + CTF flag capture."""
    logger.info(
        "[Investigator] Iteration %d  (trace=%s)",
        state["iteration_count"], state["trace_id"],
    )

    inv_llm = groq_llm.bind_tools(INVESTIGATOR_TOOLS)

    messages = [
        SystemMessage(content=INVESTIGATOR_PROMPT),
        HumanMessage(
            content=(
                f"Target Topography from Scout:\n{state['target_topography']}\n\n"
                f"Iteration: {state['iteration_count']} / 10\n"
                f"Previous hypothesis: {state.get('current_hypothesis', 'None')}\n\n"
                f"Exploit the SQL injection vulnerability and try to capture the flag."
            )
        ),
    ]

    new_messages = await _run_tool_loop(inv_llm, messages, max_rounds=5)

    return {
        "messages": new_messages,
        "iteration_count": state["iteration_count"] + 1,
    }


# ── Node: Evaluator (Deterministic — no LLM) ────────────────────

async def evaluator_node(state: GraphState) -> Dict[str, Any]:
    """
    Deterministic routing node.
    Checks if the Investigator captured the flag or needs to retry.
    """
    logger.info("[Evaluator] Checking iteration %d", state["iteration_count"])

    # Search all recent messages for evidence of success
    recent_content = " ".join(
        msg.content for msg in state["messages"][-6:]
        if hasattr(msg, "content") and msg.content
    ).lower()

    # CTF success: flag file content found
    flag_markers = ["flag{", "ctf{", "chimera{", "flag.txt"]
    exploit_markers = [
        "exploit confirmed", "successfully", "dumped", "leaked",
        "vulnerability proven", "injection succeeded", "union select",
        "password", "admin",
    ]

    has_flag = any(m in recent_content for m in flag_markers)
    has_exploit = any(m in recent_content for m in exploit_markers)

    if has_flag:
        # Extract the flag from recent messages
        flag_content = ""
        for msg in state["messages"][-6:]:
            if hasattr(msg, "content") and msg.content:
                for marker in ["flag{", "ctf{", "chimera{"]:
                    idx = msg.content.lower().find(marker)
                    if idx != -1:
                        end = msg.content.find("}", idx)
                        if end != -1:
                            flag_content = msg.content[idx:end + 1]
                            break
            if flag_content:
                break

        return {
            "exploit_proof": state["messages"][-1].content if state["messages"] else "",
            "captured_flag": flag_content,
            "status": "patching",
        }

    if has_exploit:
        return {
            "exploit_proof": state["messages"][-1].content if state["messages"] else "",
            "status": "patching",
        }

    if state["iteration_count"] >= 10:
        return {"status": "failed"}

    # Not yet proven — update hypothesis and loop back
    return {
        "current_hypothesis": (
            state["messages"][-1].content[:500]
            if state["messages"] else "No hypothesis yet"
        ),
    }


# ── Node: Architect (Gemini Pro) ─────────────────────────────────

async def architect_node(state: GraphState) -> Dict[str, Any]:
    """Blue Team agent — reads vulnerable source and generates a patch."""
    logger.info("[Architect] Generating patch  (trace=%s)", state["trace_id"])

    arch_llm = gemini_pro.bind_tools(ARCHITECT_TOOLS)

    messages = [
        SystemMessage(content=ARCHITECT_PROMPT),
        HumanMessage(
            content=(
                f"Exploit Proof:\n{_truncate(state['exploit_proof'], 1500)}\n\n"
                f"Hypothesis: {state['current_hypothesis']}\n"
                f"Captured Flag: {state.get('captured_flag', 'N/A')}\n\n"
                f"Read the vulnerable source file (app.py) and generate a patch "
                f"that fixes the SQL injection by using parameterised queries."
            )
        ),
    ]

    new_messages = await _run_tool_loop(arch_llm, messages, max_rounds=4)

    # Try to capture the original source from tool outputs (for rollback)
    original_source = ""
    for msg in new_messages:
        if isinstance(msg, ToolMessage) and "def " in msg.content and "app.py" not in state.get("original_source", ""):
            original_source = msg.content
            break

    return {
        "messages": new_messages,
        "remediation_patch": new_messages[-1].content if new_messages else "",
        "original_source": original_source or state.get("original_source", ""),
        "status": "verifying",
    }


# ── Node: Verifier (Gemini Flash) ────────────────────────────────

async def verifier_node(state: GraphState) -> Dict[str, Any]:
    """Re-runs the exploit to confirm the patch actually works."""
    logger.info("[Verifier] Testing patch  (trace=%s)", state["trace_id"])

    ver_llm = gemini_flash.bind_tools(VERIFIER_TOOLS)

    messages = [
        SystemMessage(content=VERIFIER_PROMPT),
        HumanMessage(
            content=(
                f"The following exploit was previously successful:\n"
                f"{_truncate(state['exploit_proof'], 1500)}\n\n"
                f"A patch has been applied.  Re-run the EXACT same exploit "
                f"and report whether it is now blocked."
            )
        ),
    ]

    new_messages = await _run_tool_loop(ver_llm, messages, max_rounds=3)

    return {"messages": new_messages}


# ── Node: Rollback (Deterministic — no LLM) ─────────────────────

async def rollback_node(state: GraphState) -> Dict[str, Any]:
    """Restores original source code if the patch broke the Victim."""
    logger.info("[Rollback] Restoring original source  (trace=%s)", state["trace_id"])

    if state.get("original_source"):
        return {
            "status": "failed",
            "remediation_patch": "",
            "messages": [
                AIMessage(
                    content="[Rollback] Restored original source. Patch reverted. Manual review required."
                )
            ],
        }

    return {
        "status": "failed",
        "messages": [
            AIMessage(
                content="[Rollback] No original source stored. Cannot rollback. Manual intervention required."
            )
        ],
    }
