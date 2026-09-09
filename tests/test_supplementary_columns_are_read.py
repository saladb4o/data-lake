"""Three columns were fetched, counted, and read by nothing.

a3d3799 added fifteen identifiers to the TradingView supplementary request.
The run counted how many companies answered each:

    ebitda_margin_ttm                672
    return_on_invested_capital_fq    744
    book_tangible_per_share_fq       785

and `ebitda` blocked 630 symbols, `roic` 155. Every one of those columns
arrived in the payload and no line of code read it.

That is the tenth instance in this audit of the same defect shape - a value
computed or fetched, correctly tiered, and connected to nothing - and the
first one introduced by this audit rather than found by it. These tests pin
the two that are now wired, so the shape cannot recur silently here.

Both are ratios. Neither carries a unit assumption: the EBITDA margin is
multiplied by revenue already held in known units and propagates revenue's
tier, and ROIC is a percentage read as a percentage.
"""

import pytest

from services import unified_data_service as uds


PRICE = 25_000.0
SHARES = 1e9


def _tri(**tv):
    base = {
        "close": PRICE,
        "diluted_shares_outstanding_fq": SHARES,
        "total_assets_fq": 900e9,
        "total_liabilities_fq": 400e9,
        "total_equity_fq": 500e9,
        "total_debt_fq": 200e9,
        "cash_n_short_term_invest_fq": 50e9,
        "total_revenue_ttm": 1_000e9,
        "net_income_ttm": 80e9,
    }
    base.update({k: v for k, v in tv.items()})
    base = {k: v for k, v in base.items() if v is not None}
    return uds.reconstruct_financial_triangles(
        "TEST", PRICE, PRICE * SHARES / 1e9, "VNIND", base, {}, {},
    )


class TestEbitdaFromAReportedMargin:
    def test_a_reported_margin_is_used(self):
        tri = _tri(ebitda_margin_ttm=18.0)
        assert tri["ebitda"] == pytest.approx(180e9, rel=1e-6)

    def test_it_is_trusted_when_revenue_is(self):
        tri = _tri(ebitda_margin_ttm=18.0)
        assert tri["field_provenance"]["ebitda"] >= 2

    def test_a_reported_ebitda_still_outranks_it(self):
        tri = _tri(ebitda_margin_ttm=18.0, ebitda_ttm=250e9)
        assert tri["ebitda"] == pytest.approx(250e9, rel=1e-6)
        assert tri["field_provenance"]["ebitda"] == 3

    def test_it_never_outranks_a_reported_ebitda_even_when_absurd(self):
        tri = _tri(ebitda_margin_ttm=99.0, ebitda_ttm=10e9)
        assert tri["ebitda"] == pytest.approx(10e9, rel=1e-6)

    @pytest.mark.parametrize("bad", [101.0, -100.5, 1e6, -1e6])
    def test_a_margin_outside_the_band_is_discarded_not_rescaled(self, bad):
        """Out of band means "not the quantity we asked for". It is dropped;
        nothing tries to guess what it might have meant."""
        tri = _tri(ebitda_margin_ttm=bad)
        assert tri["ebitda"] != pytest.approx(1_000e9 * bad / 100.0, rel=1e-6)

    def test_a_negative_margin_is_kept(self):
        """A company can lose money before D&A. That is a fact about the
        company, not a bad reading."""
        tri = _tri(ebitda_margin_ttm=-12.0)
        assert tri["ebitda"] == pytest.approx(-120e9, rel=1e-6)

    def test_no_revenue_means_no_margin_rung(self):
        tri = _tri(ebitda_margin_ttm=18.0, total_revenue_ttm=None)
        assert tri["field_provenance"]["ebitda"] <= 2


class TestRoicIsReadWhenReported:
    def test_a_reported_roic_is_used(self):
        tri = _tri(return_on_invested_capital_fq=14.5)
        assert tri["roic"] == pytest.approx(14.5, abs=0.01)
        assert tri["field_provenance"]["roic"] == 3

    def test_it_outranks_the_nopat_proxy(self):
        """The proxy assumes a flat 20% tax rate for every company in the
        country. A reported figure does not need the assumption."""
        tri = _tri(return_on_invested_capital_fq=14.5, ebit_ttm=120e9)
        assert tri["roic"] == pytest.approx(14.5, abs=0.01)

    @pytest.mark.parametrize("bad", [100.5, -101.0, 5_000.0])
    def test_out_of_band_falls_through_to_the_proxy(self, bad):
        tri = _tri(return_on_invested_capital_fq=bad, ebit_ttm=120e9)
        assert tri["roic"] != pytest.approx(bad, abs=0.01)
        assert tri["field_provenance"]["roic"] >= 2

    def test_a_small_reported_roic_is_not_rescaled(self):
        """The neighbouring ratios multiply |x| <= 1 by 100 on the theory
        that it is a fraction. A genuine 0.8% return is indistinguishable
        from 0.8 as a fraction, so that rescale is not applied here."""
        tri = _tri(return_on_invested_capital_fq=0.8)
        assert tri["roic"] == pytest.approx(0.8, abs=0.01)

    def test_a_negative_roic_is_kept(self):
        tri = _tri(return_on_invested_capital_fq=-7.0)
        assert tri["roic"] == pytest.approx(-7.0, abs=0.01)


def test_every_supplementary_column_is_actually_read():
    """The defect this file exists for, stated as an invariant.

    Counting mentions is not enough - a column named only in the comment
    explaining that it was never read would satisfy that, which is how the
    first version of this test passed while book_tangible_per_share_fq was
    still connected to nothing. So this looks for the read itself.
    """
    import pathlib
    import re
    src = pathlib.Path(uds.__file__).read_text()
    for col in uds.TRADINGVIEW_SUPPLEMENTARY_COLUMNS:
        pattern = re.compile(
            r"""(?:tv_data|row|extra|entry)\.get\(\s*["']%s["']""" % re.escape(col)
        )
        assert pattern.search(src), (
            f"{col} is requested from the vendor and never read out of the "
            "payload: the request is paid for and the answer discarded"
        )


def test_the_vietcap_margin_probe_can_be_reached_without_tradingview_revenue():
    """The gate that made a working route unreachable.

    A company with no EBIT rung is, overwhelmingly, a company TradingView
    carries nothing for - its revenue arrives from VNDIRECT. Selecting the
    probe's symbols on TradingView's revenue alone therefore excluded
    exactly the companies the probe exists for, and the census measured the
    cost: Vietcap reports a non-zero EBIT margin for 615 of the 720
    companies with no operating line and none was asked.

    This pins the selection expression itself, since the probe's own body
    needs a network. The rung is sound either way: it multiplies the margin
    by whatever revenue the triangle resolves, and that resolution already
    reads the VNDIRECT overlay.
    """
    import inspect

    src = inspect.getsource(uds)
    block = src[src.index("needs_margin = ["):]
    block = block[:block.index("]")]

    assert "_has_no_ebit_rung" in block
    assert "vnd_by_symbol" in block and "revenue_ttm" in block, (
        "the probe still selects on TradingView revenue alone"
    )
    assert "total_revenue_ttm" in block, (
        "TradingView revenue must remain an accepted witness"
    )
