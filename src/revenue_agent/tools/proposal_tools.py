"""Tools for proposing corrective actions."""

from typing import Any

from langchain_core.tools import tool

from revenue_agent.schemas.actions import (
    ActionDraft,
    ActionType,
    CreditMemoProposal,
    MakeGoodInvoiceProposal,
    PlanAmendmentProposal,
)
from revenue_agent.services.data_loader import data_loader
from revenue_agent.tools.sandbox_tools import store_pending_action


def _error_response(message: str) -> dict:
    return {"error": message}


def _format_draft_response(
    *,
    draft: ActionDraft,
    details: dict[str, Any],
    message: str,
) -> dict:
    return {
        "action_id": draft.id,
        "action_type": draft.action_type.value,
        "status": draft.status.value,
        "details": details,
        "evidence": draft.evidence,
        "message": message,
    }


@tool
def propose_make_good_invoice(
    plan_id: str,
    amount: float,
    reason: str,
    billing_period_start: str,
    billing_period_end: str,
) -> dict:
    """Propose a make-good invoice to recover missed or underbilled revenue.

    Args:
        plan_id: The billing plan ID to invoice
        amount: The invoice amount
        reason: Explanation for the make-good invoice (e.g., "Missing October 2024 billing")
        billing_period_start: Start of the missed billing period (YYYY-MM-DD)
        billing_period_end: End of the missed billing period (YYYY-MM-DD)

    Returns:
        Dictionary with the action draft details requiring approval.
    """
    plan = data_loader.get_plan(plan_id)
    if plan is None:
        return _error_response(f"Plan {plan_id} not found")

    proposal = MakeGoodInvoiceProposal(
        plan_id=plan_id,
        amount=amount,
        currency=plan.currency,
        reason=reason,
        billing_period_start=billing_period_start,
        billing_period_end=billing_period_end,
    )

    draft = ActionDraft(
        action_type=ActionType.MAKE_GOOD_INVOICE,
        details=proposal,
        evidence=f"Make-good invoice for {plan.customer_name}: {reason}",
    )
    store_pending_action(
        draft.id,
        {
            "action_type": draft.action_type.value,
            "details": proposal.model_dump(),
        },
    )

    return _format_draft_response(
        draft=draft,
        details=proposal.model_dump(),
        message=(
            f"Proposed a make-good invoice for {amount:,.2f} {plan.currency} "
            f"covering {billing_period_start} to {billing_period_end}. "
            f"Please confirm if you'd like to apply this."
        ),
    )


@tool
def propose_credit_memo(
    invoice_id: str,
    amount: float,
    reason: str,
) -> dict:
    """Propose a credit memo to reduce what a customer owes due to overbilling.

    Args:
        invoice_id: The invoice ID to credit
        amount: The credit amount (positive value)
        reason: Explanation for the credit memo (e.g., "Overbilled by $2,000 due to FX error")

    Returns:
        Dictionary with the action draft details requiring approval.
    """
    # Find the invoice to get plan and currency info
    invoices = [inv for inv in data_loader.invoices if inv.id == invoice_id]
    if not invoices:
        return _error_response(f"Invoice {invoice_id} not found")

    invoice = invoices[0]

    proposal = CreditMemoProposal(
        invoice_id=invoice_id,
        plan_id=invoice.plan_id,
        amount=amount,
        currency=invoice.currency,
        reason=reason,
    )

    draft = ActionDraft(
        action_type=ActionType.CREDIT_MEMO,
        details=proposal,
        evidence=f"Credit memo for invoice {invoice_id}: {reason}",
    )
    store_pending_action(
        draft.id,
        {
            "action_type": draft.action_type.value,
            "details": proposal.model_dump(),
        },
    )

    return _format_draft_response(
        draft=draft,
        details=proposal.model_dump(),
        message=(
            f"Proposed a credit memo of {amount:,.2f} {invoice.currency} "
            f"for invoice {invoice_id}. "
            f"Please confirm if you'd like to apply this."
        ),
    )


@tool
def propose_plan_amendment(
    plan_id: str,
    changes: dict[str, Any],
    reason: str,
) -> dict:
    """Propose an amendment to a billing plan (amount, cadence, entitlements).

    Args:
        plan_id: The billing plan ID to amend
        changes: Dictionary of fields to update (e.g., {"amount": 100000, "entitlements": ["Premium Support"]})
        reason: Explanation for the amendment (e.g., "Customer upgraded to Enterprise tier")

    Returns:
        Dictionary with the action draft details requiring approval.
    """
    plan = data_loader.get_plan(plan_id)
    if plan is None:
        return _error_response(f"Plan {plan_id} not found")

    proposal = PlanAmendmentProposal(
        plan_id=plan_id,
        changes=changes,
        reason=reason,
    )

    draft = ActionDraft(
        action_type=ActionType.PLAN_AMENDMENT,
        details=proposal,
        evidence=f"Plan amendment for {plan.customer_name}: {reason}",
    )
    store_pending_action(
        draft.id,
        {
            "action_type": draft.action_type.value,
            "details": proposal.model_dump(),
        },
    )

    return _format_draft_response(
        draft=draft,
        details=proposal.model_dump(),
        message=(
            f"Proposed a plan amendment for {plan.customer_name}. "
            f"Please confirm if you'd like to apply these changes."
        ),
    )
