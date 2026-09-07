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


class _Model:
    def __init__(self, status, imputed=(), active=False):
        self.status = status
        self.active = active
        self.diagnostics = {"imputed_drivers": list(imputed)}


class TestBlockedByCountsOnlyApplicableModels:
    """The blocking table was an artefact of evaluation order.

    add_model() records imputed_drivers before it checks sector
    applicability, so a model the sector never allows still files its
    complaint on the way to BYPASSED. Every ordinary company therefore
    appeared blocked by affo (a REIT driver), rwa (a bank driver) and
    landbank (a real-estate driver) at once - which no single company could
    be short of, and which read as a diagnosis rather than as noise.
    """

    def _evaluate(self, monkeypatch, models):
        class _Engine:
            def calculate_all_models(self, symbol, record):
                return models

            def calculate_composite_fair_value(self, models, sector):
                return 0.0

        import services.valuation_engine as ve

        monkeypatch.setattr(ve, "ValuationEngine", _Engine)
        return audit.evaluate({"symbol": "AAV", "sector_code": "VNIND"})

    def test_a_bypassed_model_does_not_file_a_blocking_driver(self, monkeypatch):
        row = self._evaluate(monkeypatch, [_Model("BYPASSED", ["affo", "rwa"])])
        assert row["blocked_by"] == []

    def test_an_applicable_model_still_files_one(self, monkeypatch):
        row = self._evaluate(monkeypatch, [_Model("INSUFFICIENT_DATA", ["ebit"])])
        assert row["blocked_by"] == ["ebit"]

    def test_the_two_are_separated_within_one_symbol(self, monkeypatch):
        row = self._evaluate(
            monkeypatch,
            [_Model("BYPASSED", ["affo", "landbank"]),
             _Model("INSUFFICIENT_DATA", ["ebit", "fcf"])],
        )
        assert set(row["blocked_by"]) == {"ebit", "fcf"}

    def test_models_offered_counts_the_sector_s_own_models_not_all_22(
        self, monkeypatch
    ):
        # Every model is appended to results regardless of sector and merely
        # marked BYPASSED, so len(models) is always 22 and measures nothing.
        row = self._evaluate(
            monkeypatch,
            [_Model("BYPASSED")] * 16 + [_Model("INSUFFICIENT_DATA", ["ebit"])] * 6,
        )
        assert row["models_offered"] == 6
