"""Tools for querying invoices."""

from datetime import date

from langchain_core.tools import tool

from revenue_agent.services.data_loader import data_loader


def _parse_date(date_str: str, field_name: str) -> tuple[date | None, dict | None]:
    try:
        return date.fromisoformat(date_str), None
    except ValueError:
        return None, {"error": f"Invalid {field_name}: {date_str}. Expected YYYY-MM-DD."}


def _serialize_invoice(invoice) -> dict:
    return {
        "id": invoice.id,
        "plan_id": invoice.plan_id,
        "customer_name": invoice.customer_name,
        "amount": invoice.amount,
        "currency": invoice.currency,
        "billing_period_start": invoice.billing_period_start.isoformat(),
        "billing_period_end": invoice.billing_period_end.isoformat(),
        "issue_date": invoice.issue_date.isoformat(),
        "status": invoice.status.value,
    }


@tool
def query_invoices(
    plan_id: str | None = None,
    customer_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Query invoices with optional filters.

    Args:
        plan_id: Filter by billing plan ID (e.g., "P-12345")
        customer_name: Filter by customer name (e.g., "Acme Corporation"). Case-insensitive partial match.
        start_date: Filter invoices with billing period starting on or after this date (YYYY-MM-DD)
        end_date: Filter invoices with billing period ending on or before this date (YYYY-MM-DD)

    Returns:
        Dictionary with list of matching invoices and count.
    """
    start = None
    end = None

    if start_date:
        start, error = _parse_date(start_date, "start_date")
        if error:
            return error

    if end_date:
        end, error = _parse_date(end_date, "end_date")
        if error:
            return error

    name_lower = customer_name.lower() if customer_name else None

    invoices = [
        invoice
        for invoice in data_loader.invoices
        if (not plan_id or invoice.plan_id == plan_id)
        and (not name_lower or name_lower in invoice.customer_name.lower())
        and (not start or invoice.billing_period_start >= start)
        and (not end or invoice.billing_period_end <= end)
    ]

    return {
        "count": len(invoices),
        "invoices": [_serialize_invoice(invoice) for invoice in invoices],
    }
