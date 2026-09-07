"""The EBIT census said VNDIRECT answered for 619 symbols with no operating
line and not one carried an ebit_ttm - while the same payloads supplied
revenue, net income, assets and equity. Statements that complete cannot be
missing their operating line; the extractor reads itemCodes [21020, 22000]
and those are evidently not where this vendor puts it.

So the payload now reports which itemCodes it actually carries, and the sync
names them against the itemName catalogue. These tests pin that this is a
measurement and nothing more: the codes must not reach a published record,
and no valuation input may be computed from them.
"""

import inspect

import pytest

from services import unified_data_service as uds


def test_the_parser_reports_the_codes_it_saw():
    src = inspect.getsource(uds.fetch_vndirect_financials)
    assert '"available_item_codes": sorted(val_lookup.keys())' in src


def test_the_census_reads_only_payloads_already_fetched():
    """It must not cost a round of requests: the whole point of keeping the
    codes on the parsed payload is that the sync can count them for free."""
    src = inspect.getsource(uds.sync_unified_screener_universe)
    start = src.index("code_census")
    end = src.index("Compute Empirical Percentiles")
    census_block = src[start:end]
    for caller in ("fetch_vndirect_financials", "_request_with_retry",
                   "requests.", "ThreadPoolExecutor"):
        assert caller not in census_block, f"the census must not call {caller}"


def test_the_codes_do_not_reach_a_published_record():
    """A record is a valuation input. A diagnostic list of vendor item codes
    is not, and must not be able to be read as one."""
    tv = {
        "close": 25_000.0,
        "diluted_shares_outstanding_fq": 1e9,
        "total_revenue_ttm": 149e12,
        "net_income_ttm": 34.5e12,
        "total_equity_fq": 74e12,
    }
    vnd = {
        "revenue_ttm": 149e12,
        "net_income_ttm": 34.5e12,
        "available_item_codes": [21001, 22000, 23000],
    }
    rec = uds.normalize_stock_data(
        "TST", tv_data=tv, vndirect_data=vnd, sector_code="VNIND",
    )
    assert "available_item_codes" not in rec

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert key != "available_item_codes"
                _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)

    _walk(rec)


def test_the_census_writes_nothing_back():
    """The invariant that matters: counting vendor item codes must never
    become a source of a number the valuation engine reads. It may print;
    it may not assign into a record, a provenance map or a statement line."""
    src = inspect.getsource(uds.sync_unified_screener_universe)
    start = src.index("code_census")
    end = src.index("Compute Empirical Percentiles")
    block = src[start:end]
    for forbidden in (
        "unified_stocks[", "field_provenance", "_absolute_lines",
        "absolute_lines[", "tri[", "rec[",
    ):
        assert forbidden not in block, (
            f"the census assigns into {forbidden} - it is a measurement, "
            "not a source of valuation inputs"
        )
