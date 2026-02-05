"""Tools for loading and working with billing plans."""

from langchain_core.tools import tool

from revenue_agent.services.data_loader import data_loader


@tool
def load_plan(plan_id: str) -> dict:
    """Load a billing plan by its ID.

    Args:
        plan_id: The unique identifier for the billing plan (e.g., "P-12345")

    Returns:
        Dictionary containing plan details including amount, currency, cadence,
        customer info, and entitlements. Returns error message if plan not found.
    """
    plan = data_loader.get_plan(plan_id)
    if plan is None:
        return {"error": f"Plan {plan_id} not found"}

    return {
        "id": plan.id,
        "customer_id": plan.customer_id,
        "customer_name": plan.customer_name,
        "amount": plan.amount,
        "currency": plan.currency,
        "cadence": plan.cadence.value,
        "start_date": plan.start_date.isoformat(),
        "end_date": plan.end_date.isoformat() if plan.end_date else None,
        "entitlements": plan.entitlements,
        "is_active": plan.is_active,
    }
