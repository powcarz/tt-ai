"""Preprocessor service for automatic analysis before LLM processing.

This module runs deterministic Python analysis on user messages BEFORE
they are sent to the LLM. The analysis results are injected as context
so the LLM can interpret and act on them.

Flow:
1. User sends message
2. Preprocessor detects plan IDs in the message
3. Python analysis runs for detected plans
4. Analysis results are added as system context
5. LLM receives the enriched message with analysis data
"""

import re
from datetime import date
from typing import Any

from revenue_agent.services.analysis import full_plan_analysis
from revenue_agent.services.data_loader import data_loader

_PLAN_ID_PATTERN = re.compile(r"\bP-\d+\b", re.IGNORECASE)


def extract_plan_ids(message: str) -> list[str]:
    """Extract plan IDs from a user message.
    
    Looks for patterns like P-12345, P-67890, etc.
    
    Args:
        message: User's message text
    
    Returns:
        List of plan IDs found in the message
    """
    matches = (m.group(0).upper() for m in _PLAN_ID_PATTERN.finditer(message))
    # Deduplicate while preserving order of appearance
    return list(dict.fromkeys(matches))


def is_investigation_request(message: str) -> bool:
    """Detect if the user is asking for an investigation or analysis.
    
    Args:
        message: User's message text
    
    Returns:
        True if the message appears to be requesting investigation
    """
    investigation_keywords = [
        'check', 'investigate', 'analyze', 'analysis', 'review',
        'leakage', 'missing', 'discrepancy', 'issue', 'problem',
        'revenue', 'billing', 'invoice', 'gap', 'gaps'
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in investigation_keywords)


def run_plan_analysis(plan_id: str) -> dict[str, Any] | None:
    """Run full analysis for a plan using Python logic.
    
    Args:
        plan_id: The plan ID to analyze
    
    Returns:
        Analysis results or None if plan not found
    """
    plan = data_loader.get_plan(plan_id)
    if plan is None:
        return None

    invoices = data_loader.get_invoices_for_plan(plan_id)
    return full_plan_analysis(plan, invoices, as_of_date=date.today())


def format_analysis_context(analysis: dict[str, Any]) -> str:
    """Format analysis results as context for the LLM.
    
    Args:
        analysis: Analysis results from full_plan_analysis
    
    Returns:
        Formatted string to inject as context
    """
    summary = analysis["summary"]

    lines = [
        f"## Pre-computed Analysis for Plan {analysis['plan_id']} (as of {analysis['analysis_date']})",
        "",
        f"**Customer**: {analysis['customer_name']}",
        f"**Plan Amount**: {analysis['plan_amount']:,.2f} {analysis['plan_currency']} ({analysis['plan_cadence']})",
        f"**Plan Start Date**: {analysis['plan_start_date']}",
        "",
        f"**Expected Invoices**: {analysis['expected_invoices']}",
        f"**Actual Invoices Found**: {analysis['total_invoices_found']}",
        "",
    ]

    # Missing periods
    if analysis["missing_periods"]:
        lines.append(f"### Missing Billing Periods ({analysis['missing_periods_count']} found)")
        lines.append(f"**Total Missing Revenue**: {summary['total_missing_revenue']:,.2f} {summary['currency']}")
        lines.append("")
        for i, period in enumerate(analysis["missing_periods"], 1):
            lines.append(f"{i}. {period['period_start']} to {period['period_end']} - {period['expected_amount']:,.2f} {period['currency']}")
        lines.append("")
    else:
        lines.append("### No Missing Billing Periods")
        lines.append("")

    # Amount discrepancies
    if analysis["amount_discrepancies"]:
        lines.append(f"### Amount Discrepancies ({analysis['amount_discrepancies_count']} found)")
        for disc in analysis["amount_discrepancies"]:
            if disc["type"] == "amount_mismatch":
                direction = "overbilled" if disc["is_overbilled"] else "underbilled"
                lines.append(f"- Invoice {disc['invoice_id']}: {direction} by {abs(disc['difference']):,.2f} {disc['currency']} ({disc['billing_period']})")
            elif disc["type"] == "currency_mismatch":
                lines.append(f"- Invoice {disc['invoice_id']}: Currency mismatch - billed in {disc['invoice_currency']} instead of {disc['plan_currency']} ({disc['billing_period']})")
        lines.append("")

    # Summary
    lines.append("### Revenue Impact Summary")
    lines.append(f"- Total Missing Revenue: {summary['total_missing_revenue']:,.2f} {summary['currency']}")
    if summary['total_overbilled'] > 0:
        lines.append(f"- Total Overbilled: {summary['total_overbilled']:,.2f} {summary['currency']}")
    if summary['total_underbilled'] > 0:
        lines.append(f"- Total Underbilled: {summary['total_underbilled']:,.2f} {summary['currency']}")
    lines.append(f"- **Net Revenue Leakage**: {summary['net_revenue_leakage']:,.2f} {summary['currency']}")

    return "\n".join(lines)


def preprocess_message(message: str) -> tuple[str, str | None]:
    """Preprocess a user message and generate analysis context.
    
    This is the main entry point. It:
    1. Extracts plan IDs from the message
    2. Checks if it's an investigation request
    3. Runs Python analysis for relevant plans
    4. Returns the analysis as context to inject
    
    Args:
        message: The user's original message
    
    Returns:
        Tuple of (original_message, analysis_context or None)
    """
    # Only run analysis for investigation-type requests
    if not is_investigation_request(message):
        return message, None

    # Extract plan IDs
    plan_ids = extract_plan_ids(message)

    if not plan_ids:
        return message, None

    # Run analysis for each plan
    analysis_parts = []
    for plan_id in plan_ids:
        analysis = run_plan_analysis(plan_id)
        if analysis:
            analysis_parts.append(format_analysis_context(analysis))

    if not analysis_parts:
        return message, None

    # Combine all analyses
    context = (
        "---\n"
        "**[AUTOMATED PRE-ANALYSIS - Python Deterministic Calculations]**\n"
        "The following analysis was computed using Python date logic before your response.\n"
        "Use this data to inform your response - these calculations are accurate as of today's date.\n"
        "---\n\n"
        + "\n\n---\n\n".join(analysis_parts)
        + "\n\n---\n"
        "**[END OF PRE-ANALYSIS]**\n"
        "Now respond to the user's question using the above analysis data.\n"
        "---"
    )

    return message, context
