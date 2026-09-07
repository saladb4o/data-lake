"""The audit's report on symbols the model map refuses despite good data.

The last run valued 1,163 of 1,522 symbols. 1,307 carried core drivers at
tier 2 or better, so 144 symbols were turned away with data the provenance
gate had already accepted. That is not a data gap and no new vendor fixes
it; the report has to say which sector each of them was valued as, because
a sector missing from SECTOR_MODEL_MAP falls through to all 22 models and a
sector whose own five models need absent drivers does not.
"""
import io
import contextlib

import pytest

from scripts import audit_valuation_coverage as audit


def _report(rows):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        audit.report(rows, show_blocked=0)
    return buf.getvalue()


def _row(symbol, tier, models=0, sector="VNIND", offered=6, fv=0.0):
    return {
        "symbol": symbol,
        "worst_tier": tier,
        "active_models": models,
        "fair_value": fv,
        "blocked_by": [],
        "error": None,
        "sector_code": sector,
        "models_offered": offered,
    }


class TestItSeparatesTheTwoKindsOfRefusal:
    def test_a_refusal_on_tier_1_data_is_not_counted_as_gated_out(self):
        # Tier 1 is a sector stand-in back-solved from market cap. Refusing
        # it is the provenance gate doing its job, not a model-map gap.
        out = _report([_row("A", 1)])
        assert "Refused despite tier-2-or-better data" not in out

    def test_a_refusal_on_tier_3_data_is_reported_with_its_sector(self):
        out = _report([_row("AAV", 3, sector="VNREAL", offered=22)])
        assert "Refused despite tier-2-or-better data: 1 of 1" in out
        assert "VNREAL" in out

    def test_a_valued_symbol_is_never_counted(self):
        out = _report([_row("FPT", 3, models=4, fv=120_000.0)])
        assert "Refused despite tier-2-or-better data" not in out


class TestItNamesTheSectorMapGap:
    def test_a_sector_absent_from_the_map_is_flagged_no(self):
        out = _report([_row("AAV", 3, sector="NOT_A_SECTOR", offered=22)])
        # 22 models offered means the map had no entry and every model ran,
        # which is why such a symbol is blocked by affo, rwa and landbank at
        # once. The flag says so outright rather than leaving it inferred.
        assert "NO" in out
        assert "22" in out

    def test_a_sector_present_in_the_map_is_flagged_yes(self):
        out = _report([_row("AAH", 3, sector="VNIND", offered=6)])
        assert "yes" in out

    def test_an_empty_sector_is_rendered_rather_than_left_blank(self):
        out = _report([_row("X", 3, sector="", offered=22)])
        assert "(none)" in out


class TestItSurvivesTheErrorPath:
    def test_a_row_that_never_reached_the_engine_does_not_crash_the_report(self):
        # evaluate() sets sector_code inside the try, so a symbol that raised
        # has no such key. Reading it directly would turn a report about
        # failures into a failure.
        broken = _row("BAD", 3)
        del broken["sector_code"]
        del broken["models_offered"]
        broken["error"] = "ValueError: boom"
        _report([broken])  # must not raise
