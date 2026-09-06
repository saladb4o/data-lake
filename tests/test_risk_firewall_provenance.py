"""Altman Z'' must not be a function of the share price.

The firewall's balance-sheet inputs fell back to fractions of market cap
(liabilities 50%, equity 50%, EBIT 12%), so a company the market had already
sold off scored as more distressed with no reference to its accounts - and
could then be excluded from a backtest universe on that basis.
"""
import pytest

from services.valuation_engine import RiskFirewallEngine, ValuationEngine, WACCEngine


def _wacc():
    return WACCEngine.calculate(
        market_cap=5e12, interest_bearing_debt=1e12, ebit=8e11, interest_expense=7e10,
    )


class TestUnreliableAltmanIsLabelled:
    def test_balance_sheet_absent_marks_zone_unknown(self):
        res = RiskFirewallEngine.evaluate(
            {"symbol": "NODATA", "price": 20_000.0, "shares_out": 1e8}, _wacc()
        )
        assert res.altman_zone == "unknown"
        assert res.details["altman_inputs_reliable"] is False
        assert "total_assets" in res.details["imputed_inputs"]

    def test_firewall_does_not_disqualify_on_an_invented_z_score(self):
        res = RiskFirewallEngine.evaluate(
            {"symbol": "NODATA", "price": 20_000.0, "shares_out": 1e8}, _wacc()
        )
        assert res.four_quadrant_category != "toxic_exclusion"
        assert res.firewall_passed is True

    def test_real_balance_sheet_is_marked_reliable(self):
        res = RiskFirewallEngine.evaluate(
            {
                "symbol": "REAL", "price": 20_000.0, "shares_out": 1e8,
                "total_assets": 2e12, "total_liabilities": 8e11,
                "book_equity": 1.2e12, "working_capital": 3e11,
                "retained_earnings": 4e11, "ebit": 2.5e11,
            },
            _wacc(),
        )
        assert res.details["altman_inputs_reliable"] is True
        assert res.altman_zone in ("safe", "grey", "distress")

    def test_a_real_distressed_balance_sheet_is_still_caught(self):
        """The relaxation must not blunt the firewall on real data."""
        res = RiskFirewallEngine.evaluate(
            {
                "symbol": "SICK", "price": 3_000.0, "shares_out": 1e8,
                "total_assets": 1e12, "total_liabilities": 1.4e12,
                "book_equity": -4e11, "working_capital": -5e11,
                "retained_earnings": -6e11, "ebit": -2e11,
                "beneish_m_score": -1.20,
            },
            _wacc(),
        )
        assert res.details["altman_inputs_reliable"] is True
        assert res.four_quadrant_category == "toxic_exclusion"
        assert res.firewall_passed is False


class TestZScoreDoesNotTrackPrice:
    @pytest.mark.parametrize("price", [5_000.0, 20_000.0, 80_000.0])
    def test_same_accounts_same_zone_at_any_price(self, price):
        res = RiskFirewallEngine.evaluate(
            {
                "symbol": "SAME", "price": price, "shares_out": 1e8,
                "total_assets": 2e12, "total_liabilities": 8e11,
                "book_equity": 1.2e12, "working_capital": 3e11,
                "retained_earnings": 4e11, "ebit": 2.5e11,
            },
            _wacc(),
        )
        assert res.altman_zone == "safe"
