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
