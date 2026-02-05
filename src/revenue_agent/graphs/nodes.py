"""Graph nodes for the Revenue Leakage Agent."""

from datetime import datetime, timezone
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import interrupt

from revenue_agent.agents.prompts.system import SYSTEM_PROMPT
from revenue_agent.agents.revenue_agent import create_agent, get_tools
from revenue_agent.schemas.state import AgentState

# Tools that modify the sandbox and require explicit human approval
SANDBOX_TOOL_NAMES: frozenset[str] = frozenset({"apply_action", "rollback_action"})


def _now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str, max_len: int = 300) -> str:
    """Truncate text for trace previews."""
    if not text:
        return ""
    return text[:max_len] + ("..." if len(text) > max_len else "")


def agent_node(state: AgentState) -> AgentState:
    """Main agent node - decides what to do next."""
    messages = state["messages"]

    # Add system message if not present
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

    # Create agent and invoke
    agent = create_agent()
    response = agent.invoke(messages)

    # Build reasoning trace entry for this LLM decision
    trace_entry: dict[str, Any] = {
        "step": "llm_decision",
        "node": "agent",
        "timestamp": _now_iso(),
    }

    if response.tool_calls:
        trace_entry["tool_calls"] = [tc["name"] for tc in response.tool_calls]
        trace_entry["content_preview"] = None
    else:
        # Final response — keep full content, no truncation
        trace_entry["tool_calls"] = []
        trace_entry["content_preview"] = response.content or ""

    return {
        "messages": [response],
        "reasoning_trace": [trace_entry],
    }


def human_review_node(state: AgentState) -> AgentState:
    """Pause for human approval before executing sandbox-modifying tools.

    Uses LangGraph's interrupt() to pause the graph and wait for
    explicit human confirmation before applying or rolling back
    sandbox actions.
    """
    messages = state["messages"]
    last_message = messages[-1]

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"messages": [], "reasoning_trace": []}

    # Extract sandbox tool call details for the approval prompt
    sandbox_calls = [
        tc for tc in last_message.tool_calls
        if tc["name"] in SANDBOX_TOOL_NAMES
    ]

    approval_details = {
        "pending_tool_calls": [
            {"tool": tc["name"], "args": tc["args"]}
            for tc in sandbox_calls
        ],
        "message": "The agent wants to modify the sandbox. Please approve or reject.",
    }

    # Pause the graph — returns the value from Command(resume=...) when continued
    human_decision = interrupt(approval_details)

    if human_decision == "reject":
        # Create rejection ToolMessages for ALL tool calls so the LLM
        # receives a response for every pending call
        rejection_messages = [
            ToolMessage(
                content="Action rejected by the user. Do not retry without new explicit approval.",
                tool_call_id=tc["id"],
                name=tc["name"],
            )
            for tc in last_message.tool_calls
        ]
        return {
            "messages": rejection_messages,
            "reasoning_trace": [{
                "step": "human_review",
                "node": "human_review",
                "timestamp": _now_iso(),
                "content_preview": "User rejected the proposed action.",
                "is_error": False,
            }],
        }

    # Approved — continue to tool execution (no messages added, so the
    # AIMessage with tool_calls remains as the last message for tool_node)
    return {
        "messages": [],
        "reasoning_trace": [{
            "step": "human_review",
            "node": "human_review",
            "timestamp": _now_iso(),
            "content_preview": "User approved the proposed action.",
            "is_error": False,
        }],
    }


def tool_node(state: AgentState) -> AgentState:
    """Execute tool calls from the agent."""
    messages = state["messages"]
    last_message = messages[-1]

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return state

    tools = {tool.name: tool for tool in get_tools()}
    tool_messages: list[ToolMessage] = []
    trace_entries: list[dict[str, Any]] = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        # Trace: tool_call (before execution)
        trace_entries.append({
            "step": "tool_call",
            "node": "tools",
            "timestamp": _now_iso(),
            "tool": tool_name,
            "tool_args": tool_args,
        })

        if tool_name in tools:
            try:
                result = tools[tool_name].invoke(tool_args)
                result_str = str(result)
                tool_messages.append(
                    ToolMessage(
                        content=result_str,
                        tool_call_id=tool_call["id"],
                        name=tool_name,
                    )
                )
                # Trace: tool_result (success)
                trace_entries.append({
                    "step": "tool_result",
                    "node": "tools",
                    "timestamp": _now_iso(),
                    "tool": tool_name,
                    "content_preview": _truncate(result_str),
                    "is_error": False,
                })
            except Exception as e:
                error_str = f"Error executing {tool_name}: {str(e)}"
                tool_messages.append(
                    ToolMessage(
                        content=error_str,
                        tool_call_id=tool_call["id"],
                        name=tool_name,
                    )
                )
                # Trace: tool_result (error)
                trace_entries.append({
                    "step": "tool_result",
                    "node": "tools",
                    "timestamp": _now_iso(),
                    "tool": tool_name,
                    "content_preview": _truncate(error_str),
                    "is_error": True,
                })
        else:
            error_str = f"Unknown tool: {tool_name}"
            tool_messages.append(
                ToolMessage(
                    content=error_str,
                    tool_call_id=tool_call["id"],
                    name=tool_name,
                )
            )
            trace_entries.append({
                "step": "tool_result",
                "node": "tools",
                "timestamp": _now_iso(),
                "tool": tool_name,
                "content_preview": error_str,
                "is_error": True,
            })

    return {
        "messages": tool_messages,
        "reasoning_trace": trace_entries,
    }


def should_continue(state: AgentState) -> Literal["tools", "human_review", "end"]:
    """Determine if we should continue to tools, require human approval, or end."""
    messages = state["messages"]
    last_message = messages[-1]

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        # Route sandbox-modifying tool calls through human review
        if any(tc["name"] in SANDBOX_TOOL_NAMES for tc in last_message.tool_calls):
            return "human_review"
        return "tools"

    # Otherwise, end the conversation turn
    return "end"


def after_human_review(state: AgentState) -> Literal["tools", "agent"]:
    """Route after human review: to tools if approved, back to agent if rejected.

    When the user approves, no messages are added so the AIMessage with
    tool_calls is still the last message — route to tools for execution.
    When the user rejects, rejection ToolMessages are added — route back
    to agent so it can acknowledge the rejection.
    """
    messages = state["messages"]
    last_message = messages[-1] if messages else None

    # Rejection ToolMessages were added → route back to agent
    if isinstance(last_message, ToolMessage):
        return "agent"

    # Approved → proceed to tool execution
    return "tools"
