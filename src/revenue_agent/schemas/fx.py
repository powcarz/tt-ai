"""Foreign exchange rate schemas."""

from datetime import date

from pydantic import BaseModel, Field


class ExchangeRate(BaseModel):
    """Exchange rate between two currencies on a specific date."""

    from_currency: str = Field(..., min_length=3, max_length=3, description="Source currency code")
    to_currency: str = Field(..., min_length=3, max_length=3, description="Target currency code")
    rate: float = Field(..., gt=0, description="Exchange rate (multiply source by this)")
    effective_date: date = Field(..., description="Date the rate is effective")


class ExchangeRateTable(BaseModel):
    """Collection of exchange rates."""

    base_currency: str = Field(..., description="Base currency for the rates")
    rates: list[ExchangeRate] = Field(default_factory=list, description="List of exchange rates")
