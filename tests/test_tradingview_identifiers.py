"""Five requested columns exist at no company, one is not an identifier at
all, and the quantity that would have answered the largest blocking driver
in the universe was never requested.

Checked against TradingView's published financial-identifier catalogue:

  * OPERATING_MARGIN, INTEREST_EXPENSE_ON_DEBT, CAPITAL_EXPENDITURES,
    RESEARCH_AND_DEV and PREFERRED_DIVIDENDS are published at FH/FQ/FY only.
    Every "_ttm" form of them returns null for every symbol, always.
  * "depreciation_and_amortization" is not an identifier. The
    income-statement line is DEP_AMORT_EXP_INCOME_S; the cash-flow line is
    CASH_FLOW_DEPRECATION_N_AMORTIZATION - the vendor's own spelling of
    "deprecation", which the correctly-spelled copy therefore misses.
  * OPER_INCOME (TTM) is operating income: the same quantity EBIT names.

A column that does not exist is indistinguishable from a company that does
not report it, which is why this went unseen while the EBIT census read
zero across every rung and was taken as evidence about vendor coverage.
"""

import inspect

import pytest

from services import unified_data_service as uds


#: Identifiers published at FH/FQ/FY only, per the catalogue.
NO_TTM = (
    "operating_margin", "interest_expense_on_debt", "capital_expenditures",
    "research_and_dev", "preferred_dividends",
)


class TestTheSupplementaryPass:
    def test_it_asks_for_operating_income(self):
        for name in ("oper_income_ttm", "oper_income_fq"):
            assert name in uds.TRADINGVIEW_SUPPLEMENTARY_COLUMNS

    def test_it_drops_the_names_that_answered_for_nobody(self):
        """Measured over the whole universe, not reasoned about.

        The first supplementary pass counted non-null answers per column
        across all 1522 symbols. These six returned nothing for anyone,
        which makes them names the scanner does not serve - the catalogue
        gives the Pine fin_id, not the scanner's spelling of it, and the
        two agree for some identifiers and not for others. Asking again
        costs bandwidth and re-earns the same zero.
        """
        for dead in ("dep_amort_exp_income_s_ttm",
                     "dep_amort_exp_income_s_fq",
                     "cash_flow_deprecation_n_amortization_fq",
                     "total_oper_expense_ttm",
                     "interest_expense_on_debt_fy",
                     "cost_of_goods_ttm"):
            assert dead not in uds.TRADINGVIEW_SUPPLEMENTARY_COLUMNS

    def test_it_keeps_the_periods_that_answered(self):
        for base in ("operating_margin", "capital_expenditures"):
            assert f"{base}_fy" in uds.TRADINGVIEW_SUPPLEMENTARY_COLUMNS

    def test_it_never_repeats_a_ttm_that_does_not_exist(self):
        for base in NO_TTM:
            assert f"{base}_ttm" not in uds.TRADINGVIEW_SUPPLEMENTARY_COLUMNS

    def test_no_column_is_requested_twice(self):
        cols = uds.TRADINGVIEW_SUPPLEMENTARY_COLUMNS
        assert len(cols) == len(set(cols))

    def test_it_is_a_separate_request(self):
        """An identifier this service has never sent could be rejected, and
        the batch every symbol depends on must not be what discovers that."""
        src = inspect.getsource(uds.sync_unified_screener_universe)
        assert "columns=TRADINGVIEW_SUPPLEMENTARY_COLUMNS" in src
        block = src[src.index("tv_extra = fetch_tradingview"):]
        block = block[:block.index("filled = collections.Counter()")]
        assert "except Exception" in block

    def test_the_supplement_never_overwrites_the_primary_batch(self):
        src = inspect.getsource(uds.sync_unified_screener_universe)
        block = src[src.index("filled = collections.Counter()"):]
        block = block[:block.index("if tv_extra:")]
        assert "row.setdefault(" in block
        assert "row[key] = value" not in block


class TestTheFetcherHonoursTheColumnList:
    def test_arity_is_checked_against_what_was_asked_for(self):
        """Not against TRADINGVIEW_COLUMNS: a supplementary row is shorter,
        and checking it against the primary list would drop every row."""
        src = inspect.getsource(uds.fetch_tradingview_batch_by_tickers)
        assert "len(request_columns)" in src
        assert "len(TRADINGVIEW_COLUMNS)" not in src
        assert "dict(zip(request_columns, d_values))" in src

    def test_the_default_is_still_the_primary_list(self):
        sig = inspect.signature(uds.fetch_tradingview_batch_by_tickers)
        assert sig.parameters["columns"].default is None
        src = inspect.getsource(uds.fetch_tradingview_batch_by_tickers)
        assert "columns else TRADINGVIEW_COLUMNS" in src


class TestOperatingIncomeIsARungOfItsOwn:
    PRICE, SHARES = 25_000.0, 1_000_000_000

    def _tri(self, **over):
        tv = {
            "close": self.PRICE,
            "diluted_shares_outstanding_fq": self.SHARES,
            "total_revenue_ttm": 149e12,
            "net_income_ttm": 34.5e12,
            "total_equity_fq": 74e12,
            "total_assets_fq": 178e12,
            "total_liabilities_fq": 104e12,
        }
        tv.update(over)
        return uds.reconstruct_financial_triangles(
            "TST", self.PRICE, self.PRICE * self.SHARES, "VNIND", tv, {}, {},
        )

    def test_operating_income_supplies_ebit_when_ebit_is_absent(self):
        rec = self._tri(oper_income_ttm=40e12)
        assert rec["field_provenance"]["ebit"] == 3
        assert rec["ebit"] == pytest.approx(40e12)

    def test_a_reported_ebit_still_wins(self):
        rec = self._tri(ebit_ttm=41e12, oper_income_ttm=40e12)
        assert rec["ebit"] == pytest.approx(41e12)

    def test_it_is_a_reading_not_a_triangulation(self):
        """Operating income is EBIT, reported. Filing it at tier 2 would
        understate the evidence and refuse models that should run."""
        assert self._tri(oper_income_ttm=40e12)["field_provenance"]["ebit"] == 3

    def test_a_negative_operating_income_is_carried_through(self):
        rec = self._tri(oper_income_ttm=-3e12)
        assert rec["ebit"] == pytest.approx(-3e12)
        assert rec["field_provenance"]["ebit"] == 3

    def test_the_quarterly_and_annual_forms_are_read_too(self):
        assert self._tri(oper_income_fq=9e12)["ebit"] == pytest.approx(9e12)
        assert self._tri(oper_income_fy=36e12)["ebit"] == pytest.approx(36e12)

    def test_no_operating_income_leaves_the_ladder_where_it_was(self):
        rec = self._tri()
        assert "ebit" not in rec["field_provenance"]


class TestDepreciationReadsTheRealIdentifier:
    PRICE, SHARES = 25_000.0, 1_000_000_000

    def _tri(self, **over):
        tv = {
            "close": self.PRICE,
            "diluted_shares_outstanding_fq": self.SHARES,
            "total_revenue_ttm": 149e12,
            "net_income_ttm": 34.5e12,
            "total_equity_fq": 74e12,
            "ebit_ttm": 40e12,
        }
        tv.update(over)
        return uds.reconstruct_financial_triangles(
            "TST", self.PRICE, self.PRICE * self.SHARES, "VNIND", tv, {}, {},
        )

    def test_the_income_statement_identifier_is_read(self):
        rec = self._tri(dep_amort_exp_income_s_ttm=6e12)
        assert rec["field_provenance"]["da"] == 3
        assert rec["da"] == pytest.approx(6e12)

    def test_the_vendors_spelling_of_deprecation_is_read(self):
        rec = self._tri(cash_flow_deprecation_n_amortization_fq=6e12)
        assert rec["field_provenance"]["da"] == 3

    def test_the_old_misspelled_names_still_work_for_other_overlays(self):
        rec = self._tri(depreciation_and_amortization_ttm=6e12)
        assert rec["field_provenance"]["da"] == 3
