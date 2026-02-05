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
"""
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming user messages."""
    thread_id = cl.user_session.get("thread_id", "default")

    # Show thinking indicator
    msg = cl.Message(content="")
    await msg.send()

    try:
        # Run the agent via FastAPI
        async with httpx.AsyncClient(timeout=120.0) as client:
            api_response = await client.post(
                f"{_API_BASE_URL}/chat",
                json={"message": message.content, "thread_id": thread_id},
            )
        api_response.raise_for_status()
        response_payload = api_response.json()
        response = response_payload.get("response", "")
        reasoning_trace = response_payload.get("reasoning_trace", [])

        # Render reasoning trace as expandable steps.
        # Use only generic labels as step names so Chainlit doesn't try
        # to fetch a unique avatar per tool name (which causes 400 spam).
        if reasoning_trace:
            tool_steps = [s for s in reasoning_trace if s.get("step") in {"tool_call", "tool_result"}]
            llm_steps = [s for s in reasoning_trace if s.get("step") == "llm_decision"]
            other_steps = [
                s
                for s in reasoning_trace
                if s.get("step") not in {"tool_call", "tool_result", "llm_decision"}
            ]

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

        # Update the message with the response
        msg.content = response
        await msg.update()

    except Exception as e:
        msg.content = f"I encountered an error: {str(e)}\n\nPlease try again or rephrase your question."
        await msg.update()


@cl.on_stop
async def on_stop():
    """Handle chat stop."""
    pass
