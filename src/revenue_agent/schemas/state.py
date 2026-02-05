"""LangGraph agent state schema."""

import operator
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from revenue_agent.schemas.actions import ActionDraft


class ReasoningStep(BaseModel):
    """A single step in the agent's reasoning trace."""

    step: str = Field(..., description="Type of step: llm_decision, tool_call, tool_result, pre_analysis")
    node: str = Field(..., description="Graph node that produced this step")
    timestamp: str = Field(..., description="ISO-8601 timestamp")
    tool: str | None = Field(None, description="Tool name (for tool_call / tool_result steps)")
    tool_args: dict[str, Any] | None = Field(None, description="Tool arguments (for tool_call steps)")
    tool_calls: list[str] | None = Field(None, description="Tool names the LLM chose to call")
    content_preview: str | None = Field(None, description="Truncated content preview")
    is_error: bool = Field(False, description="Whether this step encountered an error")


class ConversationContext(BaseModel):
    """Context accumulated during the conversation."""

    referenced_plans: dict[str, Any] = Field(
        default_factory=dict, description="Plans loaded during conversation"
    )
    referenced_invoices: dict[str, Any] = Field(
        default_factory=dict, description="Invoices queried during conversation"
    )
    pending_action: ActionDraft | None = Field(
        None, description="Action awaiting user approval"
    )


class AgentState(TypedDict):
    """State for the Revenue Leakage Agent graph."""

    # Messages with automatic deduplication
    messages: Annotated[list[BaseMessage], add_messages]

    # Current pending action (if any)
    pending_action: ActionDraft | None

    # Whether we're waiting for human approval
    needs_approval: bool

    # Accumulated context from the conversation
    context: dict[str, Any]

    # Reasoning trace: each node appends steps, operator.add concatenates lists
    reasoning_trace: Annotated[list[dict[str, Any]], operator.add]


def create_initial_state() -> AgentState:
    """Create a fresh agent state."""
    return AgentState(
        messages=[],
        pending_action=None,
        needs_approval=False,
        context={
            "referenced_plans": {},
            "referenced_invoices": {},
        },
        reasoning_trace=[],
    )
