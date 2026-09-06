"""The weighting stage must not reward models for agreeing with the market.

Three defects lived here:
  * nearest-rank quartiles inflated the IQR until the outlier fence stopped
    rejecting anything at small n;
  * sector priors were diluted by every model the priors table did not name,
    so a stated 35% was really 29% and moved with unrelated models;
  * with no measured history - which is every production call - "omnibus"
    weighted each model by its closeness to the mean of the others, damping
    precisely the models that disagreed.
"""
import pytest

from services.valuation_engine import (
    LAST_WEIGHTING_DIAGNOSTICS,
    SECTOR_WEIGHT_PRIORS,
    AdaptiveWeightingEngine,
)


class TestOutlierFence:
    def test_small_sample_outlier_is_rejected(self):
        """Nearest-rank put Q3 on the largest value at n=4, so nothing was ever
        outside the fence."""
        kept, idx = AdaptiveWeightingEngine.filter_outliers_iqr([10.0, 12.0, 14.0, 100.0])
        assert 100.0 not in kept
        assert idx == [0, 1, 2]

    def test_tight_cluster_keeps_everything(self):
        vals = [10.0, 11.0, 12.0, 13.0]
        kept, idx = AdaptiveWeightingEngine.filter_outliers_iqr(vals)
        assert kept == vals

    def test_below_four_values_is_left_alone(self):
        vals = [10.0, 900.0, 12.0]
        assert AdaptiveWeightingEngine.filter_outliers_iqr(vals) == (vals, [0, 1, 2])


class TestSectorPriorsMeanWhatTheySay:
    def test_named_models_keep_their_stated_proportions(self):
        priors = SECTOR_WEIGHT_PRIORS["VNBNK"]
        named = list(priors)
        # An unpriored but sector-applicable model is present too.
        models = named + ["graham_growth", "p_tbv"]
        values = [20_000.0] * len(models)

        weights, _ = AdaptiveWeightingEngine.calculate_weights(
            active_models=models, active_values=values, sector_code="VNBNK",
        )
        assert weights["pb_rhodes_kropf"] == pytest.approx(priors["pb_rhodes_kropf"], abs=1e-3)
        assert weights.get("graham_growth", 0.0) == 0.0
        assert sum(w for w in weights.values()) == pytest.approx(1.0, abs=1e-3)

    def test_the_gap_in_the_priors_table_is_reported(self):
        AdaptiveWeightingEngine.calculate_weights(
            active_models=list(SECTOR_WEIGHT_PRIORS["VNBNK"]) + ["graham_growth"],
            active_values=[20_000.0] * 5, sector_code="VNBNK",
        )
        assert LAST_WEIGHTING_DIAGNOSTICS["unpriored_models"] == ["graham_growth"]

    def test_weights_do_not_move_when_an_unpriored_model_appears(self):
        """The dilution bug: an unrelated model changed every stated weight."""
        named = list(SECTOR_WEIGHT_PRIORS["VNBNK"])
        without, _ = AdaptiveWeightingEngine.calculate_weights(
            active_models=named, active_values=[20_000.0] * len(named), sector_code="VNBNK",
        )
        with_extra, _ = AdaptiveWeightingEngine.calculate_weights(
            active_models=named + ["graham_growth", "p_tbv"],
            active_values=[20_000.0] * (len(named) + 2), sector_code="VNBNK",
        )
        for model in named:
            assert without[model] == pytest.approx(with_extra[model], abs=1e-4)


class TestOmnibusDoesNotHerd:
    MODELS = ["blended_pe", "pb_rhodes_kropf", "rim_edwards_bell_ohlson",
              "bank_equity_cash_flow"]

    SPREAD = ["blended_pe", "pb_rhodes_kropf", "rim_edwards_bell_ohlson",
              "bank_equity_cash_flow", "p_tbv", "graham_growth"]

    def test_dissenting_model_is_not_damped_within_a_call(self):
        """A model far from the consensus - but inside the outlier fence -
        must not be weighted down for disagreeing."""
        values = [15_000.0, 18_000.0, 21_000.0, 24_000.0, 27_000.0, 36_000.0]
        weights, rejected = AdaptiveWeightingEngine.calculate_weights(
            self.SPREAD, values, sector_code="NO_PRIOR", composite_mode="omnibus",
        )
        assert rejected == [], "fence should keep all six for this test"
        assert weights["graham_growth"] == pytest.approx(weights["blended_pe"], abs=1e-4)

    def test_a_models_weight_does_not_move_with_its_own_disagreement(self):
        near = [15_000.0, 18_000.0, 21_000.0, 24_000.0, 27_000.0, 29_000.0]
        far = [15_000.0, 18_000.0, 21_000.0, 24_000.0, 27_000.0, 36_000.0]

        w_near, _ = AdaptiveWeightingEngine.calculate_weights(
            self.SPREAD, near, sector_code="NO_PRIOR", composite_mode="omnibus",
        )
        w_far, _ = AdaptiveWeightingEngine.calculate_weights(
            self.SPREAD, far, sector_code="NO_PRIOR", composite_mode="omnibus",
        )
        assert w_near["graham_growth"] == pytest.approx(w_far["graham_growth"], abs=1e-4)

    def test_unapplied_metric_is_declared(self):
        AdaptiveWeightingEngine.calculate_weights(
            self.MODELS, [20_000.0] * 4, sector_code="VNBNK",
            composite_mode="omnibus", omnibus_metric="smape",
        )
        assert LAST_WEIGHTING_DIAGNOSTICS["fallback"] == "no_history_metric_not_applied"
        assert LAST_WEIGHTING_DIAGNOSTICS["requested_metric"] == "smape"

    def test_measured_history_still_drives_the_weights(self):
        """The honest path must keep working: a model with a lower measured
        error gets more weight."""
        errors = {
            "blended_pe": {"smape": 8.0, "n_obs": 12, "r2": 1.0},
            "pb_rhodes_kropf": {"smape": 40.0, "n_obs": 12, "r2": 1.0},
        }
        weights, _ = AdaptiveWeightingEngine.calculate_weights(
            ["blended_pe", "pb_rhodes_kropf"], [20_000.0, 21_000.0],
            sector_code="VNBNK", composite_mode="omnibus",
            omnibus_metric="smape", historical_errors=errors,
        )
        assert weights["blended_pe"] > weights["pb_rhodes_kropf"]
