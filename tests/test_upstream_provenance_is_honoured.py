"""A number that is present is not thereby a number that was observed.

`services.unified_data_service.reconstruct_financial_triangles` back-solves a
missing EPS, revenue or equity from market capitalisation and a sector
multiple. Market cap is price times shares, so those values are the price
tautology one layer up: every model fed them returns a fixed multiple of the
price it is supposed to judge.

The data layer is honest about it - it ships `is_imputed` and per-field
`field_provenance` tiers alongside the values. The valuation engine was not
reading them, so a tier-1 EPS arrived as a plain float and `InputResolver`
recorded it as REAL. These tests pin the fix: the payload's own verdict wins.
"""

from __future__ import annotations

import pytest

from services.valuation_engine import (
    IMPUTED,
    REAL,
    InputResolver,
    ValuationEngine,
)

RECONSTRUCTED_KEYS = ("eps", "bvps", "revenue", "net_income", "total_equity")


def _payload(price: float, *, flagged: bool) -> dict:
    """A symbol whose statements were back-solved from its own market cap."""
    shares = 1e9
    mcap = price * shares
    data = {
        "symbol": "TEST", "sector_code": "VNIND",
        "price": price, "current_price": price,
        "shares_out": shares, "market_cap": mcap,
        "eps": mcap / 12.0 / shares,
        "bvps": mcap / 1.5 / shares,
        "revenue": mcap / 0.9,
        "net_income": mcap / 12.0,
        "total_equity": mcap / 1.5,
        "roe": 15.0,
    }
    if flagged:
        data["is_imputed"] = {k: True for k in RECONSTRUCTED_KEYS}
        data["field_provenance"] = {k: 1 for k in RECONSTRUCTED_KEYS}
    return data


# --------------------------------------------------------------------------
# InputResolver
# --------------------------------------------------------------------------

def test_is_imputed_flag_overrides_a_present_value():
    r = InputResolver({"eps": 2500.0, "is_imputed": {"eps": True}})
    assert r.resolve("eps", ("eps",)) == 2500.0
    assert r.provenance["eps"] == IMPUTED
    assert not r.trustworthy("eps")


def test_low_provenance_tier_overrides_a_present_value():
    r = InputResolver({"eps": 2500.0, "field_provenance": {"eps": 1}})
    r.resolve("eps", ("eps",))
    assert r.provenance["eps"] == IMPUTED


@pytest.mark.parametrize("tier,expected", [
    (4, REAL),      # audited primary filing
    (3, REAL),      # vendor reported
    (2, REAL),      # triangulated from other reported lines
    (1, IMPUTED),   # sector-median stand-in
    (0, IMPUTED),   # fabricated
])
def test_tier_boundary(tier, expected):
    r = InputResolver({"eps": 2500.0, "field_provenance": {"eps": tier}})
    r.resolve("eps", ("eps",))
    assert r.provenance["eps"] == expected


def test_a_payload_with_no_provenance_still_resolves_as_real():
    """Absence of a flag is not evidence a value was invented."""
    r = InputResolver({"eps": 2500.0})
    r.resolve("eps", ("eps",))
    assert r.provenance["eps"] == REAL


def test_flags_are_per_field_not_per_payload():
    r = InputResolver({
        "eps": 2500.0, "bvps": 18000.0,
        "field_provenance": {"eps": 3, "bvps": 1},
    })
    r.resolve("eps", ("eps",))
    r.resolve("bvps", ("bvps",))
    assert r.provenance["eps"] == REAL
    assert r.provenance["bvps"] == IMPUTED


def test_malformed_provenance_metadata_is_ignored_not_fatal():
    for bad in ("not-a-dict", 42, [], None):
        r = InputResolver({"eps": 2500.0, "is_imputed": bad, "field_provenance": bad})
        r.resolve("eps", ("eps",))
        assert r.provenance["eps"] == REAL


def test_imputation_propagates_to_a_derivation():
    r = InputResolver({
        "net_income": 5e11, "shares_out": 1e9,
        "is_imputed": {"net_income": True},
    })
    r.resolve("net_income", ("net_income",))
    r.resolve("shares_out", ("shares_out",))
    eps = r.resolve(
        "eps", ("eps",),
        derive=(("net_income", "shares_out"), lambda: 5e11 / 1e9),
    )
    assert eps == 500.0
    assert r.provenance["eps"] == IMPUTED, "derived from an imputed input"


# --------------------------------------------------------------------------
# End to end: the tautology must not come back through the payload
# --------------------------------------------------------------------------

def _composite(price: float, *, flagged: bool) -> float:
    engine = ValuationEngine()
    data = _payload(price, flagged=flagged)
    models = engine.calculate_all_models("TEST", data)
    return engine.calculate_composite_fair_value(models, "VNIND")


PRICES = (10_000.0, 20_000.0, 40_000.0, 80_000.0)


def test_unflagged_reconstruction_is_a_fixed_multiple_of_price():
    """Documents the defect, so the fix below is measured against it.

    With no provenance metadata the engine cannot know the inputs came from
    the price, and the composite tracks price exactly - which is why the
    metadata has to be read.
    """
    ratios = [_composite(p, flagged=False) / p for p in PRICES]
    spread = max(ratios) - min(ratios)
    assert spread < 0.001, f"expected a fixed multiple, got {ratios}"


@pytest.mark.parametrize("price", PRICES)
def test_flagged_reconstruction_produces_no_valuation(price):
    """The honest answer for accounts back-solved from the price is none."""
    assert _composite(price, flagged=True) == 0.0


def test_no_model_stays_active_on_reconstructed_inputs():
    engine = ValuationEngine()
    data = _payload(40_000.0, flagged=True)
    models = engine.calculate_all_models("TEST", data)
    active = [m.model_id for m in models if m.active]
    assert not active, f"models valued price-derived inputs: {active}"


def test_the_suppression_says_which_drivers_were_imputed():
    """A refusal has to be diagnosable, not just empty."""
    engine = ValuationEngine()
    data = _payload(40_000.0, flagged=True)
    models = engine.calculate_all_models("TEST", data)
    reported = {
        d
        for m in models
        for d in (m.diagnostics or {}).get("imputed_drivers", [])
    }
    assert reported & set(RECONSTRUCTED_KEYS), (
        f"no model named its imputed drivers; saw {reported}"
    )


def test_real_filings_still_value_normally():
    """The guard must not refuse a symbol whose statements are reported."""
    engine = ValuationEngine()
    data = _payload(40_000.0, flagged=False)
    data["field_provenance"] = {k: 3 for k in RECONSTRUCTED_KEYS}
    data["is_imputed"] = {k: False for k in RECONSTRUCTED_KEYS}
    models = engine.calculate_all_models("TEST", data)
    assert [m for m in models if m.active], "reported filings were refused"


# --------------------------------------------------------------------------
# Calibration: the gate must refuse reconstruction without blanking the app
# --------------------------------------------------------------------------

def test_tier_wins_over_the_coarser_boolean():
    """upstream builds is_imputed as `tier < 3`, which lumps tier 2 in with 1.

    Reading the boolean first would refuse every balance sheet whose equity
    came from assets minus liabilities - a bookkeeping identity, not a guess -
    and that is a large share of a real universe. The tier is the finer signal
    and wins wherever it exists.
    """
    payload = {
        "eps": 2500.0,
        "field_provenance": {"eps": 2},
        "is_imputed": {"eps": True},   # exactly what the module emits for tier 2
    }
    r = InputResolver(payload)
    r.resolve("eps", ("eps",))
    assert r.provenance["eps"] == REAL


def test_boolean_still_applies_when_no_tier_is_given():
    payload = {"eps": 2500.0, "is_imputed": {"eps": True}}
    r = InputResolver(payload)
    r.resolve("eps", ("eps",))
    assert r.provenance["eps"] == IMPUTED


def _valued_at(tier: int) -> int:
    """Active model count for a payload whose every field carries `tier`."""
    engine = ValuationEngine()
    data = _payload(40_000.0, flagged=False)
    fields = [k for k in data if k not in ("symbol", "sector_code")]
    data["field_provenance"] = {k: tier for k in fields}
    data["is_imputed"] = {k: tier < 3 for k in fields}
    return len([m for m in engine.calculate_all_models("TEST", data) if m.active])


@pytest.mark.parametrize("tier", [4, 3, 2])
def test_evidence_grade_data_is_still_valued(tier):
    """The gate must not blank out a universe built from real filings."""
    assert _valued_at(tier) > 0, f"tier {tier} produced no valuation at all"


@pytest.mark.parametrize("tier", [1, 0])
def test_reconstructed_data_is_refused(tier):
    assert _valued_at(tier) == 0, f"tier {tier} was valued despite being invented"


def test_the_cut_sits_between_one_and_two():
    """Pins the boundary itself, so moving it has to be deliberate."""
    assert InputResolver.MIN_TRUSTED_UPSTREAM_TIER == 2
    assert _valued_at(2) > 0 and _valued_at(1) == 0
