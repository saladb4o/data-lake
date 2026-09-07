"""The share count decides whether a symbol can be valued at all.

A derived field inherits the worst provenance tier of its inputs, so an
invented share count does not merely leave one field wrong: it drags the
market cap to tier 0, and the market cap drags every valuation model with
it. Measured across the whole universe, 565 of 1,522 symbols were refused
in exactly that shape - full VNDIRECT statements at tier 3 sitting behind a
fabricated 50,000,000.

These tests pin the rungs that recover the count from evidence already in
hand, and - just as importantly - pin the floor: when nothing reports it,
the ladder must still say so rather than invent a plausible number.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.unified_data_service import reconstruct_financial_triangles

PRICE = 20_000.0


def triangles(tv, price=PRICE, raw_mcap=0.0, vn=None, vnd=None):
    return reconstruct_financial_triangles(
        symbol="TST",
        price=price,
        raw_mcap=raw_mcap,
        sector_code="VNIND",
        tv_data=tv,
        vn_data=vn or {},
        yf_data={},
        vnd_data=vnd,
    )


def test_total_shares_column_is_read():
    """TV_COLUMNS asks for both share columns; only diluted was ever read."""
    tri = triangles({"close": PRICE, "total_shares_outstanding_fq": 80_000_000.0})
    assert tri["shares_out"] == 80_000_000.0
    assert tri["field_provenance"]["shares"] == 3


def test_diluted_still_wins_over_total():
    tri = triangles({
        "close": PRICE,
        "diluted_shares_outstanding_fq": 90_000_000.0,
        "total_shares_outstanding_fq": 80_000_000.0,
    })
    assert tri["shares_out"] == 90_000_000.0


def test_reported_eps_rung_outranks_an_implied_one():
    """A reported EPS is a witness; one implied by a multiple is arithmetic."""
    tri = triangles({
        "close": PRICE,
        "net_income_ttm": 200_000_000_000.0,
        "earnings_per_share_basic_ttm": 2_000.0,
        "price_earnings_ttm": 5.0,          # would imply a different count
    })
    assert tri["shares_out"] == 100_000_000
    assert tri["field_provenance"]["shares"] == 2


def test_net_income_over_implied_eps():
    """price / pe is the vendor's own EPS: dividing a reported total by it
    recovers the share count the vendor used."""
    tri = triangles({
        "close": PRICE,
        "price_earnings_ttm": 10.0,
        "net_income_ttm": 200_000_000_000.0,
    })
    assert tri["shares_out"] == 100_000_000
    assert tri["field_provenance"]["shares"] == 2
    # And the whole point: the market cap is now evidence, not a fabrication.
    assert tri["field_provenance"]["market_cap"] >= 2
    # NI x PE is the market cap by definition; in billions.
    assert tri["mcap"] == pytest.approx(2_000, rel=0.01)


def test_equity_over_implied_bvps():
    tri = triangles({
        "close": PRICE,
        "price_book_fq": 2.0,
        "total_equity_fq": 1_000_000_000_000.0,
    })
    assert tri["shares_out"] == 100_000_000
    assert tri["field_provenance"]["shares"] == 2


def test_a_vndirect_only_symbol_survives_the_provenance_gate():
    """The shape that was being refused: TradingView carries a price and a
    multiple, VNDIRECT carries the statements, nobody carries the count."""
    vnd = {
        "revenue_ttm": 900_000_000_000.0,
        "net_income_ttm": 200_000_000_000.0,
        "total_assets_fq": 2_000_000_000_000.0,
        "total_equity_fq": 1_000_000_000_000.0,
        "total_debt_fq": 400_000_000_000.0,
        "cash_fq": 150_000_000_000.0,
    }
    tv = {
        "close": PRICE,
        "price_earnings_ttm": 10.0,
        "net_income_ttm": vnd["net_income_ttm"],
        "total_equity_fq": vnd["total_equity_fq"],
    }
    tri = triangles(tv, vnd=vnd)
    prov = tri["field_provenance"]
    for field in ("shares", "market_cap", "equity", "net_income"):
        assert prov[field] >= 2, f"{field} is tier {prov[field]}, below the gate"


def test_an_implied_rung_never_outranks_the_price_it_used():
    """With no real close, price is the invented 10,000 fallback. A count
    derived through it must inherit that, or a fabrication is laundered
    into evidence."""
    tri = triangles(
        {"price_earnings_ttm": 10.0, "net_income_ttm": 200_000_000_000.0},
        price=10_000.0,
    )
    assert tri["field_provenance"]["shares"] == 0


def test_nonsense_multiple_falls_through_rather_than_publishing():
    """A pe small enough to imply a company with 1,000 shares is stale data.
    Falling through to the honest fabrication beats publishing it as tier 2."""
    tri = triangles({
        "close": PRICE,
        "price_earnings_ttm": 0.001,
        "net_income_ttm": 20_000_000_000.0,
    })
    assert tri["shares_out"] == 50_000_000
    assert tri["field_provenance"]["shares"] == 0


def test_nothing_reported_is_still_refused():
    """The floor. No rung may invent a count out of an empty payload."""
    tri = triangles({}, price=10_000.0)
    assert tri["shares_out"] == 50_000_000
    assert tri["field_provenance"]["shares"] == 0
    assert tri["field_provenance"]["market_cap"] == 0
