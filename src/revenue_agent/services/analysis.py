"""Pure Python analysis service for revenue leakage detection.

This module provides deterministic calculations that don't rely on LLM reasoning.
It calculates expected billing periods and identifies gaps based on actual dates.
"""

from calendar import monthrange
from datetime import date, timedelta
from typing import Any

from revenue_agent.schemas.billing import BillingPlan, Cadence, Invoice


def get_period_delta(cadence: Cadence) -> tuple[int, int]:
    """Get the month/day delta for a billing cadence.
    
    Returns:
        Tuple of (months, days) to add for each period.
    """
    match cadence:
        case Cadence.MONTHLY:
            return (1, 0)
        case Cadence.QUARTERLY:
            return (3, 0)
        case Cadence.ANNUAL:
            return (12, 0)
        case _:
            return (1, 0)


def add_months(start_date: date, months: int) -> date:
    """Add months to a date, handling month-end edge cases."""
    month = start_date.month - 1 + months
    year = start_date.year + month // 12
    month = month % 12 + 1
    day = min(start_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def get_period_end(period_start: date, cadence: Cadence) -> date:
    """Calculate the end date of a billing period."""
    months, _ = get_period_delta(cadence)
    next_period_start = add_months(period_start, months)
    return next_period_start - timedelta(days=1)


def calculate_expected_billing_periods(
    start_date: date,
    cadence: Cadence,
    end_date: date | None = None,
    as_of_date: date | None = None,
) -> list[tuple[date, date]]:
    """Calculate all expected billing periods from plan start to current date.
    
    This is a DETERMINISTIC calculation that doesn't rely on LLM reasoning.
    
    Args:
        start_date: When the billing plan started
        cadence: Billing frequency (monthly, quarterly, annual)
        end_date: When the plan ended (None if ongoing)
        as_of_date: Calculate periods up to this date (defaults to today)
    
    Returns:
        List of (period_start, period_end) tuples for all expected billing periods
    """
    # Use current date if not specified
    as_of_date = as_of_date or date.today()
    
    # For ongoing plans, use as_of_date as the effective end
    effective_end = min(end_date, as_of_date) if end_date else as_of_date
    
    periods: list[tuple[date, date]] = []
    current_start = start_date
    
    while current_start <= effective_end:
        period_end = get_period_end(current_start, cadence)
        
        # Only include periods that have fully elapsed
        if period_end <= as_of_date:
            periods.append((current_start, period_end))
        
        # Move to next period
        months, _ = get_period_delta(cadence)
        current_start = add_months(current_start, months)
    
    return periods


def find_missing_billing_periods(
    plan: BillingPlan,
    invoices: list[Invoice],
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    """Find all billing periods that are missing invoices.
    
    This is the core DETERMINISTIC analysis that combines:
    - Pure Python date calculations
    - Actual invoice data comparison
    
    Args:
        plan: The billing plan to analyze
        invoices: List of invoices for this plan
        as_of_date: Analyze up to this date (defaults to today)
    
    Returns:
        List of missing periods with details
    """
    as_of_date = as_of_date or date.today()
    
    # Calculate all expected periods
    expected_periods = calculate_expected_billing_periods(
        start_date=plan.start_date,
        cadence=plan.cadence,
        end_date=plan.end_date,
        as_of_date=as_of_date,
    )
    
    # Extract invoiced periods (as date tuples for comparison)
    invoiced_period_set: set[tuple[date, date]] = set()
    for inv in invoices:
        invoiced_period_set.add((inv.billing_period_start, inv.billing_period_end))
    
    # Find gaps
    missing: list[dict[str, Any]] = []
    for period_start, period_end in expected_periods:
        if (period_start, period_end) not in invoiced_period_set:
            missing.append({
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "expected_amount": plan.amount,
                "currency": plan.currency,
            })
    
    return missing


def analyze_invoice_amounts(
    plan: BillingPlan,
    invoices: list[Invoice],
) -> list[dict[str, Any]]:
    """Analyze invoices for amount discrepancies.
    
    Compares each invoice amount against the plan's expected amount.
    
    Args:
        plan: The billing plan
        invoices: List of invoices for this plan
    
    Returns:
        List of discrepancies found
    """
    discrepancies: list[dict[str, Any]] = []
    
    for inv in invoices:
        # Check currency match
        if inv.currency != plan.currency:
            discrepancies.append({
                "type": "currency_mismatch",
                "invoice_id": inv.id,
                "invoice_currency": inv.currency,
                "plan_currency": plan.currency,
                "invoice_amount": inv.amount,
                "billing_period": f"{inv.billing_period_start} to {inv.billing_period_end}",
            })
        # Check amount match (only if same currency)
        elif inv.amount != plan.amount:
            difference = inv.amount - plan.amount
            discrepancies.append({
                "type": "amount_mismatch",
                "invoice_id": inv.id,
                "invoice_amount": inv.amount,
                "expected_amount": plan.amount,
                "difference": difference,
                "is_overbilled": difference > 0,
                "currency": inv.currency,
                "billing_period": f"{inv.billing_period_start} to {inv.billing_period_end}",
            })
    
    return discrepancies


def full_plan_analysis(
    plan: BillingPlan,
    invoices: list[Invoice],
    as_of_date: date | None = None,
) -> dict[str, Any]:
    """Perform complete revenue leakage analysis for a plan.
    
    This combines all deterministic checks:
    - Missing billing periods
    - Amount discrepancies
    - Currency mismatches
    
    Args:
        plan: The billing plan to analyze
        invoices: List of invoices for this plan
        as_of_date: Analyze up to this date (defaults to today)
    
    Returns:
        Complete analysis report
    """
    as_of_date = as_of_date or date.today()
    
    missing_periods = find_missing_billing_periods(plan, invoices, as_of_date)
    amount_issues = analyze_invoice_amounts(plan, invoices)
    expected_periods = calculate_expected_billing_periods(
        plan.start_date, plan.cadence, plan.end_date, as_of_date
    )
    
    # Calculate total revenue impact
    total_missing_revenue = sum(p["expected_amount"] for p in missing_periods)
    total_overbilled = sum(
        d["difference"] for d in amount_issues 
        if d.get("type") == "amount_mismatch" and d.get("is_overbilled")
    )
    total_underbilled = sum(
        abs(d["difference"]) for d in amount_issues 
        if d.get("type") == "amount_mismatch" and not d.get("is_overbilled")
    )
    
    return {
        "plan_id": plan.id,
        "customer_name": plan.customer_name,
        "analysis_date": as_of_date.isoformat(),
        "plan_start_date": plan.start_date.isoformat(),
        "plan_amount": plan.amount,
        "plan_currency": plan.currency,
        "plan_cadence": plan.cadence.value,
        "total_invoices_found": len(invoices),
        "expected_invoices": len(expected_periods),
        "missing_periods": missing_periods,
        "missing_periods_count": len(missing_periods),
        "amount_discrepancies": amount_issues,
        "amount_discrepancies_count": len(amount_issues),
        "summary": {
            "total_missing_revenue": total_missing_revenue,
            "total_overbilled": total_overbilled,
            "total_underbilled": total_underbilled,
            "net_revenue_leakage": total_missing_revenue + total_underbilled - total_overbilled,
            "currency": plan.currency,
        },
    }
