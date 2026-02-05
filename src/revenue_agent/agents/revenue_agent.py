"""Revenue Leakage Agent using LangGraph."""

from langchain_openai import ChatOpenAI

from revenue_agent.agents.prompts.system import SYSTEM_PROMPT
from revenue_agent.config import settings
from revenue_agent.tools import (
    apply_action,
    fx_convert,
    load_plan,
    propose_credit_memo,
    propose_make_good_invoice,
    propose_plan_amendment,
    query_invoices,
    rollback_action,
)


def get_tools() -> list:
    """Get all available tools for the agent.
    
    These are the 8 core tools as specified in the requirements.
    """
    return [
        load_plan,
        query_invoices,
        fx_convert,
        propose_make_good_invoice,
        propose_credit_memo,
        propose_plan_amendment,
        apply_action,
        rollback_action,
    ]


def create_agent() -> ChatOpenAI:
    """Create a ChatOpenAI model with tools bound."""
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )

    tools = get_tools()
    return llm.bind_tools(tools)


def get_system_prompt() -> str:
    """Get the system prompt for the agent."""
    return SYSTEM_PROMPT
