"""Main LangGraph graph for the Revenue Leakage Agent."""

from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from revenue_agent.graphs.nodes import agent_node, should_continue, tool_node
from revenue_agent.schemas.state import AgentState, create_initial_state
from revenue_agent.services.preprocessor import preprocess_message


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

class AgentResult:
    """Container for agent response + reasoning trace."""

    def __init__(self, response: str, reasoning_trace: list[dict[str, Any]]) -> None:
        self.response = response
        self.reasoning_trace = reasoning_trace


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def create_graph() -> StateGraph:
    """Create the Revenue Leakage Agent graph."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    # Set entry point
    workflow.set_entry_point("agent")

    # Add conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        },
    )

    # Tools always go back to agent
    workflow.add_edge("tools", "agent")

    return workflow


def compile_graph(checkpointer: MemorySaver | None = None):
    """Compile the graph with optional checkpointer."""
    workflow = create_graph()

    if checkpointer:
        return workflow.compile(checkpointer=checkpointer)

    return workflow.compile()


# Global checkpointer for conversation memory
_memory = MemorySaver()


def get_compiled_graph():
    """Get a compiled graph with memory checkpointer."""
    return compile_graph(_memory)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_messages_with_preprocessing(message: str) -> tuple[list, list[dict[str, Any]]]:
    """Build message list with optional pre-analysis context.

    Returns:
        Tuple of (messages, initial_trace_steps) — the trace captures the
        pre-analysis step so it appears in the reasoning trace.
    """
    _, analysis_context = preprocess_message(message)

    messages: list = []
    trace_steps: list[dict[str, Any]] = []

    # If we have pre-computed analysis, add it as context and log to trace
    if analysis_context:
        messages.append(SystemMessage(content=analysis_context))
        trace_steps.append({
            "step": "pre_analysis",
            "node": "preprocessor",
            "timestamp": _now_iso(),
            "content_preview": analysis_context[:300] + ("..." if len(analysis_context) > 300 else ""),
        })

    # Add the user's message
    messages.append(HumanMessage(content=message))

    return messages, trace_steps


def _build_input_state(messages: list, initial_trace: list[dict[str, Any]] | None = None) -> dict:
    return {
        "messages": messages,
        "pending_action": None,
        "needs_approval": False,
        "context": {},
        "reasoning_trace": initial_trace or [],
    }


def _extract_response_message(result: dict) -> str:
    result_messages = result.get("messages", [])
    for msg in reversed(result_messages):
        if hasattr(msg, "content") and msg.content and not hasattr(msg, "tool_calls"):
            return msg.content
        if hasattr(msg, "content") and hasattr(msg, "tool_calls") and not msg.tool_calls:
            return msg.content
    return "I apologize, but I couldn't generate a response. Please try again."


def _build_result(result: dict) -> AgentResult:
    """Extract response text and reasoning trace from graph result."""
    response = _extract_response_message(result)
    trace = result.get("reasoning_trace", [])
    return AgentResult(response=response, reasoning_trace=trace)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_agent(
    message: str,
    thread_id: str = "default",
) -> AgentResult:
    """Run the agent with a user message.

    This function:
    1. Runs Python preprocessing to detect plan IDs and compute analysis
    2. Injects analysis results as context for the LLM
    3. LLM interprets the pre-computed results and responds
    4. Returns response text together with the full reasoning trace

    Args:
        message: The user's message
        thread_id: Conversation thread ID for memory

    Returns:
        AgentResult with response text and reasoning_trace list.
    """
    graph = get_compiled_graph()

    config = {"configurable": {"thread_id": thread_id}}

    # Build messages with preprocessing (Python analysis runs HERE)
    messages, initial_trace = _build_messages_with_preprocessing(message)

    # Create input state — seed the trace with pre-analysis steps
    input_state = _build_input_state(messages, initial_trace)

    # Run the graph
    result = await graph.ainvoke(input_state, config)

    return _build_result(result)


def run_agent_sync(
    message: str,
    thread_id: str = "default",
) -> AgentResult:
    """Synchronous version of run_agent.

    Returns:
        AgentResult with response text and reasoning_trace list.
    """
    graph = get_compiled_graph()

    config = {"configurable": {"thread_id": thread_id}}

    # Build messages with preprocessing (Python analysis runs HERE)
    messages, initial_trace = _build_messages_with_preprocessing(message)

    input_state = _build_input_state(messages, initial_trace)

    result = graph.invoke(input_state, config)

    return _build_result(result)
