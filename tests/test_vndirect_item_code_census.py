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
                assert key != "income_statement_ttm_by_code"
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


class TestTheNamesComeFromThePayload:
    """The census was going to name item codes out of data/financial_models.json.

    Nothing in this repository writes that file and data/*.json is gitignored,
    so it may not exist wherever the sync runs - and a census that prints
    thirty codes with no names against them answers nothing. The vendor names
    its own line items in every row it sends; read them from there.
    """

    def test_the_parser_takes_the_name_from_the_row(self):
        src = inspect.getsource(uds.fetch_vndirect_financials)
        assert "name_lookup" in src
        assert "it.get('itemName')" in src
        assert '"item_code_names": name_lookup' in src

    def test_the_census_prefers_the_vendor_name_over_the_local_catalogue(self):
        src = inspect.getsource(uds.sync_unified_screener_universe)
        block = src[src.index("def _name_of"):]
        block = block[:block.index("return \"(unnamed")]
        vendor = block.index("vendor_names[code]")
        catalogue = block.index("_FINANCIAL_MODELS_BY_CODE")
        assert vendor < catalogue, (
            "the local catalogue must be the second opinion, not the first"
        )

    def test_a_missing_catalogue_is_not_fatal(self):
        """The import is guarded: an absent catalogue degrades the census,
        it does not stop the sync."""
        src = inspect.getsource(uds.sync_unified_screener_universe)
        block = src[src.index("vendor_names: Dict"):src.index("def _name_of")]
        assert "try:" in block and "except Exception:" in block

    def test_the_names_are_never_read_as_numbers(self):
        src = inspect.getsource(uds.sync_unified_screener_universe)
        start = src.index("vendor_names: Dict")
        end = src.index("Compute Empirical Percentiles")
        block = src[start:end]
        for forbidden in ("_safe_float", "float(", "unified_stocks["):
            assert forbidden not in block, (
                f"{forbidden} in the naming block - these are labels, not data"
            )


class TestTheCodesAreIdentifiedByArithmeticNotByName:
    """The census ran and the vendor named none of its own codes: the log
    printed thirty item codes and "vendor named 0 of these codes".

    So no lookup can say which line is the operating one. Two lines are
    known anyway - the extractor already reads revenue at 21001 and net
    income at 23000 and gets sensible numbers for hundreds of companies -
    and that is enough to identify the rest by what their values do,
    rather than by guessing at a numbering scheme. Guessing is how
    [21020, 22000] got into the extractor, and neither code appears in
    any payload the vendor sent.
    """

    def test_the_parser_carries_the_income_statement_values(self):
        src = inspect.getsource(uds.fetch_vndirect_financials)
        assert '"income_statement_ttm_by_code"' in src
        # Income statement only: a probe that swept the balance sheet and
        # cash flow too would carry most of the payload around for nothing.
        assert "20000 <= c < 30000" in src

    def test_the_probe_searches_rather_than_proposing_a_reading(self):
        """The first version stated four identities under one reading of
        the numbering. All four came back at 0.0% - the reading was wrong,
        and it was wrong in the log rather than in a published valuation,
        which is exactly what stating them was for.

        The ratio table did settle three codes on its own: 21000 and 21001
        at 1.000 x revenue, 22100 at 0.859 and 23100 at 0.144, summing to
        1.003 - cost of goods and gross profit, identified by what the
        numbers do. So the probe now searches for the relations instead of
        proposing them: no hard-coded reading survives here to be wrong.
        """
        src = inspect.getsource(uds.sync_unified_screener_universe)
        block = src[src.index("code_census"):src.index("Compute Empirical Percentiles")]
        assert "searched" in block
        # No proposed reading may be hard-coded: those are the numbers that
        # were wrong, and the anchors are named in prose, not in a formula.
        for guess in ("21900 = 21001", "22200 = 21900", "22500 = 22200",
                      "22900 = 22500"):
            assert guess not in block

    def test_the_search_reports_a_hit_rate_and_a_sample_size(self):
        """A relation that holds for four companies is coincidence. The
        rate and the n are what separate that from the statement's own
        structure, so neither may be dropped from the output."""
        src = inspect.getsource(uds.sync_unified_screener_universe)
        block = src[src.index("recover_item_code_relations"):
                    src.index("Compute Empirical Percentiles")]
        assert "{rate:5.1f}%" in block and "(n={n})" in block

    def test_the_search_lives_where_it_can_be_tested(self):
        """It was written inline in a 400-line sync function, where the
        only thing a test could check was the text of the source. It is a
        function now, and tests/test_item_code_relations.py checks what it
        actually recovers."""
        assert callable(getattr(uds, "recover_item_code_relations", None))

    def test_a_coefficient_that_is_not_whole_is_shown_as_it_is(self):
        """No line of a statement is 0.83 of another line, so a fractional
        coefficient is the log saying "this is not a line". Rounding it to
        1 would erase exactly that signal."""
        src = inspect.getsource(uds.sync_unified_screener_universe)
        block = src[src.index("recover_item_code_relations"):
                    src.index("Compute Empirical Percentiles")]
        assert "abs(abs(b) - 1.0) < 0.02" in block
        assert "{abs(b):.3f}*" in block

    def test_the_probe_only_prints(self):
        """The same invariant as the census: identifying a code is a
        measurement. Acting on the identification is a separate change,
        made once the log says the reading holds."""
        src = inspect.getsource(uds.sync_unified_screener_universe)
        block = src[src.index("by_code_rows"):src.index("Compute Empirical Percentiles")]
        for forbidden in ("unified_stocks[", "field_provenance", "ebit_ttm =",
                          "_absolute_lines", "rec["):
            assert forbidden not in block

    def test_the_values_do_not_reach_a_published_record(self):
        """Covered for the code list by test_the_codes_do_not_reach_a_
        published_record; pinned here for the values, which are numbers and
        so would be far easier to read by accident."""
        src = inspect.getsource(uds.fetch_vndirect_financials)
        assert "Diagnostic only" in src or "never read as a number" in src
