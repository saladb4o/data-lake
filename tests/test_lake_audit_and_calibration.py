"""The two reporting tools: what the BCTC lake holds, and how priors get made.

Neither is a data pipeline - they exist so a gap is a number someone can act
on rather than an assumption. The BCTC lake reads as a rich corpus at 100 MB
and holds statements for four companies; the sector weight priors were
labelled "pre-calibrated" with no derivation anywhere in the repository.
"""
import importlib.util
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "scripts", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit_mod = _load("audit_bctc_lake")
calib_mod = _load("calibrate_sector_weight_priors")


def _record(**overrides):
    base = {"symbol": "HPG", "year": 2024, "filing_date": "2024-04-20",
            "extracted_data": {}}
    base.update(overrides)
    return base


def _with_statements(**items):
    return {"document_type": "NATIVE",
            "balance_sheet": {"items": items or {270: {"current_val": 1e12}}}}


class TestBctcLakeAudit:
    def test_an_empty_extraction_is_not_counted_as_usable(self):
        report = audit_mod.audit({"a": _record(), "b": _record(symbol="FPT")})
        assert report["records"] == 2
        assert report["records_with_any_extracted_data"] == 0
        assert report["records_with_statements"] == 0
        assert report["usable_pct"] == 0.0

    def test_a_scanned_pdf_with_no_items_is_not_usable(self):
        """document_type alone is not evidence that anything was parsed."""
        scanned = _record(extracted_data={"document_type": "SCANNED_IMAGE",
                                          "total_pages": 30})
        report = audit_mod.audit({"a": scanned})
        assert report["records_with_any_extracted_data"] == 1
        assert report["records_with_statements"] == 0
        assert report["document_types"] == {"SCANNED_IMAGE": 1}

    def test_a_record_with_statement_items_counts(self):
        report = audit_mod.audit({"a": _record(extracted_data=_with_statements())})
        assert report["records_with_statements"] == 1
        assert report["usable_pct"] == 100.0
        assert report["distinct_symbols_with_statements"] == 1

    def test_empty_statement_blocks_do_not_count(self):
        hollow = _record(extracted_data={"balance_sheet": {"items": {}},
                                         "income_statement": {}})
        assert audit_mod.audit({"a": hollow})["records_with_statements"] == 0

    def test_missing_period_metadata_is_counted(self):
        lake = {
            "a": _record(year=None, filing_date=""),
            "b": _record(year="None", filing_date=None),
            "c": _record(),
        }
        report = audit_mod.audit(lake)
        assert report["records_missing_year"] == 2
        assert report["records_missing_filing_date"] == 2
        assert report["years"] == {"2024": 1}

    def test_distinct_symbols_are_deduplicated(self):
        lake = {
            "a": _record(symbol="HPG", extracted_data=_with_statements()),
            "b": _record(symbol="hpg", extracted_data=_with_statements()),
            "c": _record(symbol="FPT", extracted_data=_with_statements()),
        }
        assert audit_mod.audit(lake)["distinct_symbols_with_statements"] == 2

    def test_an_empty_lake_does_not_divide_by_zero(self):
        report = audit_mod.audit({})
        assert report["records"] == 0
        assert report["usable_pct"] == 0.0


class TestPriorCalibration:
    def test_quarter_codes_round_trip(self):
        for code in ("2021-Q1", "2023-Q4", "2026-Q2"):
            assert calib_mod._quarter_code(calib_mod._quarter_ordinal(code)) == code

    def test_the_lower_error_model_gets_more_weight(self):
        errors = {
            "accurate": [0.01] * 30,   # 10% typical error
            "poor": [0.25] * 30,       # 50% typical error
        }
        weights, observations = calib_mod.weights_from_errors(errors, min_observations=12)
        assert observations == 60
        assert weights["accurate"] > weights["poor"]
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-3)

    def test_a_model_with_too_few_observations_is_excluded(self):
        errors = {"solid": [0.02] * 30, "sparse": [0.001] * 3}
        weights, _ = calib_mod.weights_from_errors(errors, min_observations=12)
        assert "sparse" not in weights, "a 3-observation model must not be weighted"
        assert set(weights) == {"solid"}

    def test_thin_evidence_shrinks_toward_equal_weight(self):
        """Twelve observations should not produce a confident split."""
        thin = {"a": [0.01] * 6, "b": [0.25] * 6}
        thick = {"a": [0.01] * 60, "b": [0.25] * 60}
        w_thin, _ = calib_mod.weights_from_errors(thin, min_observations=6)
        w_thick, _ = calib_mod.weights_from_errors(thick, min_observations=6)
        assert abs(w_thin["a"] - w_thin["b"]) < abs(w_thick["a"] - w_thick["b"])

    def test_no_model_can_own_a_sector(self):
        errors = {"dominant": [1e-6] * 100, "other": [0.5] * 100,
                  "third": [0.6] * 100}
        weights, _ = calib_mod.weights_from_errors(errors, min_observations=12)
        assert weights["dominant"] <= calib_mod.MAX_MODEL_WEIGHT + 0.15
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-3)

    def test_no_usable_model_yields_no_table(self):
        weights, observations = calib_mod.weights_from_errors(
            {"a": [0.01] * 2}, min_observations=12)
        assert weights == {} and observations == 0

    def test_the_forward_horizon_matches_the_backtest(self):
        from services.fair_value_backtest_service import FORWARD_ERROR_HORIZON_QUARTERS

        assert calib_mod.FORWARD_HORIZON_QUARTERS == FORWARD_ERROR_HORIZON_QUARTERS
