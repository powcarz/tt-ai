"""FastAPI routes for the Revenue Leakage Agent."""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from revenue_agent.config import settings
from revenue_agent.graphs.revenue_graph import run_agent
from revenue_agent.services.data_loader import data_loader

router = APIRouter()


def _read_json_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, "r") as f:
        return json.load(f)


def _read_sandbox_file(filename: str) -> list[dict[str, Any]]:
    return _read_json_file(settings.sandbox_dir / filename)


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., description="User message to the agent")
    thread_id: str = Field(default="default", description="Conversation thread ID")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    response: str = Field(..., description="Agent response")
    thread_id: str = Field(..., description="Conversation thread ID")
    reasoning_trace: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Step-by-step reasoning trace of the agent's decision process",
    )


class AuditLogEntry(BaseModel):
    """Audit log entry model."""

    action: str
    result_id: str | None = None
    timestamp: str
    details: dict[str, Any] = Field(default_factory=dict)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to the Revenue Leakage Agent.

    Args:
        request: Chat request with message and optional thread_id

    Returns:
        Agent response with reasoning trace
    """
    try:
        result = await run_agent(request.message, request.thread_id)
        return ChatResponse(
            response=result.response,
            thread_id=request.thread_id,
            reasoning_trace=result.reasoning_trace,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@router.get("/audit-log")
async def get_audit_log() -> list[dict[str, Any]]:
    """Get the audit log of applied actions.

    Returns:
        List of audit log entries
    """
    try:
        return _read_json_file(settings.audit_log_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading audit log: {str(e)}")


@router.get("/sandbox/invoices")
async def get_sandbox_invoices() -> list[dict[str, Any]]:
    """Get all applied invoices from the sandbox.

    Returns:
        List of applied make-good invoices
    """
    try:
        return _read_sandbox_file("applied_invoices.json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading sandbox: {str(e)}")


@router.get("/sandbox/credit-memos")
async def get_sandbox_credit_memos() -> list[dict[str, Any]]:
    """Get all applied credit memos from the sandbox.

    Returns:
        List of applied credit memos
    """
    try:
        return _read_sandbox_file("applied_credit_memos.json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading sandbox: {str(e)}")


@router.get("/sandbox/amendments")
async def get_sandbox_amendments() -> list[dict[str, Any]]:
    """Get all applied plan amendments from the sandbox.

    Returns:
        List of applied plan amendments
    """
    try:
        return _read_sandbox_file("applied_amendments.json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading sandbox: {str(e)}")


@router.post("/sandbox/reset")
async def reset_sandbox() -> dict[str, str]:
    """Reset all sandbox files to empty state.

    Returns:
        Success message
    """
    try:
        for filename in [
            "applied_invoices.json",
            "applied_credit_memos.json",
            "applied_amendments.json",
            "audit_log.json",
        ]:
            path = settings.sandbox_dir / filename
            with open(path, "w") as f:
                json.dump([], f)
        return {"message": "Sandbox reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting sandbox: {str(e)}")


@router.get("/plans")
async def list_plans() -> list[dict[str, Any]]:
    """List all billing plans.

    Returns:
        List of billing plans
    """
    plans = data_loader.plans
    return [
        {
            "id": p.id,
            "customer_name": p.customer_name,
            "amount": p.amount,
            "currency": p.currency,
            "cadence": p.cadence.value,
        }
        for p in plans.values()
    ]


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Status message
    """
    return {"status": "healthy"}
