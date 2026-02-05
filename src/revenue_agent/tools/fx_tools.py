"""Tools for currency conversion."""

from datetime import date

from langchain_core.tools import tool

from revenue_agent.services.data_loader import data_loader


@tool
def fx_convert(
    amount: float,
    from_currency: str,
    to_currency: str,
    on_date: str | None = None,
) -> dict:
    """Convert an amount from one currency to another.

    Args:
        amount: The amount to convert
        from_currency: Source currency code (e.g., "USD", "EUR", "GBP")
        to_currency: Target currency code (e.g., "USD", "EUR", "GBP")
        on_date: Optional date for historical rate (YYYY-MM-DD), uses latest if not provided

    Returns:
        Dictionary with converted amount, rate used, and effective date.
    """
    if from_currency == to_currency:
        return {
            "original_amount": amount,
            "converted_amount": amount,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": 1.0,
            "effective_date": on_date or date.today().isoformat(),
        }

    rate_date = date.fromisoformat(on_date) if on_date else None
    rate = data_loader.get_exchange_rate(from_currency, to_currency, rate_date)

    if rate is None:
        return {
            "error": f"No exchange rate found for {from_currency} to {to_currency}",
            "original_amount": amount,
            "from_currency": from_currency,
            "to_currency": to_currency,
        }

    converted = round(amount * rate.rate, 2)

    return {
        "original_amount": amount,
        "converted_amount": converted,
        "from_currency": from_currency,
        "to_currency": to_currency,
        "rate": rate.rate,
        "effective_date": rate.effective_date.isoformat(),
    }
