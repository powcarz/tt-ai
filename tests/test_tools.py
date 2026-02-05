"""Tests for agent tools."""

import pytest

from revenue_agent.tools.plan_tools import load_plan
from revenue_agent.tools.invoice_tools import query_invoices
from revenue_agent.tools.fx_tools import fx_convert


class TestLoadPlan:
    """Tests for load_plan tool."""

    def test_load_existing_plan(self):
        """Test loading an existing plan."""
        result = load_plan.invoke({"plan_id": "P-12345"})
        
        assert "error" not in result
        assert result["id"] == "P-12345"
        assert result["customer_name"] == "Acme Corporation"
        assert result["amount"] == 10000.0
        assert result["currency"] == "USD"
        assert result["cadence"] == "monthly"

    def test_load_nonexistent_plan(self):
        """Test loading a plan that doesn't exist."""
        result = load_plan.invoke({"plan_id": "P-99999"})
        
        assert "error" in result
        assert "not found" in result["error"]


class TestQueryInvoices:
    """Tests for query_invoices tool."""

    def test_query_all_invoices(self):
        """Test querying all invoices."""
        result = query_invoices.invoke({})
        
        assert "count" in result
        assert "invoices" in result
        assert result["count"] > 0

    def test_query_invoices_by_plan(self):
        """Test filtering invoices by plan ID."""
        result = query_invoices.invoke({"plan_id": "P-12345"})
        
        assert result["count"] == 2  # September and November
        for inv in result["invoices"]:
            assert inv["plan_id"] == "P-12345"

    def test_query_invoices_by_date_range(self):
        """Test filtering invoices by date range."""
        result = query_invoices.invoke({
            "start_date": "2024-10-01",
            "end_date": "2024-10-31"
        })
        
        # Should get invoices with billing period in October
        for inv in result["invoices"]:
            assert inv["billing_period_start"] >= "2024-10-01"


class TestFxConvert:
    """Tests for fx_convert tool."""

    def test_same_currency(self):
        """Test converting same currency returns same amount."""
        result = fx_convert.invoke({
            "amount": 100.0,
            "from_currency": "USD",
            "to_currency": "USD"
        })
        
        assert result["converted_amount"] == 100.0
        assert result["rate"] == 1.0

    def test_eur_to_usd(self):
        """Test EUR to USD conversion."""
        result = fx_convert.invoke({
            "amount": 1000.0,
            "from_currency": "EUR",
            "to_currency": "USD",
            "on_date": "2024-09-01"
        })
        
        assert "error" not in result
        assert result["rate"] == 1.08
        assert result["converted_amount"] == 1080.0

    def test_unknown_currency_pair(self):
        """Test handling unknown currency pair."""
        result = fx_convert.invoke({
            "amount": 100.0,
            "from_currency": "XYZ",
            "to_currency": "ABC"
        })
        
        assert "error" in result
