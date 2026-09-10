"""The lake and the screener read the same company the same way.

scripts/build_historical_fundamentals.py carried its own copy of the
VNDIRECT item codes. Two of those fields were then corrected in the
service on measured evidence - cfo from the operating section's
adjustment lines to its total, debt from total liabilities to borrowings
- and the copy went on reading the old codes.

Nothing would have failed. The lake would simply have held, for the same
company and the same quarter, figures the screener disagrees with, and
because the lake is what the point-in-time backtest values against, the
disagreement would have read as the market being wrong rather than the
extractor. The script has never been run end to end, so the copy was
still only a latent defect when it was found - these tests are what stop
it coming back.
"""
import ast
import inspect
import re

import pytest

import scripts.build_historical_fundamentals as lake
import services.unified_data_service as uds


#: An item code is a five- or six-digit VNDIRECT line number.
_CODE_RANGE = range(10000, 1000000)


def _is_code_list(value: ast.AST) -> bool:
    """True for a list or tuple literal holding item codes."""
    for inner in ast.walk(value):
        if isinstance(inner, (ast.List, ast.Tuple)) and any(
                isinstance(e, ast.Constant) and isinstance(e.value, int)
                and e.value in _CODE_RANGE for e in inner.elts):
            return True
    return False


def _tables_of_item_codes(tree: ast.AST):
    """The names of every dict in `tree` that maps fields to item codes.

    An unnamed one is reported as None: a table nobody assigned is still
    a second table, and being anonymous makes it harder to notice rather
    than less dangerous.
    """
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        if sum(1 for value in node.values if _is_code_list(value)) < 3:
            continue
        names = [
            target.id
            for stmt in ast.walk(tree)
            if isinstance(stmt, (ast.Assign, ast.AnnAssign))
            and getattr(stmt, "value", None) is node
            for target in (stmt.targets if isinstance(stmt, ast.Assign)
                           else [stmt.target])
            if isinstance(target, ast.Name)
        ]
        found.extend(names or [None])
    return found


class TestThereIsOneTable:
    def test_the_lake_reads_the_services_table(self):
        assert lake.VNDIRECT_ITEM_CODES is uds.VNDIRECT_ITEM_CODES

    def test_every_field_the_lake_publishes_comes_from_it(self):
        missing = set(lake.LAKE_FIELDS) - set(uds.VNDIRECT_ITEM_CODES)
        assert not missing, f"{sorted(missing)} are declared nowhere"

    @pytest.mark.parametrize("module", [lake, uds])
    def test_no_module_declares_a_second_map_of_item_codes(self, module):
        """A second dict of item codes anywhere is a new copy.

        This is the actual failure mode - not that someone edits the
        shared table wrongly, but that a second one appears beside it and
        drifts quietly, which is exactly how the lake came to read cfo
        and debt from codes the service had already abandoned.
        """
        tables = _tables_of_item_codes(ast.parse(inspect.getsource(module)))
        assert tables == ["VNDIRECT_ITEM_CODES"] or tables == [], (
            f"{module.__name__} declares {tables}; the one table of item"
            " codes is VNDIRECT_ITEM_CODES")

    def test_the_guard_would_catch_a_copy_coming_back(self):
        """A guard that detects nothing passes exactly like one that works."""
        copy = ast.parse(
            "OTHER_CODES = {\n"
            "    'revenue': [21001, 421900],\n"
            "    'cfo': [31000, 31100],\n"
            "    'debt': [13000, 13100],\n"
            "}\n")
        assert _tables_of_item_codes(copy) == ["OTHER_CODES"]

    def test_the_guard_is_not_tripped_by_ordinary_dicts(self):
        # A dict of results or of small constants must not read as a code
        # table, or the guard gets disabled by whoever it cries wolf at.
        ordinary = ast.parse(
            "res = {'a': assets, 'b': equity, 'c': [1, 2, 3]}\n")
        assert _tables_of_item_codes(ordinary) == []


class TestTheRuleTravelsWithTheCodes:
    """Sharing codes without the rule would hand over the bug intact."""

    def test_borrowings_are_summed_not_chained(self):
        codes, how = uds.VNDIRECT_ITEM_CODES["debt"]
        assert codes == (13110, 13340)
        assert how == "sum", (
            "read as a chain this publishes short-term borrowings as"
            " total debt - smaller than the truth, in a ratio the"
            " screener displays")

    def test_the_lake_adds_a_sum_field_up(self, monkeypatch):
        rows = [
            {"fiscalDate": "2024-03-31", "itemCode": 13110,
             "numericValue": 200.0},
            {"fiscalDate": "2024-03-31", "itemCode": 13340,
             "numericValue": 100.0},
        ]
        monkeypatch.setattr(lake, "_fetch_raw", lambda *a, **k: rows)
        quarters = lake.build_symbol("TEST")
        assert quarters["2024-Q1"]["debt"] == 300.0, (
            "300 is the sum; 200 means the codes were walked as"
            " alternatives and the first one won")

    def test_the_lake_falls_through_a_first_field(self, monkeypatch):
        # The other half of the same rule: 32000 answers, so the
        # adjustment lines behind it are alternatives and must not be
        # added to it.
        rows = [
            {"fiscalDate": "2024-03-31", "itemCode": 32000,
             "numericValue": 500.0},
            {"fiscalDate": "2024-03-31", "itemCode": 31000,
             "numericValue": 70.0},
        ]
        monkeypatch.setattr(lake, "_fetch_raw", lambda *a, **k: rows)
        assert lake.build_symbol("TEST")["2024-Q1"]["cfo"] == 500.0

    def test_an_unknown_rule_raises_rather_than_chaining(self, monkeypatch):
        """Falling back to "first" is how the sum bug would return."""
        monkeypatch.setitem(uds.VNDIRECT_ITEM_CODES, "debt",
                            ((13110, 13340), "average"))
        rows = [{"fiscalDate": "2024-03-31", "itemCode": 13110,
                 "numericValue": 200.0}]
        monkeypatch.setattr(lake, "_fetch_raw", lambda *a, **k: rows)
        with pytest.raises(ValueError, match="average"):
            lake.build_symbol("TEST")

    def test_the_service_refuses_a_sum_it_cannot_perform(self, monkeypatch):
        """_sum_ttm walks codes as alternatives and stops at the first.

        So a flow field marked "sum" would publish one code where two
        were meant - the same silent halving as debt, on the other side
        of the table. Raising is the only honest answer until _sum_ttm
        learns to add; falling through to "first" is how the bug returns.
        """
        monkeypatch.setitem(uds.VNDIRECT_ITEM_CODES, "revenue",
                            ((21001, 21000), "sum"))
        rows = [{"fiscalDate": "2024-03-31", "itemCode": 21001,
                 "numericValue": 5.0, "modelType": 1.0}]
        monkeypatch.setattr("services.stock_service.fetch_vndirect_raw_statements",
                            lambda *a, **k: rows)
        with pytest.raises(ValueError, match="_sum_ttm cannot do"):
            uds.fetch_vndirect_financials("TEST")


class TestTheFieldsTheBugWasIn:
    """Both corrections have to be visible in the lake, not just here."""

    def test_the_lake_no_longer_calls_liabilities_debt(self):
        source = inspect.getsource(lake)
        assert 'record["total_liabilities"]' not in source, (
            "debt was assigned from total liabilities; trade payables and"
            " customer deposits are not borrowings")

    def test_total_liabilities_is_still_published_under_its_own_name(self):
        # Removing it would cost every record one of the fields
        # MIN_REQUIRED_FIELDS counts. The error was the assignment, not
        # the figure.
        assert "total_liabilities" in lake.LAKE_FIELDS
        assert uds.VNDIRECT_ITEM_CODES["total_liabilities"][0] == (13000,
                                                                   13100)

    def test_the_lake_reads_the_operating_section_total(self):
        assert uds.VNDIRECT_ITEM_CODES["cfo"][0][0] == 32000, (
            "31000 and 31100 are adjustment lines inside the operating"
            " section; the total is 32000")


class TestTheLakesOwnNames:
    def test_a_renamed_field_is_declared_rather_than_assumed(self):
        # The backtest reads "depreciation"; the service calls it "da".
        assert lake.LAKE_FIELD_NAMES["da"] == "depreciation"

    def test_the_rename_actually_reaches_the_record(self, monkeypatch):
        rows = [{"fiscalDate": "2024-03-31", "itemCode": 31110,
                 "numericValue": 42.0}]
        monkeypatch.setattr(lake, "_fetch_raw", lambda *a, **k: rows)
        record = lake.build_symbol("TEST")["2024-Q1"]
        assert record["depreciation"] == 42.0
        assert "da" not in record

    def test_every_renamed_field_is_one_the_lake_publishes(self):
        stray = set(lake.LAKE_FIELD_NAMES) - set(lake.LAKE_FIELDS)
        assert not stray, f"{sorted(stray)} are renamed but never read"
