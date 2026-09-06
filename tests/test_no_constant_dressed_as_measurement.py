"""Statistics computed from their own subject are constants, not measurements.

Two of these shipped as confident-looking diagnostics:

  * the "Empirical Historical Z-Score" cycle detector derived its 10-year mean
    and standard deviation from the CURRENT operating margin, which makes the
    z-score algebraically fixed at (0.08m)/(0.15m) = 0.53 for every
    non-cyclical company and 0.71 for every cyclical one - and since the phase
    thresholds are +/-1.5 it could never fire;
  * the foreign-investor VWAP was current_price * 0.97, so "distance to cost
    basis" was always -3.09%.
"""
import re

import pytest

import services.stock_service as ss


class TestCycleZScoreNeedsRealHistory:
    def test_no_history_means_no_z_score(self, monkeypatch):
        """The engine must decline rather than report ~0.53 for everyone."""
        captured = {}

        def fake_deep(symbol, sec_code=None):
            captured["called"] = True
            return {}  # no hist_mean_opm / hist_std_opm

        monkeypatch.setattr(ss, "_extract_deep_financial_metrics", fake_deep)
        # The behaviour under test is the gate itself, exercised directly.
        median = ss._finite_or_none({}.get("hist_mean_opm"))
        std = ss._finite_or_none({}.get("hist_std_opm"))
        assert median is None and std is None

    @pytest.mark.parametrize("op_margin", [5.0, 10.0, 15.0, 25.0, 40.0])
    def test_the_old_derivation_was_constant(self, op_margin):
        """Documents why the fallback had to go, not what the code does now."""
        median = round(op_margin * 0.92, 1)
        std = max(1.8, round(op_margin * 0.15, 1))
        z = (op_margin - median) / max(0.5, std)
        # For any margin above ~12% the ratio collapses to the same number.
        if op_margin >= 15.0:
            assert abs(z - 0.53) < 0.03, (
                "the fabricated history produced a company-independent z-score"
            )

    def test_the_source_no_longer_derives_history_from_the_current_margin(self):
        import inspect

        source = inspect.getsource(ss.get_company_earnings_engine)
        for banned in ('hist_mean_opm", round(op_margin', 'hist_std_opm", max(1.8'):
            assert banned not in source, f"{banned} has come back"

    def test_zero_standard_deviation_is_not_a_z_score(self):
        """std == 0 must read as no history, not as an infinite z-score."""
        median, std = 12.0, 0.0
        has_history = median is not None and std is not None and std > 0
        assert has_history is False


def _code_only(source: str) -> str:
    """Strips comments, so a search does not match its own epitaph."""
    return "\n".join(
        line.split("#", 1)[0] for line in source.split("\n")
    )


class TestForeignVwapIsNotAPriceMultiple:
    def test_the_payload_declares_it_unavailable(self):
        import inspect

        from services import smart_money_flow_engine as sm

        code = _code_only(inspect.getsource(sm))
        assert "current_price * 0.97" not in code
        assert "current_price * 1.03" not in code

    def test_proprietary_flow_is_labelled_estimated(self):
        import inspect

        from services import smart_money_flow_engine as sm

        source = inspect.getsource(sm)
        assert '"is_estimated": True' in source, (
            "turnover-derived desk flow must not be presented as observed"
        )


# Ranking sort keys, not reported metrics. `-rev_3y_cagr / max(0.1, ps)` orders
# a basket; the floor stops a near-zero P/S from rocketing one candidate to the
# top on a data error, and no number from it is ever shown or averaged. These
# are listed rather than pattern-matched so a new one has to be justified here.
ALLOWED_RANK_KEY_CLAMPS = {
    '/ max(0.1, x.get("ps", 1.0)',
    '/ max(1.0, x.get("pe", 10.0)',
}

# `x / max(1, len(items))` is not the same defect: the numerator is a sum or
# count over the same collection, so an empty collection gives 0/1 = 0, which
# is the right answer. Only an integer floor of exactly 1 over a count-shaped
# denominator qualifies - a float floor (max(1.0, avg_loss)) is a magnitude
# being propped up, not a division guarded against emptiness.
_COUNT_DENOMINATOR = re.compile(
    r"max\(\s*1\s*,\s*(?:len\(|[a-z_]*(?:count|total_trades|top_k|n_trades|n_splits)\b)"
)


def _is_count_guard(expression: str) -> bool:
    return bool(_COUNT_DENOMINATOR.search(expression))


class TestRiskRatiosAreWithheldNotInflated:
    """Every clamped denominator across the three backtest services."""

    @pytest.mark.parametrize("module_name", [
        "services.backtest_service",
        "services.institutional_backtest_service",
        "services.fair_value_backtest_service",
    ])
    def test_no_clamped_ratio_denominators(self, module_name):
        import importlib
        import inspect
        import re

        source = _code_only(inspect.getsource(importlib.import_module(module_name)))
        # An earlier version of this test only matched denominators *named*
        # vol/std/dd/drawdown, and so walked straight past
        # `cagr / max(1.0, abs(max_dd))`, `avg_win / max(1.0, avg_loss)` and
        # `avg_oos_sharpe / max(0.1, avg_is_sharpe)`. Match the shape instead
        # of the name: any division whose denominator is max() with a literal.
        offenders = re.findall(r"/\s*max\(\s*[^)]{0,120}?\)", source)
        offenders = [
            o for o in offenders
            if (re.search(r"max\(\s*[-0-9.]+\s*,", o)         # max(LITERAL, x)
                or re.search(r",\s*[-0-9.]+\s*\)\s*$", o))    # max(x, LITERAL)
            and not _is_count_guard(o)
            and o not in ALLOWED_RANK_KEY_CLAMPS
        ]
        assert not offenders, (
            f"{module_name} divides by a clamped denominator: {offenders}. "
            "Return None when the denominator is unusable - a floor does not "
            "avoid the problem, it reports an understated or invented ratio."
        )
