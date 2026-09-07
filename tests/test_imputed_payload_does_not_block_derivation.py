"""A tier-1 stand-in in the payload must not shoulder aside a real derivation.

``InputResolver.resolve`` returned any present value immediately, before the
``derive`` branch. So a field the upstream layer had back-solved from market
cap - present, concrete, and flagged tier 1 - kept the derivation from ever
running, even when every dependency it needed was reported. The engine had
the arithmetic and the observations and still recorded the answer as invented.

These tests pin the ordering: a derivation over trustworthy dependencies wins
over an imputed payload value, and nothing else about resolution changes.
"""

import math

import pytest

from services.valuation_engine import DERIVED, IMPUTED, REAL, InputResolver


NET_INCOME = 8.0e11
SHARES = 4.0e8


def _resolver(**over):
    data = {
        "net_income": NET_INCOME,
        "shares_out": SHARES,
        # The stand-in: present, plausible, and back-solved from market cap.
        "eps": 123.0,
        "field_provenance": {"net_income": 3, "shares_out": 3, "eps": 1},
    }
    data.update(over)
    return InputResolver(data)


def _resolve_eps(res):
    shares = res.resolve("shares", ("shares_out",), require_positive=True)
    net_income = res.resolve("net_income", ("net_income",))
    return res.resolve(
        "eps", ("eps",),
        derive=(("net_income", "shares"), lambda: net_income / shares),
        impute=lambda: 0.0,
    )


def test_the_derivation_replaces_the_stand_in():
    res = _resolver()
    assert _resolve_eps(res) == pytest.approx(NET_INCOME / SHARES)
    assert res.provenance["eps"] == DERIVED


def test_the_stand_in_value_is_not_what_is_returned():
    res = _resolver()
    assert _resolve_eps(res) != 123.0


def test_a_reported_value_still_wins_over_the_derivation():
    """The fix must not start recomputing fields the vendor actually reports."""
    res = _resolver(field_provenance={"net_income": 3, "shares_out": 3, "eps": 3})
    assert _resolve_eps(res) == 123.0
    assert res.provenance["eps"] == REAL


def test_the_stand_in_is_kept_when_the_dependencies_are_no_better():
    """Nothing is gained by deriving from numbers that are themselves invented,
    so the payload value is kept - imputed, exactly as it was before."""
    res = _resolver(field_provenance={"net_income": 1, "shares_out": 3, "eps": 1})
    assert _resolve_eps(res) == 123.0
    assert res.provenance["eps"] == IMPUTED


def test_an_absent_field_still_derives():
    res = _resolver()
    res._data.pop("eps")
    assert _resolve_eps(res) == pytest.approx(NET_INCOME / SHARES)
    assert res.provenance["eps"] == DERIVED


def test_an_absent_field_with_bad_dependencies_still_imputes():
    res = _resolver(field_provenance={"net_income": 1, "shares_out": 3})
    res._data.pop("eps")
    assert res.provenance.get("eps") is None
    _resolve_eps(res)
    assert res.provenance["eps"] == IMPUTED


def test_require_positive_still_rejects_a_non_positive_payload_value():
    res = _resolver(shares_out=0.0)
    shares = res.resolve("shares", ("shares_out",),
                         impute=lambda: 1e8, require_positive=True)
    assert shares == 1e8
    assert res.provenance["shares"] == IMPUTED


def test_a_field_with_no_derive_keeps_its_imputed_payload_value():
    res = _resolver()
    assert res.resolve("eps", ("eps",), impute=lambda: 7.0) == 123.0
    assert res.provenance["eps"] == IMPUTED


def test_a_derivation_returning_a_non_finite_number_falls_through():
    res = _resolver(shares_out=SHARES)
    res.resolve("shares", ("shares_out",), require_positive=True)
    res.resolve("net_income", ("net_income",))
    got = res.resolve("eps", ("eps",),
                      derive=(("net_income", "shares"), lambda: math.nan),
                      impute=lambda: 7.0)
    assert got == 123.0
    assert res.provenance["eps"] == IMPUTED


def test_a_payload_with_no_provenance_map_is_untouched():
    """A plain dict of numbers must still resolve to REAL exactly as before."""
    res = InputResolver({"eps": 123.0, "net_income": NET_INCOME, "shares_out": SHARES})
    assert _resolve_eps(res) == 123.0
    assert res.provenance["eps"] == REAL
