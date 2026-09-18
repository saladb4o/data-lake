"""Beta is a measurement, so the thing that measures it has to be checked.

The old WACC sheet carried eighteen betas typed in from a 2021 data pull,
with no way to tell a good one from a stale one. Replacing them with
computed betas only helps if the computation is right, so these tests
build price series whose beta is known by construction and ask for it
back. No network, no spreadsheet engine.
"""

import math
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "xlsxvas"))

import fill_peers as F                       # noqa: E402


def series_with_beta(beta, n=600, noise=0.0, seed=7):
    """An index walk, and a stock that moves beta times as much."""
    rng = random.Random(seed)
    index = [100.0]
    stock = [50.0]
    for _ in range(n):
        step = rng.gauss(0, 0.012)
        index.append(index[-1] * math.exp(step))
        wobble = rng.gauss(0, noise) if noise else 0.0
        stock.append(stock[-1] * math.exp(beta * step + wobble))
    return stock, index


class TestTheSlopeIsTheBeta:
    @pytest.mark.parametrize("target", [0.6, 1.0, 1.45])
    def test_a_known_beta_comes_back(self, target):
        stock, index = series_with_beta(target)
        got = F.ols_beta(F.log_returns(stock), F.log_returns(index))
        assert got is not None
        beta, n, r2 = got
        assert beta == pytest.approx(target, abs=1e-9)
        assert n == len(stock) - 1
        assert r2 == pytest.approx(1.0, abs=1e-9)

    def test_noise_widens_the_fit_without_moving_the_slope(self):
        stock, index = series_with_beta(1.2, noise=0.01)
        beta, n, r2 = F.ols_beta(F.log_returns(stock), F.log_returns(index))
        assert beta == pytest.approx(1.2, abs=0.12)
        assert r2 < 0.95


class TestTooLittleDataIsNotABeta:
    def test_a_short_series_returns_nothing(self):
        stock, index = series_with_beta(1.0, n=40)
        assert F.ols_beta(F.log_returns(stock), F.log_returns(index)) is None

    def test_a_flat_index_returns_nothing(self):
        index = [100.0] * 400
        stock = [50.0 * (1 + i * 0.001) for i in range(400)]
        assert F.ols_beta(F.log_returns(stock), F.log_returns(index)) is None


class TestOnlyDaysBothTradedCount:
    def test_a_day_the_stock_missed_is_dropped_not_zero_filled(self):
        """A halted day is not a day of zero return.

        Filling it with zero would be an observation nobody made, and it
        pulls beta toward zero in exactly the illiquid names where beta
        matters most.
        """
        stock = {"2024-01-01": 10.0, "2024-01-03": 11.0}
        index = {"2024-01-01": 100.0, "2024-01-02": 101.0,
                 "2024-01-03": 103.0}
        s, i = F.aligned(stock, index)
        assert s == [10.0, 11.0]
        assert i == [100.0, 103.0]

    def test_a_non_positive_price_does_not_become_a_return(self):
        assert all(math.isnan(r) for r in F.log_returns([0.0, 5.0]))
        assert all(math.isnan(r) for r in F.log_returns([5.0, 0.0]))

    def test_missing_pairs_drop_out_of_the_regression(self):
        stock = F.log_returns([10.0, 11.0, 0.0, 12.0, 13.0] * 60)
        index = F.log_returns([100.0, 101.0, 102.0, 103.0, 104.0] * 60)
        got = F.ols_beta(stock, index)
        assert got is not None
        _, n, _ = got
        assert n < len([x for x in index])


class TestTheHistoryShapeIsReadNotAssumed:
    def test_dict_candles(self):
        got = F.closes_by_date({"candles": [
            {"time": "2024-01-02T00:00:00", "close": 12.5},
            {"date": "2024-01-03", "c": 12.9}]})
        assert got == {"2024-01-02": 12.5, "2024-01-03": 12.9}

    def test_list_candles(self):
        got = F.closes_by_date(
            {"data": [["2024-01-02", 1, 2, 3, 12.5, 100]]})
        assert got == {"2024-01-02": 12.5}

    def test_an_empty_answer_is_not_a_zero_price(self):
        assert F.closes_by_date({}) == {}
        assert F.closes_by_date({"candles": [{"time": "2024-01-02"}]}) == {}
