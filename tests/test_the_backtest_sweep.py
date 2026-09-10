"""The sweep must ask each lag its own question, and survive a bad row.

Its whole reason to exist is that one process answers what used to take a
workflow run each. That only holds if every lag really is run, a failure
in one row does not end the pass, and a sweep that valued nothing says so
instead of printing an impressive empty table.
"""
import os
import subprocess
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "measure_the_backtest.py")


def _run(stub: str, argv: str) -> subprocess.CompletedProcess:
    """Runs the sweep with a stubbed service, in its own interpreter."""
    # Not dedented after interpolation: the stub is multi-line, and its
    # own indentation would decide the common prefix for everything.
    harness = "\n".join([
        "import sys, types",
        f"sys.path.insert(0, {ROOT!r})",
        stub,
        'module = types.ModuleType("services.fair_value_backtest_service")',
        "module.FairValueBacktestService = StubService",
        "class FundamentalsMode:",
        '    POINT_IN_TIME = "point_in_time"',
        '    SNAPSHOT_PROJECTED = "snapshot_projected"',
        "module.FundamentalsMode = FundamentalsMode",
        'sys.modules["services.fair_value_backtest_service"] = module',
        f'sys.argv = ["measure_the_backtest.py"] + {argv!r}.split()',
        f'exec(open({SCRIPT!r}, encoding="utf-8").read(),',
        f'     {{"__name__": "__main__", "__file__": {SCRIPT!r}}})',
    ])
    return subprocess.run([sys.executable, "-c", harness],
                          capture_output=True, text=True)


PAYLOAD = textwrap.dedent("""
    class Payload:
        def __init__(self, lag):
            self.metrics = {"total_return_pct": 10.0 + lag,
                            "cagr_pct": 1.0 * lag, "excess_cagr_pct": 2.0,
                            "max_drawdown_pct": -5.0, "sharpe_ratio": None,
                            "win_rate_pct": 55.0, "total_trades": 12}
            self.diagnostics = {"fundamentals": {
                "symbol_quarters_valued": 100 + lag,
                "symbol_quarters_skipped_no_filing": 3,
                "symbols_in_lake": 1380, "is_evidence_of_skill": True}}
            self.trades = [1, 2, 3]
""")


class TestEveryLagIsActuallyRun:
    def test_each_lag_reaches_the_service_once(self):
        stub = PAYLOAD + textwrap.dedent("""
            SEEN = []
            class StubService:
                def run_backtest(self, **kw):
                    SEEN.append(kw.get("publication_lag_days"))
                    print("LAG", kw.get("publication_lag_days"),
                          kw.get("fundamentals_mode"))
                    return Payload(kw.get("publication_lag_days") or 0)
        """)
        res = _run(stub, "--lags 20 90 --skip-snapshot")
        assert res.returncode == 0, res.stderr
        assert "LAG 20 point_in_time" in res.stdout
        assert "LAG 90 point_in_time" in res.stdout

    def test_the_snapshot_contrast_runs_in_the_other_mode(self):
        stub = PAYLOAD + textwrap.dedent("""
            class StubService:
                def run_backtest(self, **kw):
                    print("MODE", kw.get("fundamentals_mode"))
                    return Payload(45)
        """)
        res = _run(stub, "--lags 45")
        assert "MODE snapshot_projected" in res.stdout


class TestOneBadRowDoesNotEndTheSweep:
    def test_a_failing_lag_is_reported_and_the_rest_still_run(self):
        stub = PAYLOAD + textwrap.dedent("""
            class StubService:
                def run_backtest(self, **kw):
                    if kw.get("publication_lag_days") == 30:
                        raise RuntimeError("price lake missing")
                    print("OK", kw.get("publication_lag_days"))
                    return Payload(kw.get("publication_lag_days") or 0)
        """)
        res = _run(stub, "--lags 20 30 45 --skip-snapshot")
        assert res.returncode == 0, "one bad row must not fail the sweep"
        assert "OK 20" in res.stdout and "OK 45" in res.stdout
        assert "FAILED" in res.stdout


class TestTheSweepReportsItsOwnEmptiness:
    def test_valuing_nothing_is_called_out_not_tabulated(self):
        """An empty lake produces a clean table of zeros otherwise."""
        stub = textwrap.dedent("""
            class Payload:
                def __init__(self, lag):
                    self.metrics = {"total_return_pct": 0.0, "cagr_pct": 0.0,
                                    "excess_cagr_pct": 0.0,
                                    "max_drawdown_pct": 0.0,
                                    "sharpe_ratio": None, "win_rate_pct": 0.0,
                                    "total_trades": 0}
                    self.diagnostics = {"fundamentals": {
                        "symbol_quarters_valued": 0,
                        "symbol_quarters_skipped_no_filing": 900,
                        "symbols_in_lake": 0}}
                    self.trades = []
            class StubService:
                def run_backtest(self, **kw):
                    return Payload(0)
        """)
        res = _run(stub, "--lags 45 --skip-snapshot")
        assert "nothing was valued at any lag" in res.stdout
        assert "the lake was not read" in res.stdout

    def test_the_spread_across_lags_is_stated(self):
        stub = PAYLOAD + textwrap.dedent("""
            class StubService:
                def run_backtest(self, **kw):
                    return Payload(kw.get("publication_lag_days") or 0)
        """)
        res = _run(stub, "--lags 20 90 --skip-snapshot")
        # cagr_pct == lag in the stub, so the spread is 70 points.
        assert "spread **70.00 points**" in res.stdout
