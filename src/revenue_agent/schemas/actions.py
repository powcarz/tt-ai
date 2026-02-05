"""Action draft and applied action schemas."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Type of corrective action."""

    MAKE_GOOD_INVOICE = "make_good_invoice"
    CREDIT_MEMO = "credit_memo"
    PLAN_AMENDMENT = "plan_amendment"


class ActionStatus(str, Enum):
    """Status of an action draft."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class MakeGoodInvoiceProposal(BaseModel):
    """Details for a make-good invoice proposal."""

    plan_id: str = Field(..., description="Plan to invoice")
    amount: float = Field(..., ge=0, description="Invoice amount")
    currency: str = Field(..., description="Currency code")
    reason: str = Field(..., description="Reason for the make-good invoice")
    billing_period_start: str = Field(..., description="Start of missed billing period")
    billing_period_end: str = Field(..., description="End of missed billing period")


class CreditMemoProposal(BaseModel):
    """Details for a credit memo proposal."""

    invoice_id: str = Field(..., description="Invoice to credit")
    plan_id: str = Field(..., description="Associated plan")
    amount: float = Field(..., ge=0, description="Credit amount")
    currency: str = Field(..., description="Currency code")
    reason: str = Field(..., description="Reason for the credit memo")


class PlanAmendmentProposal(BaseModel):
    """Details for a plan amendment proposal."""

    plan_id: str = Field(..., description="Plan to amend")
    changes: dict[str, Any] = Field(..., description="Fields to update")
    reason: str = Field(..., description="Reason for the amendment")


class ActionDraft(BaseModel):
    """A proposed corrective action awaiting approval."""

    id: str = Field(default_factory=lambda: f"ACT-{uuid4().hex[:8].upper()}")
    action_type: ActionType = Field(..., description="Type of action")
    status: ActionStatus = Field(default=ActionStatus.PROPOSED)
    details: MakeGoodInvoiceProposal | CreditMemoProposal | PlanAmendmentProposal = Field(
        ..., description="Action-specific details"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    evidence: str = Field("", description="Evidence or calculations supporting this action")


class AppliedAction(BaseModel):
    """Record of an action that was applied to the sandbox."""

    action_id: str = Field(..., description="Original action draft ID")
    action_type: ActionType = Field(..., description="Type of action")
    result_id: str = Field(..., description="ID of the created resource (invoice, memo, etc.)")
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    applied_by: str = Field(default="user", description="Who approved the action")
    details: dict[str, Any] = Field(default_factory=dict, description="Snapshot of applied details")
    is_rolled_back: bool = Field(default=False)
