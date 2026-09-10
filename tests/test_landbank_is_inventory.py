"""The land bank is inventory, read under the VAS numbering.

A census of all 112 developers that return a coded balance sheet settled
this. Item code 11420 appears in none of them; 12510 appears in all of them
and is zero in every case. So the pair the service read could never publish
anything, and the record agreed: landbank_fq reached the snapshot for 0 of
112, with the `> 0` guard correctly refusing a zero.

The scheme is itemCode = 1 + the three-digit VAS balance-sheet code + 0,
confirmed on five independent lines by their median share of total assets.
That makes 11420 VAS 142 - a line the standard form does not have - and
12510 VAS 251, long-term work in progress, where a Vietnamese developer
does not hold its pipeline. It holds it in inventory: VAS 140/141, 20.5% of
total assets, non-zero for 106 of the 112.
"""
import pytest

import services.unified_data_service as uds


def _raw(rows, date="2025-06-30"):
    return [
        {"itemCode": code, "fiscalDate": date, "numericValue": value,
         "itemName": ""}
        for code, value in rows
    ]


@pytest.fixture
def vendor(monkeypatch):
    def _install(rows):
        import services.stock_service as ss
        monkeypatch.setattr(
            ss, "fetch_vndirect_raw_statements",
            lambda symbol, report_type="ANNUAL", target_quarters=16: _raw(rows),
            raising=False,
        )
        monkeypatch.setattr(ss.cache, "get", lambda *a, **k: None)
        monkeypatch.setattr(ss.cache, "set", lambda *a, **k: None)
    return _install


class TestItReadsInventory:
    def test_the_net_inventory_line_is_the_land_bank(self, vendor):
        vendor([(12700, 5.0e12), (11400, 1.0e12), (11410, 1.05e12)])
        assert uds.fetch_vndirect_financials("NLG")["landbank_fq"] == 1.0e12

    def test_the_gross_line_is_the_fallback(self, vendor):
        # 11400 is net of the obsolescence provision and 11410 is gross;
        # net first because it is the conservative one, gross when the
        # payload carries only that.
        vendor([(12700, 5.0e12), (11410, 1.05e12)])
        assert uds.fetch_vndirect_financials("NLG")["landbank_fq"] == 1.05e12


class TestTheOldCodesCouldNotHaveWorked:
    def test_a_zero_long_term_wip_is_not_a_land_bank(self, vendor):
        # The shape the census actually found: 12510 present for every
        # developer and zero for every one of them. Reading it would
        # publish nothing, which is what happened for 112 of 112.
        vendor([(12700, 5.0e12), (12510, 0.0), (11400, 1.0e12)])
        assert uds.fetch_vndirect_financials("NLG")["landbank_fq"] == 1.0e12

    def test_no_inventory_means_no_land_bank(self, vendor):
        # Fail-closed: a developer whose payload carries no inventory line
        # is refused rather than valued on a stand-in.
        vendor([(12700, 5.0e12), (12510, 0.0)])
        assert uds.fetch_vndirect_financials("NLG")["landbank_fq"] is None


class TestTheInferenceIsRecorded:
    def test_the_land_bank_is_tier_2_not_tier_3(self):
        # The vendor states an inventory balance. Reading that balance as
        # the land bank is this project's inference, not the vendor's
        # assertion, and the tier says so. Tier 2 still clears the gate.
        record = uds.normalize_stock_data(
            symbol="NLG", exchange="HOSE", name="Test",
            sector_code="8600", sector_name="Bat dong san",
            tv_data={"close": 40_000.0, "total_shares_outstanding_fq": 4e8},
            vndirect_data={"landbank_fq": 2.0e12, "gross_ppe_fq": 5.0e11},
        )
        assert record["field_provenance"]["landbank_fq"] == 2
        # A line the vendor does state outright keeps tier 3, so the
        # distinction is about this field and not a blanket downgrade.
        assert record["field_provenance"]["gross_ppe_fq"] == 3

    def test_a_zero_land_bank_is_still_refused(self):
        record = uds.normalize_stock_data(
            symbol="NLG", exchange="HOSE", name="Test",
            sector_code="8600", sector_name="Bat dong san",
            tv_data={"close": 40_000.0, "total_shares_outstanding_fq": 4e8},
            vndirect_data={"landbank_fq": 0.0},
        )
        assert "landbank_fq" not in record["field_provenance"]
