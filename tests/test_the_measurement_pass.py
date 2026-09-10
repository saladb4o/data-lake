"""The pass must report a stage that died, and rank what dying costs.

Two failures it exists to prevent. A measurement that fails silently -
every stage is piped to tee, and a piped stage's exit status is tee's
unless pipefail is set inside that shell, so the run goes green while the
number nobody read was never produced. And a pass that loses an input
lake reporting success because the measurements it could no longer make
were the optional ones.
"""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = os.path.join(ROOT, "scripts", "run_the_measurement_pass.sh")

STAGES = ("sync_unified_market_data", "sync_historical_prices",
          "build_historical_fundamentals", "score_code_candidates",
          "measure_the_backtest", "audit_valuation_coverage")


@pytest.fixture
def sandbox(tmp_path):
    """A copy of the pass with every stage stubbed to succeed."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "data").mkdir()
    shutil.copy(PASS, tmp_path / "scripts")
    for name in STAGES:
        (tmp_path / "scripts" / f"{name}.py").write_text(
            "#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
    (tmp_path / "data" / "code_candidates_probe.json").write_text("{}")
    return tmp_path


def _fail(sandbox, name, code=3):
    (sandbox / "scripts" / f"{name}.py").write_text(
        f"#!/usr/bin/env python3\nimport sys\nsys.exit({code})\n",
        encoding="utf-8")


def _run(sandbox):
    return subprocess.run(
        ["bash", "scripts/run_the_measurement_pass.sh"],
        cwd=sandbox, capture_output=True, text=True,
        env={**os.environ,
             "DATA_LOCAL_DIR": str(sandbox / "data"),
             "GITHUB_STEP_SUMMARY": str(sandbox / "summary.md")})


class TestAStageThatDiesIsNamed:
    @pytest.mark.parametrize("stage", STAGES)
    def test_each_stage_failing_is_reported(self, sandbox, stage):
        _fail(sandbox, stage)
        out = _run(sandbox).stdout
        assert "did not complete" in out, (
            f"{stage} failed and the pass said every stage completed")

    def test_a_piped_stage_is_not_hidden_by_tee(self, sandbox):
        """The specific bug: tee's exit status is always zero."""
        _fail(sandbox, "measure_the_backtest")
        out = _run(sandbox).stdout
        assert "**backtest sweep** did not complete" in out

    def test_a_clean_pass_says_so(self, sandbox):
        result = _run(sandbox)
        assert result.returncode == 0
        assert "every stage completed" in result.stdout


class TestLosingAnInputIsWorseThanLosingAMeasurement:
    @pytest.mark.parametrize("stage", ["sync_unified_market_data",
                                       "sync_historical_prices",
                                       "build_historical_fundamentals"])
    def test_an_input_stage_failing_fails_the_pass(self, sandbox, stage):
        _fail(sandbox, stage)
        assert _run(sandbox).returncode == 1

    @pytest.mark.parametrize("stage", ["score_code_candidates",
                                       "measure_the_backtest",
                                       "audit_valuation_coverage"])
    def test_a_measurement_failing_still_delivers_the_lakes(self, sandbox, stage):
        """The lakes were built; the run must not throw that away."""
        _fail(sandbox, stage)
        result = _run(sandbox)
        assert result.returncode == 0
        assert "did not complete" in result.stdout


class TestTheInventoryIsHonest:
    def test_missing_outputs_are_named_as_missing(self, sandbox):
        out = _run(sandbox).stdout
        assert "**missing**" in out, (
            "stubs write no files, so every output must read as missing")

    def test_a_written_output_is_sized(self, sandbox):
        (sandbox / "data" / "coverage.json").write_text('{"a": 1}')
        out = _run(sandbox).stdout
        assert "| coverage.json | 8 |" in out


class TestTheStagesRunInDependencyOrder:
    def test_the_lake_is_built_before_it_is_measured(self, sandbox):
        out = _run(sandbox).stdout
        assert (out.index("fundamentals lake")
                < out.index("backtest sweep")), "the sweep reads the lake"

    def test_the_coverage_headline_is_printed_last(self, sandbox):
        """A log can only be read from its tail."""
        out = _run(sandbox).stdout
        assert (out.index("coverage audit")
                > out.index("backtest sweep"))
