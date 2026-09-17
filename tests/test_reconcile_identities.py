"""The identity checker, tested on the numbers a real filing produced.

Every fixture here is taken from run 35220475916's log - FPT's Q4 2025
parent-only cash flow - rather than invented, so a change that breaks the
checker breaks against a document that exists.
"""

import pytest

from scripts.reconcile_bctc_against_vendor import (
    CASH_FLOW_IDENTITIES,
    check_identities,
    classify_period,
    classify_scope,
    compare_to_vendor,
    vendor_value,
    _words,
)


def _items(codes):
    """Code -> row, in the shape the parser returns.

    Taken as a dict rather than keyword arguments: these keys are the VAS
    codes themselves, and integers cannot be keywords.
    """
    return {c: {"code": c, "current_val": float(v)} for c, v in codes.items()}


# FPT, Q4 2025, parent-only. Codes 1 and 60 are the misbound ones.
FPT_Q4 = {
    1: 1905249672046, 20: -31728959134, 21: -122709404582, 22: 141133774,
    23: -14679809390009, 24: 13514811170009, 25: -2200000000000,
    27: 5801417334255, 30: 2313850843447, 31: 102609390000,
    33: 14269573627370, 34: -13444286187170, 36: -3182563528913,
    40: -2254666698713, 50: 27455185600, 60: 42728190111, 61: 2694503,
    70: 1905249672046,
}


def _by_label(items):
    return {c["label"]: c for c in check_identities(items, CASH_FLOW_IDENTITIES)}


class TestIdentitiesOnARealFiling:
    def test_the_three_sections_sum_to_net_cash_flow(self):
        r = _by_label(_items(FPT_Q4))["CFO+CFI+CFF = NCF"]
        assert r["status"] == "ok"
        assert r["diff"] == 0

    def test_the_investing_block_closes_even_though_code_26_is_absent(self):
        # The result that matters: whatever sits at code 21 is a component
        # of a section that sums exactly without it left over.
        r = _by_label(_items(FPT_Q4))["investing lines sum to CFI"]
        assert r["status"] == "ok"
        assert r["absent"] == [26]

    def test_the_opening_balance_identity_is_reported_broken(self):
        # 60 is misbound, every code in the identity is present, so this is
        # the definitive case - not "unclear".
        r = _by_label(_items(FPT_Q4))["opening+NCF+FX = closing"]
        assert r["status"] == "BROKEN"
        assert r["absent"] == []


class TestTheThreeStatesAreDistinguished:
    def test_a_gap_with_an_absent_line_is_unclear_not_broken(self):
        items = _items({21: -100.0, 22: 5.0, 30: -200.0})
        r = _by_label(items)["investing lines sum to CFI"]
        assert r["status"] == "unclear"
        assert 26 in r["absent"]

    def test_a_gap_with_every_line_present_is_broken(self):
        items = _items({20: 1.0, 30: 1.0, 40: 1.0, 50: 99.0})
        assert _by_label(items)["CFO+CFI+CFF = NCF"]["status"] == "BROKEN"

    def test_no_target_code_means_no_check_rather_than_a_failure(self):
        items = _items({20: 1.0, 30: 1.0, 40: 1.0})
        r = _by_label(items)["CFO+CFI+CFF = NCF"]
        assert r["status"] == "n/a"
        assert r["missing"] == [50]

    def test_rounding_of_a_dong_does_not_count_as_broken(self):
        items = _items({20: 1.0, 30: 1.0, 40: 1.0, 50: 3.000001})
        assert _by_label(items)["CFO+CFI+CFF = NCF"]["status"] == "ok"


class TestScopeIsReadFromCafefsOwnFileNames:
    @pytest.mark.parametrize("name,scope,period", [
        ("20260126_-_FPT_-_BCTC_hop_nhat_Quy_4_2025.pdf", "consolidated", "Q4"),
        ("20260126_-_FPT_-_BCTC_cong_ty_me_Quy_4_2025.pdf", "separate", "Q4"),
        ("20260319_-_FPT_-_BCTC_rieng_nam_2025_da_kiem_toan.pdf", "separate", "FY"),
        ("FPT_Baocaotaichinh_Q3_2025_Hopnhat_27102025.pdf", "consolidated", "Q3"),
        ("20250820_-_FPT_-_BCTC_hop_nhat_ban_nien_da_soat_xet.pdf",
         "consolidated", "H1"),
    ])
    def test_real_file_names_classify(self, name, scope, period):
        assert classify_scope(name) == scope
        assert classify_period(name) == period

    def test_underscores_do_not_hide_the_words(self):
        # The bug this guards: CafeF joins words with underscores, so a
        # hint list written with spaces matched nothing and every filing
        # came back "unknown".
        assert "hop nhat" in _words("BCTC_hop_nhat_Quy_4_2025.pdf")
        assert "cong ty me" in _words("BCTC_cong_ty_me_Quy_4.pdf")


class TestTheVendorComparisonRefusesWhatItCannotAttribute:
    def test_a_broken_control_withholds_the_capex_verdict(self, monkeypatch):
        # CFO disagrees, so scope/period/unit is wrong and nothing can be
        # concluded about 32100 - the point of having a control at all.
        monkeypatch.setattr(
            "scripts.reconcile_bctc_against_vendor.vendor_rows",
            lambda s, r: [
                {"itemCode": 32000, "numericValue": 999.0, "fiscalDate": "2025-12-31"},
                {"itemCode": 32100, "numericValue": -122709404582.0,
                 "fiscalDate": "2025-12-31"},
            ])
        out = compare_to_vendor("FPT", 2025, _items(FPT_Q4))
        assert out["control_ok"] is False
        assert "withheld" in out["verdict"]
        assert "capex_match" not in out

    def test_a_good_control_lets_a_capex_match_be_reported(self, monkeypatch):
        monkeypatch.setattr(
            "scripts.reconcile_bctc_against_vendor.vendor_rows",
            lambda s, r: [
                {"itemCode": 32000, "numericValue": -31728959134.0,
                 "fiscalDate": "2025-12-31"},
                {"itemCode": 32100, "numericValue": 122709404582.0,
                 "fiscalDate": "2025-12-31"},
            ])
        out = compare_to_vendor("FPT", 2025, _items(FPT_Q4))
        assert out["control_ok"] is True
        # Sign conventions differ between a filing and a vendor feed, so
        # the magnitudes are what is compared.
        assert out["capex_match"] is True
        assert out["verdict"] == "32100 IS VAS 21"

    def test_a_good_control_can_also_refute_the_mapping(self, monkeypatch):
        monkeypatch.setattr(
            "scripts.reconcile_bctc_against_vendor.vendor_rows",
            lambda s, r: [
                {"itemCode": 32000, "numericValue": -31728959134.0,
                 "fiscalDate": "2025-12-31"},
                {"itemCode": 32100, "numericValue": 7.0,
                 "fiscalDate": "2025-12-31"},
            ])
        out = compare_to_vendor("FPT", 2025, _items(FPT_Q4))
        assert out["verdict"] == "32100 is NOT VAS 21"

    def test_a_silent_vendor_is_said_rather_than_guessed(self, monkeypatch):
        monkeypatch.setattr(
            "scripts.reconcile_bctc_against_vendor.vendor_rows",
            lambda s, r: [])
        assert compare_to_vendor("FPT", 2025, _items(FPT_Q4))["verdict"] \
            == "vendor silent"


class TestVendorValue:
    ROWS = [
        {"itemCode": 32100, "numericValue": 5.0, "fiscalDate": "2024-12-31"},
        {"itemCode": 32100, "numericValue": 9.0, "fiscalDate": "2025-12-31"},
        {"itemCode": "32000", "numericValue": 3.0, "fiscalDate": "2025-12-31"},
    ]

    def test_the_right_year_is_picked(self):
        assert vendor_value(self.ROWS, 32100, 2025) == 9.0
        assert vendor_value(self.ROWS, 32100, 2024) == 5.0

    def test_a_string_item_code_still_matches(self):
        assert vendor_value(self.ROWS, 32000, 2025) == 3.0

    def test_an_absent_code_is_none_not_zero(self):
        # Zero and "the vendor does not carry it" are different findings.
        assert vendor_value(self.ROWS, 99999, 2025) is None
