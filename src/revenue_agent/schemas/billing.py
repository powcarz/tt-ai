"""Billing-related schemas: plans, invoices, credit memos."""

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class Cadence(str, Enum):
    """Billing cadence for a plan."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class InvoiceStatus(str, Enum):
    """Status of an invoice."""

    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    VOID = "void"


class BillingPlan(BaseModel):
    """A billing plan/contract defining expected revenue."""

    id: str = Field(..., description="Unique plan identifier, e.g. P-12345")
    customer_id: str = Field(..., description="Customer identifier")
    customer_name: str = Field(..., description="Customer display name")
    amount: float = Field(..., ge=0, description="Expected billing amount per period")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code")
    cadence: Cadence = Field(..., description="Billing frequency")
    start_date: date = Field(..., description="Plan start date")
    end_date: date | None = Field(None, description="Plan end date, null if ongoing")
    entitlements: list[str] = Field(default_factory=list, description="List of included features")
    is_active: bool = Field(True, description="Whether the plan is currently active")


class Invoice(BaseModel):
    """An issued invoice/bill."""

    id: str = Field(..., description="Unique invoice identifier, e.g. INV-001")
    plan_id: str = Field(..., description="Associated billing plan ID")
    customer_name: str = Field(..., description="Customer display name")
    amount: float = Field(..., ge=0, description="Invoice amount")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code")
    billing_period_start: date = Field(..., description="Start of billing period")
    billing_period_end: date = Field(..., description="End of billing period")
    issue_date: date = Field(..., description="Date invoice was issued")
    status: InvoiceStatus = Field(..., description="Current invoice status")


class CreditMemo(BaseModel):
    """A credit memo reducing what a customer owes."""

    id: str = Field(..., description="Unique credit memo identifier, e.g. CM-001")
    invoice_id: str = Field(..., description="Associated invoice ID being credited")
    plan_id: str = Field(..., description="Associated billing plan ID")
    customer_id: str = Field(..., description="Customer identifier")
    amount: float = Field(..., ge=0, description="Credit amount (positive value)")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code")
    reason: str = Field(..., description="Reason for the credit memo")
    issue_date: date = Field(..., description="Date credit memo was issued")
