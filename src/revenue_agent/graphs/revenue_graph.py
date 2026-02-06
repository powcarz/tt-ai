"""Main LangGraph graph for the Revenue Leakage Agent."""

import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from revenue_agent.graphs.nodes import (
    after_human_review,
    agent_node,
    human_review_node,
    should_continue,
    tool_node,
)
from revenue_agent.schemas.state import AgentState, create_initial_state
from revenue_agent.services.approval_classifier import (
    ApprovalIntent,
    classify_approval_intent,
)
from revenue_agent.services.preprocessor import preprocess_message

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

class AgentResult:
    """Container for agent response + reasoning trace."""

    def __init__(
        self,
        response: str,
        reasoning_trace: list[dict[str, Any]],
        *,
        needs_approval: bool = False,
        pending_actions: list[dict[str, Any]] | None = None,
    ) -> None:
        self.response = response
        self.reasoning_trace = reasoning_trace
        self.needs_approval = needs_approval
        self.pending_actions = pending_actions or []


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def create_graph() -> StateGraph:
    """Create the Revenue Leakage Agent graph.

    Graph structure::

        ┌──────────┐
        │  agent   │ ← entry point
        └────┬─────┘
             │ should_continue
             ├─── "tools" ──────────► tools ──► agent (loop)
             ├─── "human_review" ──► human_review
             │                         │ after_human_review
             │                         ├── "tools" ──► tools ──► agent
             │                         └── "agent" ──► agent (rejection)
             └─── "end" ──────────► END
    """
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("tools", tool_node)

    # Set entry point
    workflow.set_entry_point("agent")

    # Conditional edges from agent
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "human_review": "human_review",
            "end": END,
        },
    )

    # After human review: approved → tools, rejected → agent
    workflow.add_conditional_edges(
        "human_review",
        after_human_review,
        {
            "tools": "tools",
            "agent": "agent",
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


def _extract_response_message(
    result: dict,
    *,
    allow_tool_calls: bool = False,
) -> str:
    """Extract the final response message from graph result.

    Args:
        result: The graph result state dict.
        allow_tool_calls: If True, also consider AIMessages that have
            pending tool_calls (used when the graph is interrupted
            before tool execution and the AIMessage may carry content).
    """
    result_messages = result.get("messages", [])
    for msg in reversed(result_messages):
        if not hasattr(msg, "content") or not msg.content:
            continue
        # Skip AIMessages with pending tool calls unless explicitly allowed
        if hasattr(msg, "tool_calls") and msg.tool_calls and not allow_tool_calls:
            continue
        return msg.content

    if allow_tool_calls:
        return ""  # Interrupted state — let the caller compose the response
    return "I apologize, but I couldn't generate a response. Please try again."


def _build_result(
    result: dict,
    *,
    needs_approval: bool = False,
    pending_actions: list[dict[str, Any]] | None = None,
) -> AgentResult:
    """Extract response text and reasoning trace from graph result."""
    response = _extract_response_message(result, allow_tool_calls=needs_approval)
    trace = result.get("reasoning_trace", [])
    return AgentResult(
        response=response,
        reasoning_trace=trace,
        needs_approval=needs_approval,
        pending_actions=pending_actions,
    )


async def _get_interrupt_details(graph, config: dict) -> list[dict[str, Any]] | None:
    """Check if the graph has a pending interrupt and extract action details.

    Returns:
        List of pending tool call dicts, or None if no interrupt is active.
    """
    try:
        state_snapshot = await graph.aget_state(config)
    except Exception:
        return None

    if not state_snapshot.next:
        return None

    pending_actions: list[dict[str, Any]] = []
    for task in getattr(state_snapshot, "tasks", []):
        for intr in getattr(task, "interrupts", []):
            value = getattr(intr, "value", None)
            if isinstance(value, dict):
                pending_actions.extend(value.get("pending_tool_calls", []))

    return pending_actions if pending_actions else None


async def run_agent(
    message: str,
    thread_id: str = "default",
) -> AgentResult:
    """Run the agent with a user message.

    This function:
    1. Clears any stale pending interrupt (auto-reject)
    2. Runs Python preprocessing to detect plan IDs and compute analysis
    3. Injects analysis results as context for the LLM
    4. LLM interprets the pre-computed results and responds
    5. If the graph pauses for human approval, returns needs_approval=True

    Args:
        message: The user's message
        thread_id: Conversation thread ID for memory

    Returns:
        AgentResult with response text, reasoning_trace, and approval status.
    """
    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # If there is a pending interrupt from a previous turn, classify the
    # incoming message to decide whether to approve, reject, or treat it
    # as an unrelated new query (auto-reject the stale interrupt first).
    existing_interrupt = await _get_interrupt_details(graph, config)
    if existing_interrupt:
        intent = await classify_approval_intent(message)
        logger.info(
            "Pending interrupt on thread %s — classified intent: %s",
            thread_id,
            intent.value,
        )

        if intent == ApprovalIntent.APPROVE:
            return await resume_agent(thread_id, approve=True)
        if intent == ApprovalIntent.REJECT:
            return await resume_agent(thread_id, approve=False)

        # NEW_QUERY — auto-reject the stale interrupt, then process below
        logger.info("New query while interrupt pending; auto-rejecting for thread %s", thread_id)
        await graph.ainvoke(Command(resume="reject"), config)

    # Build messages with preprocessing (Python analysis runs HERE)
    messages, initial_trace = _build_messages_with_preprocessing(message)

    # Create input state — seed the trace with pre-analysis steps
    input_state = _build_input_state(messages, initial_trace)

    # Run the graph
    result = await graph.ainvoke(input_state, config)

    # Check if the graph was interrupted (pending human approval)
    pending_actions = await _get_interrupt_details(graph, config)
    if pending_actions:
        # If the user's message already expressed approval (e.g. "go ahead",
        # "I like it"), auto-approve the interrupt so there is no redundant
        # second confirmation via buttons.
        intent = await classify_approval_intent(message)
        if intent == ApprovalIntent.APPROVE:
            logger.info(
                "User message already expresses approval — auto-approving "
                "interrupt on thread %s",
                thread_id,
            )
            return await resume_agent(thread_id, approve=True)

        logger.info("Graph interrupted — awaiting approval for %s", pending_actions)
        return _build_result(
            result,
            needs_approval=True,
            pending_actions=pending_actions,
        )

    return _build_result(result)


async def resume_agent(
    thread_id: str = "default",
    *,
    approve: bool = True,
) -> AgentResult:
    """Resume the agent after human approval or rejection.

    Args:
        thread_id: Conversation thread ID.
        approve: True to approve, False to reject the pending action.

    Returns:
        AgentResult with response text and reasoning trace.
    """
    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # Verify there is actually a pending interrupt
    pending = await _get_interrupt_details(graph, config)
    if not pending:
        return AgentResult(
            response="No pending action to approve or reject.",
            reasoning_trace=[],
        )

    decision = "approve" if approve else "reject"
    logger.info("Resuming thread %s with decision: %s", thread_id, decision)

    result = await graph.ainvoke(Command(resume=decision), config)

    # Check if the graph hit another interrupt (e.g. additional apply_action calls)
    new_pending = await _get_interrupt_details(graph, config)
    if new_pending:
        logger.info("Graph interrupted again after resume — awaiting approval for %s", new_pending)
        return _build_result(
            result,
            needs_approval=True,
            pending_actions=new_pending,
        )

    return _build_result(result)


def run_agent_sync(
    message: str,
    thread_id: str = "default",
) -> AgentResult:
    """Synchronous version of run_agent (no interrupt handling).

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
