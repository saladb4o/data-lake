"""
Tests for services/rrg_service.py (RRG / Sector Rotation pure math).

No network: all series are synthetic geometric random walks with fixed seeds.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest

from services.rrg_service import (
    build_rrg_matrix,
    classify_quadrant,
    compute_rs_series,
    compute_rrg_series,
)


def make_candles(values, start="2024-01-01"):
    idx = pd.bdate_range(start=start, periods=len(values))
    return [{"time": d.strftime("%Y-%m-%d"), "close": float(v)} for d, v in zip(idx, values)]


def geo_walk(n, mu=0.0005, sigma=0.01, seed=42, s0=1000.0):
    rng = np.random.default_rng(seed)
    rets = rng.normal(mu, sigma, size=n)
    return list(s0 * np.cumprod(1.0 + rets))


N = 200


@pytest.fixture(scope="module")
def bench():
    return geo_walk(N, seed=1)


class TestComputeRsSeries:
    def test_length_matches_input(self):
        sec = [1.0, 2.0, 3.0] * 30
        bm = [2.0, 4.0, 6.0] * 30  # RS constant at 0.5
        out = compute_rs_series(sec, bm, m=14)
        assert len(out) == len(sec)
        assert np.allclose(out, 0.5)

    def test_smoothing_reduces_noise(self, bench):
        rng = np.random.default_rng(7)
        noisy = list(np.asarray(bench) * rng.normal(1.0, 0.05, size=N))
        rs_raw = np.asarray(noisy) / np.asarray(bench)
        rs_smooth = compute_rs_series(noisy, bench, m=14)
        assert np.nanstd(rs_smooth[20:]) < np.nanstd(rs_raw[20:])

    def test_equal_length_required(self):
        with pytest.raises(ValueError):
            compute_rs_series([1.0, 2.0], [1.0])


class TestClassifyQuadrant:
    @pytest.mark.parametrize(
        "x,y,expected",
        [
            (105.0, 105.0, "Leading"),
            (105.0, 100.0, "Weakening"),
            (105.0, 95.0, "Weakening"),
            (95.0, 95.0, "Lagging"),
            (100.0, 95.0, "Lagging"),
            (95.0, 105.0, "Improving"),
            (100.0, 101.0, "Improving"),
        ],
    )
    def test_obvious_cases(self, x, y, expected):
        assert classify_quadrant(x, y) == expected


class TestComputeRrgSeries:
    def test_identical_sector_ratio_is_100(self, bench):
        rs = compute_rs_series(bench, bench, m=14)
        out = compute_rrg_series(rs)
        assert out["rs_ratio"][-1] == pytest.approx(100.0, abs=1e-9)
        assert out["rs_momentum"][-1] == pytest.approx(100.0, abs=1e-9)

    def test_output_lengths_aligned(self, bench):
        sec = geo_walk(N, mu=0.003, seed=5)
        rs = compute_rs_series(sec, bench, m=14)
        for method in ("jdk", "enhanced"):
            out = compute_rrg_series(rs, k=10, method=method)
            assert len(out["rs_ratio"]) == len(out["rs_momentum"]) > 0
            assert all(np.isfinite(out["rs_ratio"]))
            assert all(np.isfinite(out["rs_momentum"]))

    def test_outperformer_above_100(self, bench):
        strong = list(np.asarray(bench) * np.linspace(1.0, 3.0, N))
        weak = list(np.asarray(bench) * np.linspace(1.0, 1 / 3.0, N))
        rs_strong = compute_rs_series(strong, bench, m=14)
        rs_weak = compute_rs_series(weak, bench, m=14)
        o_strong = compute_rrg_series(rs_strong)
        o_weak = compute_rrg_series(rs_weak)
        assert o_strong["rs_ratio"][-1] > 110.0
        assert o_weak["rs_ratio"][-1] < 90.0

    def test_enhanced_method_scales(self, bench):
        strong = list(np.asarray(bench) * np.linspace(1.0, 2.5, N))
        rs = compute_rs_series(strong, bench, m=14)
        out = compute_rrg_series(rs, method="enhanced")
        # Enhanced ratio is a % of rolling mean -> near but distinguishable from 100.
        assert 90.0 < out["rs_ratio"][-1] < 200.0
        assert out["rs_momentum"][-1] != pytest.approx(100.0)


class TestBuildRrgMatrix:
    def _matrix(self, bench_values, sectors, tail=8, **kw):
        return build_rrg_matrix(
            {code: make_candles(vals) for code, vals in sectors.items()},
            make_candles(bench_values),
            tail=tail,
            sector_names={c: f"Sector {c}" for c in sectors},
            **kw,
        )

    def test_leading_and_lagging_quadrants(self, bench):
        # Reconstruct benchmark daily returns, then add a growing relative
        # drift so outperformance accelerates (ROC rises -> momentum > 100).
        bench_rets = np.diff(np.asarray(bench)) / np.asarray(bench)[:-1]
        strong = list(1000.0 * np.cumprod(1.0 + bench_rets + np.linspace(0.002, 0.010, N - 1)))
        weak = list(1000.0 * np.cumprod(1.0 + bench_rets - np.linspace(0.002, 0.010, N - 1)))
        res = self._matrix(
            bench,
            {"STRONG": strong, "WEAK": weak},
        )
        pts = {p["sector_code"]: p for p in res["points"]}
        assert pts["STRONG"]["quadrant"] == "Leading"
        assert pts["STRONG"]["sector_name"] == "Sector STRONG"
        assert pts["WEAK"]["quadrant"] == "Lagging"
        assert pts["STRONG"]["rs_ratio"] > pts["WEAK"]["rs_ratio"]

    def test_tail_length_and_shape(self, bench):
        strong = list(np.asarray(bench) * np.linspace(1.0, 2.0, N))
        res = self._matrix(bench, {"A": strong}, tail=6)
        pt = res["points"][0]
        assert len(pt["tail"]) == 6
        for t in pt["tail"]:
            assert set(t.keys()) == {"time", "x", "y"}
            assert np.isfinite(t["x"]) and np.isfinite(t["y"])
        times = [t["time"] for t in pt["tail"]]
        assert times == sorted(times)  # chronological

    def test_date_alignment_with_extra_days(self, bench):
        # Sector has extra leading days that the benchmark lacks.
        extra = pd.bdate_range("2023-11-01", periods=15).strftime("%Y-%m-%d")
        strong = list(np.asarray(bench) * np.linspace(1.0, 2.2, N))
        candles = [{"time": t, "close": 100.0} for t in extra]
        candles += make_candles(strong)
        res = build_rrg_matrix({"X": candles}, make_candles(bench), tail=5, m=14, k=10)
        pt = res["points"][0]
        assert "error" not in pt
        bench_times = {t["time"] for t in make_candles(bench)}
        assert all(t["time"] in bench_times for t in pt["tail"])

    def test_error_for_too_short_sector(self, bench):
        short = geo_walk(30, seed=9)
        res = self._matrix(bench, {"SHORT": short}, m=14, k=10)
        pt = res["points"][0]
        assert "error" in pt
        assert "insufficient" in pt["error"]
        assert pt["sector_name"] == "Sector SHORT"

    def test_no_sectors_ok(self, bench):
        res = self._matrix(bench, {})
        assert res == {"method": "jdk", "points": []}

    def test_enhanced_matrix_runs(self, bench):
        strong = list(np.asarray(bench) * np.linspace(1.0, 2.2, N))
        res = self._matrix(bench, {"E": strong}, method="enhanced", m=14, k=10)
        pt = res["points"][0]
        assert "error" not in pt
        assert isinstance(pt["rs_ratio"], float)
