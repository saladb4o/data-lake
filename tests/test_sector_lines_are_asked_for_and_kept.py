"""The land bank and the loan book exist, and were never asked for or kept.

Two separate failures stacked on the same two numbers, and the blocking
table could not tell either of them from "the data does not exist":

  1. fetch_vndirect_financials() parses landbank_fq (item codes 11420 and
     12510) and bank_loans_fq (112000). Both were attached to the record and
     given no provenance tier, so the copy to the top level - which admits a
     line only on the evidence of a tier - dropped them. The engine asks for
     both by exactly those names.

  2. Worse, most of the companies that need them were never asked. VNDIRECT
     is called only when TradingView left one of eight general statement
     lines empty, and TradingView has no land-bank or gross-loans column at
     any level of completeness. A real estate company whose income statement
     and balance sheet TradingView covers fully was therefore never sent to
     the one vendor that could state its land bank, and was then refused for
     want of a number nobody had asked for.

landbank blocked 123 symbols and rwa 41, both previously reported as
sector-specific data no route carries. Membership in the widened gate is
not a claim that the vendor has the line: a payload without the item code
comes back empty, is not tiered, is not published, and the model stays
refused. Both directions are pinned below.
"""

import pytest

from services.unified_data_service import (
    _TV_REQUIRED_LINES,
    _needs_vndirect_backfill,
    normalize_stock_data,
)
from services.valuation_engine import InputResolver
from tests.test_altman_inputs_are_measured import payload

LANDBANK = 8e12
BANK_LOANS = 400e12
GROSS_PPE = 25e12

VENDOR_ANSWERED = {
    "landbank_fq": LANDBANK,
    "bank_loans_fq": BANK_LOANS,
    "gross_ppe_fq": GROSS_PPE,
}

# What the engine looks the line up as, and the alias tuple it uses.
ENGINE_LOOKUP = {
    "landbank": ("landbank_fq",),
    "rwa": ("bank_loans_fq", "rwa"),
    "gross_ppe": ("gross_ppe_fq", "ppe_gross", "fixed_assets"),
}


def complete_tv_row():
    """A TradingView row with every line the completeness test asks about."""
    return {key: 1.0 for key in _TV_REQUIRED_LINES}


class TestTheSectorsThatNeedThemAreAsked:
    @pytest.mark.parametrize("sector", [
        "VNREAL", "VNREA", "8600",            # land bank
        "VNFIN", "VNBNK", "VNINS", "8300", "8500",   # gross loans
    ])
    def test_a_complete_tradingview_row_does_not_excuse_the_call(self, sector):
        assert _needs_vndirect_backfill(complete_tv_row(), sector), (
            f"{sector} is valued on a line TradingView has no column for; a "
            f"complete row says nothing about whether that line is known"
        )

    def test_the_case_is_lowercase_and_whitespace_tolerant(self):
        assert _needs_vndirect_backfill(complete_tv_row(), "  vnreal ")

    def test_an_ordinary_sector_still_costs_no_second_request(self):
        assert not _needs_vndirect_backfill(complete_tv_row(), "VNIND"), (
            "widening the gate for two sectors must not turn it into a "
            "second request for the whole universe"
        )

    def test_an_incomplete_row_is_still_asked_in_any_sector(self):
        assert _needs_vndirect_backfill({}, "VNIND")

    def test_the_gate_is_unchanged_when_no_sector_is_supplied(self):
        assert not _needs_vndirect_backfill(complete_tv_row())
        assert _needs_vndirect_backfill(None)


class TestTheAnswerIsKept:
    @staticmethod
    @pytest.fixture(scope="class")
    def answered():
        return normalize_stock_data(
            "TEST", tv_data=payload(), vndirect_data=dict(VENDOR_ANSWERED))

    @pytest.mark.parametrize("key,value", sorted(VENDOR_ANSWERED.items()))
    def test_the_line_reaches_the_top_level(self, answered, key, value):
        assert answered.get(key) == value, (
            f"{key!r} is parsed by the vendor fetch and attached to the "
            f"record; without a tier it is dropped before the engine"
        )

    @pytest.mark.parametrize("key", sorted(VENDOR_ANSWERED))
    def test_a_stated_line_is_tier_three(self, answered, key):
        assert answered["field_provenance"].get(key) == 3

    @pytest.mark.parametrize("field,aliases", sorted(ENGINE_LOOKUP.items()))
    def test_the_engine_resolves_it_as_real(self, answered, field, aliases):
        res = InputResolver(answered)
        res.resolve(field, aliases, impute=lambda: 0.0)
        assert not res.is_imputed(field), (
            f"{field!r} must resolve from the vendor's own figure; an "
            f"imputed driver refuses the model that declares it"
        )


class TestASilentVendorInventsNothing:
    @staticmethod
    @pytest.fixture(scope="class")
    def silent():
        return normalize_stock_data("TEST", tv_data=payload(), vndirect_data={})

    @pytest.mark.parametrize("key", sorted(VENDOR_ANSWERED))
    def test_the_line_is_absent(self, silent, key):
        assert silent.get(key) is None

    @pytest.mark.parametrize("key", sorted(VENDOR_ANSWERED))
    def test_the_line_is_untiered(self, silent, key):
        assert key not in silent["field_provenance"]

    @pytest.mark.parametrize("field,aliases", sorted(ENGINE_LOOKUP.items()))
    def test_the_model_stays_refused(self, silent, field, aliases):
        res = InputResolver(silent)
        res.resolve(field, aliases, impute=lambda: 1.0)
        assert res.is_imputed(field), (
            "a company whose payload does not carry the item code must stay "
            "refused, not be valued on an invented land bank"
        )

    def test_a_zero_is_not_an_answer(self):
        # A code present in the payload but reported as zero is "not stated"
        # as often as it is "none", and a zero land bank would value a
        # developer at its cash alone.
        rec = normalize_stock_data(
            "TEST", tv_data=payload(),
            vndirect_data={"landbank_fq": 0.0, "bank_loans_fq": 0.0})
        assert rec.get("landbank_fq") is None
        assert rec.get("bank_loans_fq") is None
