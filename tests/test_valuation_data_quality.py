"""Valuation payloads must say how much real data they rest on.

The engine substitutes sector and structural defaults for every missing input,
so a thinly-sourced valuation is indistinguishable from a well-sourced one in
the output. data_quality makes that difference explicit.
"""

import pytest

from services.valuation_engine import (
    CORE_VALUATION_INPUTS,
    ValuationEngine,
    assess_data_quality,
)

RICH = {
    "symbol": "VCB", "price": 90000.0, "eps": 5200, "bvps": 32000, "pe": 17.3, "pb": 2.8,
    "roe": 0.21, "roic": 0.15, "revenue": 6.8e13, "net_income": 3.5e13, "pat": 3.5e13,
    "ebit": 4.2e13, "operating_profit": 4.1e13, "equity": 1.5e14, "total_assets": 1.9e15,
    "debt": 4.0e14, "shares_out": 5.5e9, "market_cap": 5e14,
    "rev_1y_growth": 0.11, "pat_1y_growth": 0.09, "sector_code": "VNBNK",
}


class TestAssessment:
    def test_full_coverage_grades_high(self):
        q = assess_data_quality(RICH)
        assert q["coverage_pct"] == 100.0
        assert q["grade"] == "HIGH"
        assert q["inputs_missing"] == []
        assert q["warnings"] == []

    def test_sparse_input_grades_low_and_warns(self):
        q = assess_data_quality({"price": 20000.0})
        assert q["grade"] == "LOW"
        assert q["coverage_pct"] < 40
        assert any("40%" in w for w in q["warnings"])
        assert set(q["inputs_missing"]) == set(CORE_VALUATION_INPUTS) - {"price"}

    @pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), ""])
    def test_unusable_values_do_not_count_as_present(self, bad):
        q = assess_data_quality(dict(RICH, eps=bad))
        assert "eps" in q["inputs_missing"], f"{bad!r} was counted as real data"
        assert any("eps" in w for w in q["warnings"])

    def test_named_models_are_flagged_when_their_driver_is_absent(self):
        q = assess_data_quality({k: v for k, v in RICH.items() if k != "bvps"})
        assert any("book-value models" in w for w in q["warnings"])


class TestPayload:
    def test_result_carries_data_quality(self):
        res = ValuationEngine().get_comprehensive_valuation("VCB", fundamental_data=dict(RICH))
        assert res.data_quality["grade"] == "HIGH"
        assert "data_quality" in res.to_dict()

    def test_thin_and_rich_valuations_are_distinguishable(self):
        """The whole point: two results that otherwise look alike."""
        engine = ValuationEngine()
        rich = engine.get_comprehensive_valuation("VCB", fundamental_data=dict(RICH))
        thin = engine.get_comprehensive_valuation("XYZ", fundamental_data={"price": 20000.0})

        assert rich.composite_fair_value > 0 and thin.composite_fair_value > 0
        assert rich.data_quality["grade"] == "HIGH"
        assert thin.data_quality["grade"] == "LOW"
        assert thin.data_quality["warnings"], "a thin valuation must carry a warning"


class TestStructuralAssumptions:
    """Structural stand-ins must be named, not just silently applied."""

    def test_assumptions_are_listed_when_their_inputs_are_absent(self):
        q = assess_data_quality({"price": 20000.0, "eps": 2500})
        fields = {a["field"] for a in q["assumptions_applied"]}
        assert fields == {"shares_out", "market_cap", "debt"}
        assert all(a["assumption"] for a in q["assumptions_applied"])

    def test_no_assumptions_when_the_data_is_there(self):
        assert assess_data_quality(RICH)["assumptions_applied"] == []

    def test_an_alternate_source_field_counts(self):
        """debt has three possible source fields; any one suppresses the stand-in."""
        q = assess_data_quality({"price": 20000.0, "interest_bearing_debt": 4.0e14})
        assert "debt" not in {a["field"] for a in q["assumptions_applied"]}

    def test_it_reaches_the_payload(self):
        res = ValuationEngine().get_comprehensive_valuation(
            "XYZ", fundamental_data={"price": 20000.0}
        )
        assert res.to_dict()["data_quality"]["assumptions_applied"]
