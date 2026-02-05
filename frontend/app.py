"""Chainlit frontend for the Revenue Leakage Agent."""

import json
import os

import chainlit as cl
import httpx

_API_BASE_URL = os.getenv("REVENUE_AGENT_API_URL", "http://localhost:8000/api")

# Fixed set of step names — Chainlit fetches an avatar per unique name,
# so we keep them generic to avoid hundreds of 400 avatar requests.
_STEP_LABELS: dict[str, str] = {
    "pre_analysis": "Pre-Analysis",
    "llm_decision": "LLM Decision",
    "human_review": "Human Review",
}


def _format_trace_step(step: dict) -> str:
    """Format a single reasoning trace step as readable markdown."""
    step_type = step.get("step", "unknown")
    parts: list[str] = []

    if step_type == "pre_analysis":
        parts.append("Ran deterministic Python analysis before LLM call.")
        if step.get("content_preview"):
            parts.append(f"\n```\n{step['content_preview']}\n```")

    elif step_type == "llm_decision":
        tool_calls = step.get("tool_calls", [])
        if tool_calls:
            parts.append(f"Decided to call: **{', '.join(tool_calls)}**")
        else:
            parts.append("Produced final response.")
            if step.get("content_preview"):
                parts.append(f"\n{step['content_preview']}")

    elif step_type == "human_review":
        parts.append(step.get("content_preview", "Human review step."))

    return "\n".join(parts) if parts else json.dumps(step, indent=2)


def _format_tool_steps(tool_steps: list[dict]) -> str:
    """Format all tool steps into one collapsible block."""
    if not tool_steps:
        return "No tools were called."

    chunks: list[str] = []
    for step in tool_steps:
        step_type = step.get("step", "unknown")
        tool = step.get("tool", "unknown")

        if step_type == "tool_call":
            args = step.get("tool_args", {})
            chunks.append(f"**Call**: `{tool}` with `{json.dumps(args, default=str)}`")
            continue

        if step_type == "tool_result":
            is_error = step.get("is_error", False)
            status = "Error" if is_error else "Success"
            chunks.append(f"**Result**: `{tool}` → {status}")
            if step.get("content_preview"):
                chunks.append(f"```\n{step['content_preview']}\n```")
            continue

    return "\n\n".join(chunks)


def _format_llm_steps(llm_steps: list[dict]) -> str:
    """Format all LLM decision steps into one collapsible block."""
    if not llm_steps:
        return "No LLM decisions recorded."

    chunks: list[str] = []
    for index, step in enumerate(llm_steps, start=1):
        tool_calls = step.get("tool_calls", [])
        if tool_calls:
            chunks.append(f"**Decision {index}**: Call tools → {', '.join(tool_calls)}")
            continue

        chunks.append(f"**Decision {index}**: Produced final response")
        if step.get("content_preview"):
            chunks.append(step["content_preview"])

    return "\n\n".join(chunks)


def _render_reasoning_trace(reasoning_trace: list[dict]) -> None:
    """Schedule rendering of reasoning trace steps as collapsible blocks.

    Returns a list of coroutines; caller should await them.
    """
    if not reasoning_trace:
        return []

    tool_steps = [s for s in reasoning_trace if s.get("step") in {"tool_call", "tool_result"}]
    llm_steps = [s for s in reasoning_trace if s.get("step") == "llm_decision"]
    other_steps = [
        s
        for s in reasoning_trace
        if s.get("step") not in {"tool_call", "tool_result", "llm_decision"}
    ]

    coros = []

    async def _render():
        for trace_step in other_steps:
            step_type = trace_step.get("step", "unknown")
            label = _STEP_LABELS.get(step_type, step_type)
            async with cl.Step(name=label) as step:
                step.output = _format_trace_step(trace_step)

        if llm_steps:
            async with cl.Step(name="LLM Decisions") as step:
                step.output = _format_llm_steps(llm_steps)

        if tool_steps:
            async with cl.Step(name="Tool Usage") as step:
                step.output = _format_tool_steps(tool_steps)

    return _render()


def _format_pending_actions(pending_actions: list[dict]) -> str:
    """Format pending sandbox actions for display in the approval prompt."""
    if not pending_actions:
        return ""
    lines = []
    for action in pending_actions:
        tool = action.get("tool", "unknown")
        args = action.get("args", {})
        lines.append(f"- **{tool}** with `{json.dumps(args, default=str)}`")
    return "\n".join(lines)

def _format_audit_log_table(entries: list[dict]) -> str:
    """Format audit log entries as a markdown table."""
    if not entries:
        return "No audit log entries found."

    rows = []
    for entry in entries:
        action = str(entry.get("action", ""))
        result_id = str(entry.get("result_id", ""))
        timestamp = str(entry.get("timestamp", ""))
        details = json.dumps(entry.get("details", {}), default=str)
        rows.append(f"| {action} | {result_id} | {timestamp} | `{details}` |")

    header = "| Action | Result ID | Timestamp | Details |"
    separator = "| --- | --- | --- | --- |"
    return "\n".join([header, separator, *rows])


async def _call_api(payload: dict) -> dict:
    """Call the agent API and return the JSON response."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{_API_BASE_URL}/chat", json=payload)
    resp.raise_for_status()
    return resp.json()


@cl.on_chat_start
async def on_chat_start():
    """Initialize a new chat session."""
    # Generate a unique thread ID for this session
    thread_id = cl.user_session.get("id")
    cl.user_session.set("thread_id", thread_id)

    # Send welcome message
    await cl.Message(
        content="""Welcome to the **Revenue Leakage Agent**! 

I'm an AI financial detective that helps investigate billing anomalies and revenue leakage issues.

**What I can do:**
- Investigate discrepancies between billing plans and invoices
- Identify missing invoices, overbilling, or underbilling
- Propose corrective actions (make-good invoices, credit memos, plan amendments)
- Apply approved actions to the sandbox

**Available Plans:**
- `P-12345` - Acme Corporation ($10,000/month USD)
- `P-67890` - Global Tech Ltd (€25,000/month EUR)
- `P-11111` - StartupXYZ Inc ($5,000/month USD)
- `P-22222` - Enterprise Solutions Co ($90,000/quarter USD)
- `P-33333` - British Innovations PLC (£15,000/month GBP)

**Try asking:**
- "Can you check if there are any revenue leakage issues with plan P-12345?"
- "Show me all invoices for Global Tech Ltd"
- "What's the status of plan P-67890?"

**Audit Log Viewer:**
- Open `/api/audit-log/view` in your browser
- Or type `/audit` in chat
"""
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming user messages."""
    thread_id = cl.user_session.get("thread_id", "default")
    normalized_text = message.content.strip().lower()

    if normalized_text in {"/audit", "/audit-log"}:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                audit_response = await client.get(f"{_API_BASE_URL}/audit-log")
            audit_response.raise_for_status()
            entries = audit_response.json()
        except Exception as e:
            await cl.Message(
                content=f"Unable to load audit log: {str(e)}"
            ).send()
            return

        await cl.Message(
            content=_format_audit_log_table(entries)
        ).send()
        return

    # Show thinking indicator
    msg = cl.Message(content="")
    await msg.send()

    try:
        response_payload = await _call_api(
            {"message": message.content, "thread_id": thread_id},
        )
        response = response_payload.get("response", "")
        reasoning_trace = response_payload.get("reasoning_trace", [])
        needs_approval = response_payload.get("needs_approval", False)
        pending_actions = response_payload.get("pending_actions", [])

        # Render reasoning trace as expandable steps
        render = _render_reasoning_trace(reasoning_trace)
        if render:
            await render

        if needs_approval:
            # Show agent response (if any) before the approval prompt
            if response:
                msg.content = response
                await msg.update()

            # Present approval prompt with action buttons
            actions_text = _format_pending_actions(pending_actions)
            res = await cl.AskActionMessage(
                content=(
                    f"**Sandbox modification requires your approval:**\n{actions_text}"
                ),
                actions=[
                    cl.Action(
                        name="approve",
                        value="approve",
                        label="Approve",
                    ),
                    cl.Action(
                        name="reject",
                        value="reject",
                        label="Reject",
                    ),
                ],
            ).send()

            # Process the user's decision
            if res:
                action_name = (
                    res.get("name") if isinstance(res, dict)
                    else getattr(res, "name", "reject")
                )
                is_approved = action_name == "approve"

                # Show processing indicator
                result_msg = cl.Message(content="")
                await result_msg.send()

                # Resume the agent graph
                resume_payload = await _call_api(
                    {"thread_id": thread_id, "approve": is_approved},
                )
                resume_response = resume_payload.get("response", "")
                resume_trace = resume_payload.get("reasoning_trace", [])

                # Render reasoning trace from the resume
                render = _render_reasoning_trace(resume_trace)
                if render:
                    await render

                result_msg.content = resume_response
                await result_msg.update()
            else:
                # Timeout — no action taken
                timeout_msg = cl.Message(
                    content="Approval timed out. The action was **not** applied."
                )
                await timeout_msg.send()
        else:
            # Normal response (no approval needed)
            msg.content = response
            await msg.update()

    except Exception as e:
        msg.content = f"I encountered an error: {str(e)}\n\nPlease try again or rephrase your question."
        await msg.update()


@cl.on_stop
async def on_stop():
    """Handle chat stop."""
    pass
