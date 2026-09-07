"""Which sector a symbol is valued as, and how that is decided.

VNIND was never "industrials" in this pipeline; it was "unclassified". The
only classifier was rep_map, built from the representative_stocks lists -
129 hand-typed tickers across ten sectors - so roughly 1,393 of 1,522
symbols defaulted to VNIND because nobody had typed them in. VNIND is then
offered the six most data-hungry models in the system, and 149 of the 150
refusals that carry tier-2-or-better data are VNIND. Those symbols were not
short of data so much as asked the wrong question.

The real classification was on disk the whole time: the listing sync stores
Vietcap's icbCode2 as "icb_code", and SECTOR_MODEL_MAP has carried the ICB
level-2 numeric keys for exactly this lookup, which nothing performed.
"""
import pytest

from scripts import sync_unified_market_data as sync
from services.valuation_engine import SECTOR_MODEL_MAP

REP_MAP = {"FPT": ("VNIT", "Công Nghệ")}


def _classify(record, symbol="TST"):
    return sync._classify(record, symbol, REP_MAP)


class TestTheIcbCodeIsUsed:
    def test_a_recognised_code_decides_the_sector(self):
        code, _name, how = _classify({"icb_code": "8600"})
        assert code == "8600"
        assert how == "ICB code from the listing"

    def test_every_numeric_key_in_the_model_map_is_reachable(self):
        # These keys exist for this lookup and nothing performed it. If one
        # is unreachable the map is carrying dead weight.
        for key in (k for k in SECTOR_MODEL_MAP if k.isdigit()):
            assert _classify({"icb_code": key})[0] == key

    def test_a_multi_code_registry_string_takes_the_first_it_recognises(self):
        # SECTOR_ICB_REGISTRY stores "8300, 8700, 8500" for banking; a
        # listing record carries one code, but the shape is not assumed.
        assert _classify({"icb_code": "8300, 8700"})[0] == "8300"

    def test_a_sector_reached_this_way_gets_its_own_models(self):
        code, _n, _h = _classify({"icb_code": "8600"})
        assert "reit_affo_dcf" in SECTOR_MODEL_MAP[code]
        assert "industrial_apv" not in SECTOR_MODEL_MAP[code]


class TestTheFallbacksAreOrdered:
    def test_an_unrecognised_code_falls_through_to_the_curated_list(self):
        code, _n, how = _classify({"icb_code": "9999"}, symbol="FPT")
        assert code == "VNIT"
        assert how == "representative-stocks list"

    def test_no_code_and_no_listing_entry_still_defaults_to_vnind(self):
        code, _n, how = _classify({}, symbol="UNKNOWN")
        assert code == "VNIND"
        assert how == "default (unclassified)"

    def test_the_curated_list_is_not_consulted_when_the_code_is_good(self):
        # FPT is in rep_map as VNIT. A recognised ICB code outranks it: the
        # listing knows the company's actual classification, the hand-typed
        # list knows only that someone once typed the ticker.
        assert _classify({"icb_code": "8600"}, symbol="FPT")[0] == "8600"

    def test_an_empty_code_is_not_treated_as_a_code(self):
        assert _classify({"icb_code": ""}, symbol="FPT")[2] == "representative-stocks list"
        assert _classify({"icb_code": None}, symbol="FPT")[2] == "representative-stocks list"


class TestUnrecognisedCodesAreCounted:
    def test_a_code_the_map_does_not_know_is_recorded_not_discarded(self):
        # The difference between "the listing carries no codes" and "it
        # carries codes in a shape we do not recognise" needs opposite
        # fixes, so an unmatched code is named rather than silently dropped.
        sync.unresolved_icb.clear()
        _classify({"icb_code": "9999"}, symbol="UNKNOWN")
        assert sync.unresolved_icb["9999"] == 1

    def test_a_recognised_code_is_not_recorded_as_unresolved(self):
        sync.unresolved_icb.clear()
        _classify({"icb_code": "8600"})
        assert not sync.unresolved_icb
