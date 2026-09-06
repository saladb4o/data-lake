"""The unified record must carry the statement lines the engine looks up.

reconstruct_financial_triangles() reconstructs the balance sheet, income
statement and cash flow and tiers every line. For a long time it published
only the ratios derived from them and dropped the lines themselves, so
ValuationEngine.calculate_all_models() looked up "debt", "cash", "ebit",
"equity" and "revenue", found nothing, resolved all five as imputed, and the
provenance gate refused every per-share model for every symbol.

These tests pin the contract in both directions: the lines are emitted with
the tier of the witness they came from, and a payload with no reported lines
still gets refused. The second half matters as much as the first - the fix
must widen coverage by carrying evidence through, never by relaxing the gate.
"""

import pytest

from services.unified_data_service import reconstruct_financial_triangles
from services.valuation_engine import ValuationEngine, InputResolver

# Every key the engine resolves as a first-choice lookup, paired with the
# internal witness whose tier it must inherit.
LINE_TO_WITNESS = {
    "total_assets": "total_assets",
    "total_liabilities": "total_liabilities",
    "equity": "total_equity",
    "debt": "total_debt",
    "cash": "cash",
    "revenue": "revenue",
    "net_income": "net_income",
    "ebitda": "ebitda",
    "cfo": "cfo",
    "capex": "capex",
    "ebit": "ebit",
}

PRICE = 25_000.0
SHARES = 5_814_785_700


def reported_payload():
    """A TradingView response with every statement line reported, in raw VND."""
    return {
        "close": PRICE,
        "diluted_shares_outstanding_fq": SHARES,
        "total_assets_fq": 178e12,
        "total_liabilities_fq": 104e12,
        "total_debt_fq": 85.824e12,
        "cash_n_short_term_invest_fq": 14.644e12,
        "total_revenue_ttm": 149e12,
        "net_income_ttm": 34.5e12,
        "ebit_ttm": 40e12,
        "ebitda_ttm": 46e12,
        "cash_f_operating_activities_ttm": 28e12,
        "capital_expenditures_ttm": -12e12,
    }


def unify(tv, vn=None, price=PRICE):
    return reconstruct_financial_triangles(
        "TEST", price, price * 1e8, "STEEL", tv, vn or {}, {}
    )


@pytest.fixture(scope="module")
def reported_record():
    return unify(reported_payload())


@pytest.mark.parametrize("line", sorted(LINE_TO_WITNESS))
def test_line_is_emitted(reported_record, line):
    assert line in reported_record, (
        f"{line!r} is reconstructed internally but never published, so the "
        f"engine cannot see it"
    )
    assert isinstance(reported_record[line], float)


@pytest.mark.parametrize("line,witness", sorted(LINE_TO_WITNESS.items()))
def test_line_carries_its_witness_tier(reported_record, line, witness):
    tiers = reported_record["field_provenance"]
    assert tiers.get(line) == tiers.get(witness), (
        f"{line!r} must inherit the tier of {witness!r}; publishing it "
        f"untiered would let a reconstruction read as an observation"
    )


@pytest.mark.parametrize("line", sorted(LINE_TO_WITNESS))
def test_reported_line_clears_the_gate(reported_record, line):
    tier = reported_record["field_provenance"].get(line)
    assert tier >= InputResolver.MIN_TRUSTED_UPSTREAM_TIER, (
        f"{line!r} came straight from a reported statement and landed at "
        f"tier {tier}"
    )


def test_lines_are_raw_vnd_not_billions(reported_record):
    # The engine derives market cap internally as price * shares (raw VND).
    # A line published in billions would be off by 1e9 and quietly produce
    # fair values a billion times wrong rather than an error.
    assert reported_record["equity"] > 1e12
    assert reported_record["debt"] > 1e12


def test_reported_payload_unlocks_the_model_suite(reported_record):
    record = dict(reported_record, symbol="TEST", price=PRICE, sector_code="STEEL")
    models = ValuationEngine().calculate_all_models("TEST", record)
    active = [m for m in models if m.active]
    assert len(active) >= 5, (
        f"only {len(active)} of {len(models)} models published from a fully "
        f"reported balance sheet; blocked drivers: "
        f"{sorted({d for m in models for d in (m.diagnostics or {}).get('imputed_drivers', [])})}"
    )


def test_empty_payload_is_still_refused():
    """Coverage must come from evidence, never from a looser gate."""
    engine = ValuationEngine()
    for price in (10_000.0, 40_000.0, 80_000.0):
        record = unify({"close": price}, price=price)
        record.update(symbol="TEST", price=price, sector_code="STEEL")
        models = engine.calculate_all_models("TEST", record)
        assert sum(1 for m in models if m.active) == 0, (
            "a payload with nothing reported produced a valuation; the only "
            "thing it can be a function of is the price being judged"
        )


def test_ebit_is_not_back_solved_from_a_sector_margin():
    """No reported operating line means no ebit, not a plausible-looking one."""
    tv = reported_payload()
    tv.pop("ebit_ttm")
    tv.pop("ebitda_ttm")
    record = unify(tv)
    tier = record["field_provenance"].get("ebit")
    assert tier is None or tier >= InputResolver.MIN_TRUSTED_UPSTREAM_TIER, (
        "ebit was invented from revenue times a sector margin and published "
        "as if it were trustworthy"
    )


# ---------------------------------------------------------------------------
# The second layer.
#
# reconstruct_financial_triangles() publishing the lines is not enough:
# normalize_stock_data() builds the screener record, and it used to rebuild it
# from a hand-written list of ratio keys and bury the provenance inside
# "_metadata". Both were dropped a second time, one layer further down. These
# tests pin the record the snapshot is actually written from.
# ---------------------------------------------------------------------------

from services.unified_data_service import normalize_stock_data


def reported_record_via_normalize():
    tv = dict(reported_payload(), market_cap_basic=145.369e12)
    return normalize_stock_data(
        "TEST", "HOSE", "Test", "VNMAT", "Vat lieu",
        tv_data=tv, enable_source0_fallback=False,
    )


@pytest.fixture(scope="module")
def screener_record():
    return reported_record_via_normalize()


def test_provenance_is_at_the_top_level(screener_record):
    # InputResolver reads data["field_provenance"], not data["_metadata"].
    assert isinstance(screener_record.get("field_provenance"), dict)
    assert isinstance(screener_record.get("is_imputed"), dict)


@pytest.mark.parametrize("line", sorted(set(LINE_TO_WITNESS) | {"shares_out"}))
def test_screener_record_carries_the_line(screener_record, line):
    assert line in screener_record, (
        f"{line!r} survives reconstruct_financial_triangles() but is dropped "
        f"again by normalize_stock_data()"
    )
    assert screener_record["field_provenance"].get(line) is not None


def test_market_cap_units_are_not_overloaded(screener_record):
    """The record publishes market cap twice, in two units, on purpose.

    "market_cap" is billions and feeds the screener UI. The engine works in
    raw VND. Reading the billions figure as VND understates every
    enterprise-value model by 1e9 and raises nothing.
    """
    assert screener_record["market_cap_vnd"] == pytest.approx(
        screener_record["market_cap"] * 1e9
    )
    assert screener_record["field_provenance"].get("market_cap_vnd") is not None
    engine_mcap = screener_record["price"] * screener_record["shares_out"]
    assert screener_record["market_cap_vnd"] == pytest.approx(engine_mcap, rel=0.02)


def test_screener_record_unlocks_its_sector_full_house(screener_record):
    record = dict(screener_record)
    models = ValuationEngine().calculate_all_models("TEST", record)
    active = [m for m in models if m.active]
    assert len(active) >= 5, (
        f"only {len(active)} models published from a fully reported screener "
        f"record; blocked: "
        f"{sorted({d for m in models for d in (m.diagnostics or {}).get('imputed_drivers', [])})}"
    )


def test_screener_record_with_only_a_price_is_refused():
    engine = ValuationEngine()
    for price in (10_000.0, 40_000.0, 80_000.0):
        record = normalize_stock_data(
            "TEST", "HOSE", "Test", "VNMAT", "Vat lieu",
            tv_data={"close": price}, enable_source0_fallback=False,
        )
        models = engine.calculate_all_models("TEST", record)
        assert sum(1 for m in models if m.active) == 0, (
            "a record built from nothing but a price produced a valuation"
        )
