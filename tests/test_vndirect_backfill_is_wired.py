"""VNDIRECT statements must actually reach the record during a sync.

normalize_stock_data() has always accepted `vndirect_data` and overlaid
revenue, net income, EBIT, assets, equity, debt and FCF wherever TradingView
was silent. reconstruct_financial_triangles() has always read those as
reported (tier 3) witnesses. sync_unified_screener_universe() never passed
them, so the whole path was dead code and roughly half the universe was
refused for want of lines a second vendor had.

These tests pin the wiring, not the vendor: no network is touched.
"""

from unittest import mock

import pytest

import services.unified_data_service as uds
from services.unified_data_service import (
    _needs_vndirect_backfill,
    normalize_stock_data,
    sync_unified_screener_universe,
)
from services.valuation_engine import InputResolver, ValuationEngine

PRICE = 25_000.0

#: TradingView's answer for a symbol it has prices for and no statements -
#: the shape that made up roughly half the universe.
TV_NO_STATEMENTS = {
    "close": PRICE,
    "market_cap_basic": 145.369e12,
    "diluted_shares_outstanding_fq": 5_814_785_700,
}

#: What VNDIRECT Finfo returns for the same symbol.
VND_FULL = {
    "revenue_ttm": 149e12,
    "net_income_ttm": 34.5e12,
    "ebit_ttm": 40e12,
    "total_assets_fq": 178e12,
    "total_equity_fq": 74e12,
    "total_debt_fq": 85.824e12,
    "cfo_ttm": 28e12,
    "capex_ttm": 12e12,
    "da_ttm": 6e12,
    "cash_fq": 14.644e12,
    "total_current_assets_fq": 90e12,
    "total_current_liabilities_fq": 60e12,
    "company_form": "NON_FINANCE",
    "source": "VNDIRECT_FINFO",
}


#: Everything _TV_REQUIRED_LINES asks for, present. The cash-flow pair
#: joined that set once the audit measured fcf and cfo as the two largest
#: blocking drivers while VNDIRECT had carried both lines all along.
COMPLETE_TV_ROW = dict(
    TV_NO_STATEMENTS,
    total_revenue_ttm=149e12, net_income_ttm=34.5e12, ebit_ttm=40e12,
    total_assets_fq=178e12, total_equity_fq=74e12, total_debt_fq=85.824e12,
    cash_f_operating_activities_ttm=28e12,
    capital_expenditures_ttm=-12e12,
)


class TestBackfillPredicate:
    def test_absent_tv_entry_needs_a_call(self):
        assert _needs_vndirect_backfill(None) is True
        assert _needs_vndirect_backfill({}) is True

    def test_price_only_entry_needs_a_call(self):
        assert _needs_vndirect_backfill(TV_NO_STATEMENTS) is True

    def test_partial_coverage_still_needs_a_call(self):
        partial = dict(TV_NO_STATEMENTS, total_assets_fq=178e12, total_debt_fq=85e12)
        assert _needs_vndirect_backfill(partial) is True

    def test_a_complete_row_is_still_asked_while_a_line_is_overridden(self):
        """This used to assert False, and the assertion was the bug.

        A complete TradingView row excused the call, which was correct
        while the overlay was purely a cascade: nothing VNDIRECT returned
        would have been read. Two lines are now decided in VNDIRECT's
        favour whatever TradingView holds, and this gate went on skipping
        those symbols - so the payload never arrived, the overlay never
        ran, and the overrides were unreachable for exactly the companies
        that motivated them. The measurement: 58.3% of the universe
        satisfied the cash flow identity with the published figure where
        the override should have given 99.8%.

        The call costs a request per symbol. That is the price of the
        override and it is named here rather than quietly avoided.
        """
        assert _needs_vndirect_backfill(COMPLETE_TV_ROW) is True

    def test_and_it_would_cost_nothing_again_if_the_overrides_went_away(self):
        """The gate must still be a gate, not a hard-wired True.

        If the overlay ever returns to a pure cascade, a complete row can
        be skipped again - and this pins that the reason it is asked
        today is the override list, not a line someone gave up on.
        """
        assert uds._LINES_THE_VENDOR_WINS_OUTRIGHT, "premise of the test above"
        with mock.patch.object(uds, "_LINES_THE_VENDOR_WINS_OUTRIGHT", ()):
            assert _needs_vndirect_backfill(COMPLETE_TV_ROW) is False
            assert _needs_vndirect_backfill(TV_NO_STATEMENTS) is True


class TestOverlayReachesTheEngine:
    def test_without_vndirect_the_symbol_is_refused(self):
        record = normalize_stock_data(
            "TEST", "HOSE", "Test", "VNMAT", "Vat lieu",
            tv_data=dict(TV_NO_STATEMENTS), enable_source0_fallback=False,
        )
        models = ValuationEngine().calculate_all_models("TEST", record)
        assert sum(1 for m in models if m.active) == 0

    def test_with_vndirect_the_lines_arrive_tiered(self):
        record = normalize_stock_data(
            "TEST", "HOSE", "Test", "VNMAT", "Vat lieu",
            tv_data=dict(TV_NO_STATEMENTS), vndirect_data=dict(VND_FULL),
            enable_source0_fallback=False,
        )
        tiers = record["field_provenance"]
        for line in ("revenue", "net_income", "ebit", "total_assets", "equity", "debt"):
            assert line in record, f"{line} did not survive the overlay"
            assert tiers[line] >= InputResolver.MIN_TRUSTED_UPSTREAM_TIER, (
                f"{line} came from a reported VNDIRECT statement but landed at "
                f"tier {tiers[line]}"
            )

    def test_with_vndirect_the_models_publish(self):
        record = normalize_stock_data(
            "TEST", "HOSE", "Test", "VNMAT", "Vat lieu",
            tv_data=dict(TV_NO_STATEMENTS), vndirect_data=dict(VND_FULL),
            enable_source0_fallback=False,
        )
        models = ValuationEngine().calculate_all_models("TEST", record)
        active = [m for m in models if m.active]
        assert len(active) >= 4, (
            f"only {len(active)} models published; blocked: "
            f"{sorted({d for m in models for d in (m.diagnostics or {}).get('imputed_drivers', [])})}"
        )

    def test_vndirect_does_not_override_tradingview(self):
        """The overlay fills gaps. It must not replace a reported line."""
        tv = dict(TV_NO_STATEMENTS, total_revenue_ttm=100e12)
        record = normalize_stock_data(
            "TEST", "HOSE", "Test", "VNMAT", "Vat lieu",
            tv_data=tv, vndirect_data=dict(VND_FULL), enable_source0_fallback=False,
        )
        assert record["revenue"] == pytest.approx(100e12)

    def test_an_empty_vndirect_reply_changes_nothing(self):
        record = normalize_stock_data(
            "TEST", "HOSE", "Test", "VNMAT", "Vat lieu",
            tv_data=dict(TV_NO_STATEMENTS), vndirect_data={},
            enable_source0_fallback=False,
        )
        models = ValuationEngine().calculate_all_models("TEST", record)
        assert sum(1 for m in models if m.active) == 0


class TestSyncPassesItThrough:
    def test_sync_queries_and_forwards_vndirect(self, monkeypatch):
        """The regression that made all of the above dead code."""
        import services.unified_data_service as uds

        monkeypatch.setattr(
            uds, "fetch_tradingview_batch_by_tickers",
            lambda tickers, chunk_size=150: {"TEST": dict(TV_NO_STATEMENTS)},
        )
        asked = []

        def _fake_vnd(symbol, *args, **kwargs):
            asked.append(symbol)
            return dict(VND_FULL)

        monkeypatch.setattr(uds, "fetch_vndirect_financials", _fake_vnd)

        payload = sync_unified_screener_universe(
            {"TEST": {"exchange": "HOSE", "sector_code": "VNMAT",
                      "sector_name": "Vat lieu", "name": "Test"}}
        )

        assert asked == ["TEST"], "the sync never asked VNDIRECT for the gaps"
        record = payload["stocks"]["TEST"]
        assert "vndirect_finfo" in record["_metadata"]["sources_used"]
        assert record["field_provenance"]["debt"] >= InputResolver.MIN_TRUSTED_UPSTREAM_TIER

    def test_sync_asks_even_for_symbols_tradingview_already_covers(
            self, monkeypatch):
        """The inverse of what this asserted, for a measured reason.

        Skipping a covered symbol saved a request and cost the override:
        the two lines VNDIRECT wins outright were never fetched for any
        company TradingView had answered, so the reversal did not happen
        where it mattered. The request is the price of the override.
        """
        import services.unified_data_service as uds

        full = dict(COMPLETE_TV_ROW)
        monkeypatch.setattr(
            uds, "fetch_tradingview_batch_by_tickers",
            lambda tickers, chunk_size=150: {"TEST": full},
        )
        asked = []
        monkeypatch.setattr(
            uds, "fetch_vndirect_financials",
            lambda symbol, *a, **k: asked.append(symbol) or {},
        )

        sync_unified_screener_universe(
            {"TEST": {"exchange": "HOSE", "sector_code": "VNMAT",
                      "sector_name": "Vat lieu", "name": "Test"}}
        )
        assert asked == ["TEST"], (
            "a complete TradingView row is exactly the row an override"
            " exists to correct; skipping it makes the override dead code")
