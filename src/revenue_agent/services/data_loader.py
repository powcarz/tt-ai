"""Data loading service for JSON files."""

import json
from datetime import date
from pathlib import Path
from typing import Any

from revenue_agent.config import settings
from revenue_agent.schemas.billing import BillingPlan, CreditMemo, Invoice
from revenue_agent.schemas.fx import ExchangeRate


class DataLoader:
    """Loads and caches data from JSON files."""

    _instance: "DataLoader | None" = None
    _plans: dict[str, BillingPlan] | None = None
    _invoices: list[Invoice] | None = None
    _credit_memos: list[CreditMemo] | None = None
    _exchange_rates: list[ExchangeRate] | None = None
    _invoice_by_plan_id: dict[str, list[Invoice]] | None = None
    _invoice_by_customer_name: dict[str, list[Invoice]] | None = None
    _credit_memos_by_invoice_id: dict[str, list[CreditMemo]] | None = None
    _exchange_rate_index: dict[tuple[str, str], list[ExchangeRate]] | None = None

    def __new__(cls) -> "DataLoader":
        """Singleton pattern for data loader."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_json(self, path: Path) -> Any:
        """Load JSON from file path."""
        if not path.exists():
            return []
        with open(path, "r") as f:
            return json.load(f)

    def reload(self) -> None:
        """Force reload all data from files."""
        self._plans = None
        self._invoices = None
        self._credit_memos = None
        self._exchange_rates = None
        self._invoice_by_plan_id = None
        self._invoice_by_customer_name = None
        self._credit_memos_by_invoice_id = None
        self._exchange_rate_index = None

    @property
    def plans(self) -> dict[str, BillingPlan]:
        """Get all billing plans indexed by ID."""
        if self._plans is None:
            raw = self._load_json(settings.billing_plans_path)
            self._plans = {p["id"]: BillingPlan.model_validate(p) for p in raw}
        return self._plans

    @property
    def invoices(self) -> list[Invoice]:
        """Get all invoices."""
        if self._invoices is None:
            raw = self._load_json(settings.invoices_path)
            self._invoices = [Invoice.model_validate(inv) for inv in raw]
            self._invoice_by_plan_id = {}
            self._invoice_by_customer_name = {}
            for invoice in self._invoices:
                self._invoice_by_plan_id.setdefault(invoice.plan_id, []).append(invoice)
                self._invoice_by_customer_name.setdefault(invoice.customer_name, []).append(invoice)
        return self._invoices

    @property
    def credit_memos(self) -> list[CreditMemo]:
        """Get all credit memos."""
        if self._credit_memos is None:
            raw = self._load_json(settings.credit_memos_path)
            self._credit_memos = [CreditMemo.model_validate(cm) for cm in raw]
            self._credit_memos_by_invoice_id = {}
            for memo in self._credit_memos:
                self._credit_memos_by_invoice_id.setdefault(memo.invoice_id, []).append(memo)
        return self._credit_memos

    @property
    def exchange_rates(self) -> list[ExchangeRate]:
        """Get all exchange rates."""
        if self._exchange_rates is None:
            raw = self._load_json(settings.exchange_rates_path)
            rates_list = raw.get("rates", []) if isinstance(raw, dict) else raw
            self._exchange_rates = [ExchangeRate.model_validate(r) for r in rates_list]
            self._exchange_rate_index = {}
            for rate in self._exchange_rates:
                key = (rate.from_currency, rate.to_currency)
                self._exchange_rate_index.setdefault(key, []).append(rate)
            for rates in self._exchange_rate_index.values():
                rates.sort(key=lambda r: r.effective_date)
        return self._exchange_rates

    def get_plan(self, plan_id: str) -> BillingPlan | None:
        """Get a specific billing plan by ID."""
        return self.plans.get(plan_id)

    def get_invoices_for_plan(self, plan_id: str) -> list[Invoice]:
        """Get all invoices for a specific plan."""
        self.invoices
        return list(self._invoice_by_plan_id.get(plan_id, []))

    def get_invoices_for_customer(self, customer_name: str) -> list[Invoice]:
        """Get all invoices for a specific customer by name."""
        self.invoices
        return list(self._invoice_by_customer_name.get(customer_name, []))

    def get_credit_memos_for_invoice(self, invoice_id: str) -> list[CreditMemo]:
        """Get all credit memos for a specific invoice."""
        self.credit_memos
        return list(self._credit_memos_by_invoice_id.get(invoice_id, []))

    def _get_exchange_rate_series(self, from_currency: str, to_currency: str) -> list[ExchangeRate]:
        self.exchange_rates
        return list(self._exchange_rate_index.get((from_currency, to_currency), []))

    def get_exchange_rate(
        self, from_ccy: str, to_ccy: str, on_date: date | None = None
    ) -> ExchangeRate | None:
        """Get exchange rate between two currencies, optionally for a specific date."""
        from_currency = from_ccy
        to_currency = to_ccy

        if from_currency == to_currency:
            return ExchangeRate(
                from_currency=from_currency,
                to_currency=to_currency,
                rate=1.0,
                effective_date=on_date or date.today(),
            )

        matching = self._get_exchange_rate_series(from_currency, to_currency)
        if not matching:
            return None

        if on_date:
            # Find the rate closest to but not after the requested date
            valid_rates = [r for r in matching if r.effective_date <= on_date]
            if valid_rates:
                return max(valid_rates, key=lambda r: r.effective_date)

        # Return the most recent rate
        return max(matching, key=lambda r: r.effective_date)


# Global instance
data_loader = DataLoader()
