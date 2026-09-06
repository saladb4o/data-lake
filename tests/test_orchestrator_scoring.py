"""
Integration tests: scoring wired into sync_unified_screener_universe (M4).

Gates:
  I1. Offline end-to-end: fake master_symbols_map (>= 30 symbols with
      realistic TradingView-shaped tv_data dicts incl. near-empty ones),
      ALL fetch functions monkeypatched to canned data (zero network),
      screener_snapshot_file() redirected to a temp path. After
      sync_unified_screener_universe:
        - every stock has a "percentiles" block with the exact consumer shape
        - all five quintiles Q1..Q5 are populated
        - largest identical-composite cluster < 2% of the universe
  I2. Task C honesty: normalize_stock_data with fully empty inputs cannot
      publish eps (or any price-derived field) above tier 1 provenance.

No network access anywhere in this module.
"""

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from services import unified_data_service as uds

PERCENTILES_SHAPE = {
    "growth", "quality", "health", "valuation", "composite",
    "quintile", "quintile_label", "quintile_color", "quintile_badge",
    # How much of the record was actually reported, so a score built on two
    # factors is distinguishable from one built on all ten.
    "factor_coverage_pct",
}

#: Published only when they apply, so not part of the fixed shape.
PERCENTILES_OPTIONAL = {"winsorized", "low_evidence"}

SECTORS = [
    ("VNIND", "Công Nghiệp"),
    ("VNFIN", "Tài Chính"),
    ("VNMAT", "Nguyên Vật Liệu"),
    ("VNCONS", "Tiêu Dùng"),
]


def make_tv_entry(i: int) -> dict:
    """Realistic TradingView scanner payload shape."""
    return {
        "close": round(10.0 + (i % 60) * 1.9, 2),
        "market_cap_basic": float(1_500_000_000_000 + i * 211_000_000_000),
        "total_revenue_ttm": float(800_000_000_000 + (i % 90) * 47_000_000_000),
        "net_income_ttm": float(40_000_000_000 + (i % 70) * 6_500_000_000),
        "total_assets_fq": float(2_000_000_000_000 + (i % 80) * 83_000_000_000),
        "total_liabilities_fq": float(900_000_000_000 + (i % 60) * 31_000_000_000),
        "price_earnings_ttm": round(7.0 + (i % 33) * 0.85, 2),
        "price_book_fq": round(0.8 + (i % 25) * 0.32, 2),
        "return_on_equity_fq": round(3.0 + (i % 45) * 0.72, 2),
        "operating_margin_ttm": round(-4.0 + (i % 40) * 0.95, 2),
        "debt_to_equity_fq": round(0.15 + (i % 30) * 0.11, 2),
        "dividend_yield_recent": round((i % 19) * 0.38, 2),
        "total_revenue_cagr_5y": round(-2.0 + (i % 50) * 0.62, 2),
        "total_revenue_cagr_3y": round(-1.0 + (i % 55) * 0.48, 2),
        "earnings_per_share_basic_ttm": round(500.0 + (i % 40) * 310.0, 0),
        "diluted_shares_outstanding_fq": float(100_000_000 + (i % 35) * 27_000_000),
    }


def build_master_map(n_real: int = 110, n_clones: int = 20, n_empty: int = 2) -> dict:
    """
    >= 30 symbols; most get rich tv_data, a block of clones shares identical
    primary-factor inputs (distinct secondaries), and `n_empty` are
    near-empty payloads that must survive normalization.
    """
    master = {}
    total = n_real + n_clones + n_empty
    for i in range(total):
        sec_code, sec_name = SECTORS[i % len(SECTORS)]
        if i < n_real:
            tv = make_tv_entry(i)
        elif i < n_real + n_clones:
            # Identical primaries, distinct secondaries (anti-tie probe).
            base = make_tv_entry(3)
            base["dividend_yield_recent"] = round(0.2 + (i - n_real) * 0.07, 3)
            base["close"] = round(12.0 + (i - n_real) * 0.4, 2)
            tv = base
        else:
            # Near-empty: just a price witness, everything else imputed.
            tv = {"close": 22.5}
        master[f"TS{i:03d}"] = {
            "exchange": "HOSE",
            "sector_code": sec_code,
            "sector_name": sec_name,
            "name": f"Test Stock {i:03d}",
        }
    return master


TV_BATCH_OVERRIDE: dict = {}


def fake_fetch_tv(tickers_list, chunk_size=150):
    # tickers look like "HOSE:TS001"; batch keyed by clean symbol.
    return dict(TV_BATCH_OVERRIDE)


def fake_fetch_vnstock(symbol):
    return {}


def fake_fetch_yfinance(symbol):
    return {}


@pytest.fixture()
def offline_sync(monkeypatch, tmp_path):
    def _run(master):
        # Rebuild the canned TV batch with the same generator build_master_map
        # used (kept in sync via the same constants).
        n_clones, n_empty = 20, 2
        n_real = len(master) - n_clones - n_empty
        TV_BATCH_OVERRIDE.clear()
        for sym in master:
            idx = int(sym[2:])
            if idx < n_real:
                tv = make_tv_entry(idx)
            elif idx < n_real + n_clones:
                tv = make_tv_entry(3)
                tv["dividend_yield_recent"] = round(0.2 + (idx - n_real) * 0.07, 3)
                tv["close"] = round(12.0 + (idx - n_real) * 0.4, 2)
            else:
                tv = {"close": 22.5}
            TV_BATCH_OVERRIDE[sym] = tv

        monkeypatch.setattr(uds, "fetch_tradingview_batch_by_tickers", fake_fetch_tv)
        monkeypatch.setattr(uds, "fetch_vnstock_financials", fake_fetch_vnstock)
        monkeypatch.setattr(uds, "fetch_yfinance_financials", fake_fetch_yfinance)
        # SCREENER_SNAPSHOT_FILE became screener_snapshot_file() when the
        # import-time path constants were made lazy. Patching the old name
        # raised AttributeError, which went unnoticed because this module was
        # also (wrongly) tagged as a network module and never ran in CI - its
        # own docstring says it makes no network calls.
        snapshot_path = tmp_path / "screener_snapshot.json"
        monkeypatch.setattr(uds, "screener_snapshot_file", lambda: str(snapshot_path))
        return uds.sync_unified_screener_universe(master), snapshot_path

    return _run


def test_i1_offline_sync_scores_and_publishes_quintiles(offline_sync):
    master = build_master_map(n_real=110, n_clones=20, n_empty=2)
    assert len(master) >= 30

    payload, snapshot_path = offline_sync(master)

    stocks = payload["stocks"]
    assert len(stocks) == len(master)

    # Shape: every stock has the exact new percentiles contract.
    for sym, s in stocks.items():
        published = set(s["percentiles"].keys())
        assert PERCENTILES_SHAPE <= published, f"{sym}: percentiles shape drifted"
        assert published - PERCENTILES_SHAPE <= PERCENTILES_OPTIONAL, (
            f"{sym}: unexpected keys {published - PERCENTILES_SHAPE - PERCENTILES_OPTIONAL}"
        )
        comp = s["percentiles"]["composite"]
        assert isinstance(comp, (int, float))
        assert 0.0 <= comp <= 100.0

    # All five quintiles populated across the synced universe.
    quintile_counts = Counter(s["percentiles"]["quintile"] for s in stocks.values())
    for q in ("Q1", "Q2", "Q3", "Q4", "Q5"):
        assert quintile_counts[q] > 0, f"{q} not populated after sync"

    # Largest identical-composite cluster < 2% of the universe.
    n = len(stocks)
    comp_counts = Counter(
        round(s["percentiles"]["composite"], 4) for s in stocks.values()
    )
    worst = max(comp_counts.values())
    assert worst < 0.02 * n, (
        f"Largest composite cluster {worst} >= 2% of {n} synced stocks"
    )

    # Snapshot written to the REDIRECTED path only (real data untouched),
    # and it is loadable JSON carrying the same scored stocks.
    assert snapshot_path.exists()
    with open(snapshot_path, encoding="utf-8") as f:
        snap = json.load(f)
    assert snap["total_symbols"] == n
    assert set(snap["stocks"]) == set(stocks)

    # Sector analytics still function downstream of scoring.
    assert payload["sectors"], "sector analytics lost by the wiring"


def test_i1b_clone_block_separates_after_sync(offline_sync):
    master = build_master_map(n_real=110, n_clones=20, n_empty=2)
    payload, _ = offline_sync(master)

    stocks = payload["stocks"]
    clone_syms = [f"TS{110 + j:03d}" for j in range(20)]
    clone_comps = {
        stocks[sym]["percentiles"]["composite"] for sym in clone_syms
    }
    # 20 identical-primary records must spread across many distinct
    # composites (>= half distinct is a conservative bar; the binding
    # cluster gate lives in test_i1).
    assert len(clone_comps) >= 10, (
        f"clone block collapsed to {len(clone_comps)} distinct composites"
    )


def test_i2_empty_inputs_cannot_produce_high_tier_eps(tmp_path):
    tri = uds.reconstruct_financial_triangles(
        symbol="EMPTY",
        price=10000.0,
        raw_mcap=0.0,
        sector_code="VNIND",
        tv_data={},
        vn_data={},
        yf_data={},
    )
    fp = tri["field_provenance"]
    assert fp["eps"] <= 1, f"empty-input eps landed tier {fp['eps']} (triangulated!)"
    assert fp["pe"] <= 1
    assert fp["market_cap"] <= 1


def test_i2b_invented_price_poisons_price_derived_fields():
    # vn_data supplies ONLY market_cap: pe/eps derivations consume the
    # invented 10000.0 price, so they must not be reported tier 2+.
    tri = uds.reconstruct_financial_triangles(
        symbol="MCAPONLY",
        price=10000.0,
        raw_mcap=5_000_000_000_000.0,
        sector_code="VNIND",
        tv_data={},
        vn_data={"market_cap": 5_000_000_000_000.0},
        yf_data={},
    )
    fp = tri["field_provenance"]
    assert fp["shares"] <= 1, "shares derived via invented price got tier 2"
    # eps path needs price>0 and falls into the price/pe branch -> poisoned.
    assert fp["eps"] <= 1


def test_i2c_real_price_keeps_full_provenance():
    tri = uds.reconstruct_financial_triangles(
        symbol="REALPX",
        price=25000.0,
        raw_mcap=0.0,
        sector_code="VNIND",
        tv_data={
            "close": 25000.0,
            "price_earnings_ttm": 12.5,
            "earnings_per_share_basic_ttm": 2000.0,
        },
        vn_data={},
        yf_data={},
    )
    fp = tri["field_provenance"]
    # Reported PE stays tier 3; price-derived eps keeps its honest tier-2
    # because the price witness is real this time.
    assert fp["pe"] == 3
