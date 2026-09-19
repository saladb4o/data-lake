"""The path a real filing takes into the template.

A units mistake in a valuation is invisible - every number stays
plausible and only the answer is wrong by a factor of a million - so the
conversion gets a test of its own.
"""
import os
import sys

import pytest

openpyxl = pytest.importorskip("openpyxl")

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "xlsxvas"))

import fill_from_lake as F                     # noqa: E402
import vas_layout as V                         # noqa: E402


def test_dong_become_millions_of_dong():
    assert F.in_millions(27_566_961_471_493.0, 1.0) == 27_566_961.471493
    assert F.VND_PER_MILLION == 1_000_000.0


def test_a_filing_stated_in_thousands_is_scaled_first():
    # scale_multiplier is the lake's own "these figures are in X"
    assert F.in_millions(1_000.0, 1_000.0) == 1.0


def _record(items):
    return {"extracted_data": {"balance_sheet": {
        "items": items, "scale_multiplier": 1.0}}}


def test_only_codes_the_template_carries_are_taken():
    rec = _record({
        "270": {"current_val": 27_566_961_471_493.0},
        "119": {"current_val": 457_034_136_435.0},   # not a template line
    })
    found = F.codes_from(rec)["balance_sheet"]
    assert "270" in found
    assert "119" not in found


def test_a_missing_code_is_left_empty_not_zeroed():
    """An absent line is a line nobody extracted, not a line worth zero."""
    rec = _record({"270": {"current_val": 1_000_000.0}})
    found = F.codes_from(rec)["balance_sheet"]
    assert set(found) == {"270"}
    # every other balance-sheet code the template knows is simply absent
    assert "300" not in found and "440" not in found


def test_a_null_value_is_not_written_as_zero():
    rec = _record({"270": {"current_val": None}})
    assert F.codes_from(rec)["balance_sheet"] == {}


def test_single_digit_statement_codes_match_the_layouts_zero_padding():
    rec = {"extracted_data": {"income_statement": {
        "items": {"1": {"current_val": 5_000_000.0}},
        "scale_multiplier": 1.0}}}
    found = F.codes_from(rec)["income_statement"]
    assert found == {"01": 5.0}
    assert "01" in V.IS_ROW
