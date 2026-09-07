"""Every ICB code the listing carries must reach a sector's model list.

The first run of the ICB classifier reported 566 symbols holding a real,
correctly shaped ICB level-2 code that SECTOR_MODEL_MAP had no entry for.
They fell through to VNIND - which is not "industrials" but "unclassified"
- and were judged by the six most data-hungry models in the system. 2300
alone is 301 symbols: Construction & Materials, the largest sector on the
Vietnamese exchanges.

SECTOR_ICB_REGISTRY already declared the groupings ("1300, 1700" for
materials, "2300, 2700" for industrials); only the primary code of each
group had ever been written into the model map. These tests tie the two
structures together in both directions so they cannot drift apart again -
which is how the gap arose in the first place.
"""
import pytest

from services.stock_service import SECTOR_ICB_REGISTRY
from services.valuation_engine import SECTOR_MODEL_MAP


def _registry_codes():
    for sector, meta in SECTOR_ICB_REGISTRY.items():
        for part in str(meta.get("icb_code") or "").split(","):
            code = part.strip()
            if code:
                yield sector, code


class TestTheTwoStructuresAgree:
    @pytest.mark.parametrize("sector,code", sorted(set(_registry_codes())))
    def test_every_registry_code_has_a_model_list(self, sector, code):
        assert code in SECTOR_MODEL_MAP, (
            f"{code} is declared under {sector} in SECTOR_ICB_REGISTRY but has "
            f"no entry in SECTOR_MODEL_MAP, so every symbol carrying it falls "
            f"through to the unclassified default"
        )

    @pytest.mark.parametrize("sector,code", sorted(set(_registry_codes())))
    def test_no_registry_code_is_offered_an_empty_or_oversized_list(
        self, sector, code
    ):
        # Deliberately not "the same models as its sector". The model map is
        # finer-grained than the registry and should stay that way: the
        # registry files banks, securities firms and insurers together under
        # VNFIN, while the map gives 8500 insurance models and 8700
        # brokerage models, and 6500 telecom models rather than VNIT's
        # software models. Asserting equality would flatten that.
        models = SECTOR_MODEL_MAP[code]
        assert 0 < len(models) <= 6

    @pytest.mark.parametrize("code,group", [
        ("1300", "VNMAT"), ("2300", "VNIND"), ("3300", "VNCOND"),
        ("3700", "VNCOND"), ("5300", "VNCOND"), ("5500", "VNCOND"),
        ("5700", "VNCOND"),
    ])
    def test_the_codes_added_here_follow_their_declared_group(self, code, group):
        # These seven were aliased onto their group's list, so for them
        # equality is exactly the intended contract.
        assert SECTOR_MODEL_MAP[code] == SECTOR_MODEL_MAP[group]


class TestTheCodesSeenInTheListing:
    """The seven the run actually reported, with their symbol counts."""

    @pytest.mark.parametrize("code,seen", [
        ("2300", 301), ("3700", 73), ("1300", 70),
        ("5700", 46), ("5500", 31), ("5300", 27), ("3300", 18),
    ])
    def test_it_now_resolves(self, code, seen):
        assert code in SECTOR_MODEL_MAP, f"{seen} symbols carry {code}"

    def test_construction_is_valued_as_industry_not_as_a_reit(self):
        assert SECTOR_MODEL_MAP["2300"] == SECTOR_MODEL_MAP["VNIND"]

    def test_retail_is_valued_with_consumer_models(self):
        assert "consumer_eva_mva" in SECTOR_MODEL_MAP["5300"]
        assert "industrial_apv" not in SECTOR_MODEL_MAP["5300"]

    def test_chemicals_go_with_basic_resources(self):
        assert SECTOR_MODEL_MAP["1300"] == SECTOR_MODEL_MAP["VNMAT"]


class TestNothingWasLoosened:
    def test_each_sector_still_offers_at_most_six_models(self):
        # The point is to ask the right question, not more questions. A
        # sector handed all 22 would be back to judging a microcap by a
        # REIT model.
        for code, models in SECTOR_MODEL_MAP.items():
            assert len(models) <= 6, f"{code} offers {len(models)} models"

    def test_banks_are_still_valued_only_with_bank_models(self):
        assert "industrial_apv" not in SECTOR_MODEL_MAP["8300"]
        assert "bank_equity_cash_flow" in SECTOR_MODEL_MAP["8300"]

    def test_real_estate_is_still_valued_only_with_property_models(self):
        assert "reit_affo_dcf" in SECTOR_MODEL_MAP["8600"]
        assert "industrial_apv" not in SECTOR_MODEL_MAP["8600"]
