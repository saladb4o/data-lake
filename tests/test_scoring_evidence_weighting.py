"""A score should say how much of the company it actually saw.

A missing factor used to be ranked at the 50th percentile, so non-disclosure
was free: a company reporting only its flattering metrics was ranked on those
and handed the median for everything else. Two behaviours pin the fix - pillar
weights renormalise over the factors a record has, and the composite is then
shrunk toward the midpoint in proportion to what is missing.
"""
import pytest

from services.quant_scoring import (
    LAST_SCORING_DIAGNOSTICS,
    LOW_COVERAGE_FLAG_THRESHOLD,
    PRIMARY_FACTORS,
    score_universe,
)

ALL_FACTORS = [name for name, _ in PRIMARY_FACTORS]


def _full(symbol: str, **overrides):
    """A record carrying every primary factor."""
    base = {
        "symbol": symbol, "rev_5y_growth": 20.0, "rev_3y_cagr": 18.0,
        "pat_3y_cagr": 22.0, "roe": 18.0, "op_margin": 15.0, "roa": 9.0,
        "de_ratio": 0.5, "current_ratio": 2.0, "peg": 1.0, "pe": 12.0,
    }
    base.update(overrides)
    return base


def _only(symbol: str, **kept):
    """A record carrying nothing but the named factors."""
    record = {"symbol": symbol}
    record.update(kept)
    return record


def _universe(*records):
    return {r["symbol"]: r for r in records}


class TestCoverageIsPublished:
    def test_full_record_reports_full_coverage(self):
        universe = _universe(_full("A"), _full("B", roe=30.0))
        score_universe(universe)
        assert universe["A"]["percentiles"]["factor_coverage_pct"] == 100.0
        assert "low_evidence" not in universe["A"]["percentiles"]

    def test_thin_record_reports_its_coverage_and_is_flagged(self):
        universe = _universe(_full("A"), _only("THIN", roe=40.0))
        score_universe(universe)
        pct = universe["THIN"]["percentiles"]
        assert pct["factor_coverage_pct"] == pytest.approx(
            100.0 / len(ALL_FACTORS), abs=0.05
        )
        assert pct["low_evidence"] is True
        assert pct["factor_coverage_pct"] / 100.0 < LOW_COVERAGE_FLAG_THRESHOLD

    def test_diagnostics_summarise_the_universe(self):
        universe = _universe(_full("A"), _full("B", roe=25.0), _only("THIN", roe=40.0))
        score_universe(universe)
        assert LAST_SCORING_DIAGNOSTICS["low_evidence_records"] == 1
        assert 0.0 < LAST_SCORING_DIAGNOSTICS["mean_factor_coverage_pct"] < 100.0


class TestNonDisclosureIsNotFree:
    def test_a_single_excellent_factor_does_not_outrank_a_full_record(self):
        """The defect: report only your best number and keep the median for
        everything else."""
        universe = _universe(
            _full("GOOD"),
            _full("MID", rev_5y_growth=5.0, rev_3y_cagr=4.0, pat_3y_cagr=3.0,
                  roe=6.0, op_margin=4.0, roa=2.0, de_ratio=2.5,
                  current_ratio=0.8, peg=4.0, pe=40.0),
            _only("CHERRY", roe=99.0),
        )
        score_universe(universe)
        cherry = universe["CHERRY"]["percentiles"]["composite"]
        good = universe["GOOD"]["percentiles"]["composite"]
        assert cherry < good, "a one-factor record must not beat a full one"

    def test_shrinkage_pulls_a_thin_record_toward_the_midpoint(self):
        universe = _universe(_full("A"), _full("B", roe=25.0), _only("THIN", roe=99.0))
        score_universe(universe)
        assert abs(universe["THIN"]["percentiles"]["composite"] - 50.0) < 10.0

    def test_a_thin_record_cannot_reach_either_extreme(self):
        """Uncertainty cuts both ways: sparse data is neither excellent nor
        terrible."""
        universe = _universe(
            _full("A"), _full("B", roe=25.0),
            _only("THIN_GOOD", roe=99.0), _only("THIN_BAD", roe=-80.0),
        )
        score_universe(universe)
        good = universe["THIN_GOOD"]["percentiles"]["composite"]
        bad = universe["THIN_BAD"]["percentiles"]["composite"]
        assert abs(good - bad) < 15.0


class TestPillarsRankOnWhatIsKnown:
    def test_a_pillar_is_not_diluted_by_its_absent_factors(self):
        """Quality is roe/op_margin/roa. A record with only a strong roe should
        have a strong quality pillar, not one dragged to 50 by two absences."""
        universe = _universe(
            _full("HI", roe=40.0, op_margin=30.0, roa=20.0),
            _full("LO", roe=2.0, op_margin=1.0, roa=0.5),
            _only("ROE_ONLY", roe=40.0),
        )
        score_universe(universe)
        assert universe["ROE_ONLY"]["percentiles"]["quality"] > 60.0

    def test_a_pillar_with_no_factors_at_all_is_neutral(self):
        universe = _universe(_full("A"), _only("NOTHING", roe=15.0))
        score_universe(universe)
        # growth has none of its three factors on NOTHING
        assert universe["NOTHING"]["percentiles"]["growth"] == 50.0


class TestFullRecordsAreUnaffected:
    def test_scores_are_unchanged_when_every_record_is_complete(self):
        """The penalty must only bite on missing data."""
        universe = _universe(_full("A"), _full("B", roe=30.0), _full("C", pe=8.0))
        score_universe(universe)
        for sym in universe:
            pct = universe[sym]["percentiles"]
            assert pct["factor_coverage_pct"] == 100.0
            assert 0.0 <= pct["composite"] <= 100.0
        composites = {s: universe[s]["percentiles"]["composite"] for s in universe}
        assert len(set(composites.values())) == 3, "full records must stay separable"
