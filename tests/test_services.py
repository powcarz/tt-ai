"""Tests for services."""

import pytest
from datetime import date

from revenue_agent.services.data_loader import DataLoader


class TestDataLoader:
    """Tests for DataLoader service."""

    def setup_method(self):
        """Reset data loader before each test."""
        self.loader = DataLoader()
        self.loader.reload()

    def test_load_plans(self):
        """Test loading billing plans."""
        plans = self.loader.plans
        
        assert len(plans) == 6
        assert "P-12345" in plans
        assert plans["P-12345"].customer_name == "Acme Corporation"
        assert "P-44444" in plans
        assert plans["P-44444"].customer_name == "Umbrella Logistics"

    def test_load_invoices(self):
        """Test loading invoices."""
        invoices = self.loader.invoices
        
        assert len(invoices) > 0
        assert any(inv.id == "INV-001" for inv in invoices)

    def test_get_invoices_for_plan(self):
        """Test getting invoices for a specific plan."""
        invoices = self.loader.get_invoices_for_plan("P-12345")
        
        assert len(invoices) == 2
        assert all(inv.plan_id == "P-12345" for inv in invoices)

    def test_get_exchange_rate(self):
        """Test getting exchange rate."""
        rate = self.loader.get_exchange_rate("EUR", "USD", date(2024, 9, 1))
        
        assert rate is not None
        assert rate.rate == 1.08

    def test_get_exchange_rate_same_currency(self):
        """Test getting exchange rate for same currency."""
        rate = self.loader.get_exchange_rate("USD", "USD")
        
        assert rate is not None
        assert rate.rate == 1.0

    def test_credit_memos(self):
        """Test loading credit memos."""
        memos = self.loader.credit_memos
        
        assert len(memos) == 1
        assert memos[0].id == "CM-001"
