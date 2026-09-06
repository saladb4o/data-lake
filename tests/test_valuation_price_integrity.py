"""The valuation engine must not invent a price.

A missing price used to silently become 10,000 VND. Every downside/upside
figure is measured against that anchor, so a stock with no price still produced
a confident-looking result: fair value 17,218 against a fabricated 10,000, an
implied +72% upside, and no field anywhere marking the input as synthetic.

This is the same no-silent-fills policy the engine already enforces for a
missing fundamental_data payload, applied to the price field itself.
"""

import math

import pytest

from services.valuation_engine import ValuationEngine


BASE = {
    "symbol": "XYZ", "name": "Test Co", "eps": 2500, "bvps": 18000, "roe": 0.18,
    "revenue": 1e12, "net_income": 2.4e11, "equity": 1.3e12,
}


@pytest.fixture
def engine():
    return ValuationEngine()


@pytest.mark.parametrize("bad_price", [None, 0, 0.0, -1500, float("nan"), "", "n/a"])
def test_missing_or_invalid_price_is_rejected(engine, bad_price):
    data = dict(BASE, price=bad_price)
    with pytest.raises(ValueError, match="[Pp]rice"):
        engine.get_comprehensive_valuation("XYZ", fundamental_data=data)


def test_absent_price_key_is_rejected(engine):
    with pytest.raises(ValueError, match="[Pp]rice"):
        engine.get_comprehensive_valuation("XYZ", fundamental_data=dict(BASE))


def test_no_result_is_ever_anchored_on_the_10000_default(engine):
    """Guards the specific fabricated anchor that motivated this."""
    try:
        res = engine.get_comprehensive_valuation("XYZ", fundamental_data=dict(BASE))
    except ValueError:
        return  # correct: refused rather than fabricated
    pytest.fail(f"engine fabricated a price and returned {res.current_price}")


def test_valid_price_still_works(engine):
    res = engine.get_comprehensive_valuation("XYZ", fundamental_data=dict(BASE, price=25000))
    assert res.current_price == 25000
    assert res.composite_fair_value > 0
    assert len(res.models) == 22
