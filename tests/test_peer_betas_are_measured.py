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


class TestUnitsAreConvertedInOnePlace:
    """A board quotes 25.6 and means 25,600 dong.

    The screener carries a market capitalisation in ty dong beside a
    reference price in thousands. The workbook wants dong per share and
    millions of shares. Nothing in either number says which it is, so the
    conversion is written once and checked against a company whose share
    count is known.
    """

    def test_a_board_price_becomes_dong(self):
        assert F.price_in_dong(25.6) == 25600.0

    def test_acb_comes_back_with_the_shares_it_has(self):
        # 115,000 ty dong at 25.6; ACB has about 4.47 billion shares
        got = F.shares_in_millions(115_000, 25.6)
        assert got == pytest.approx(4492.0, abs=1.0)
        assert 4_000 < got < 5_000

    def test_the_conversion_survives_a_round_trip(self):
        cap_ty, ref = 142_000, 50.0
        shares_m = F.shares_in_millions(cap_ty, ref)
        rebuilt = shares_m * 1e6 * F.price_in_dong(ref)
        assert rebuilt == pytest.approx(cap_ty * 1e9, rel=1e-12)

    @pytest.mark.parametrize("cap,ref", [(0, 25.6), (115_000, 0),
                                         (None, 25.6), (115_000, None)])
    def test_a_missing_side_is_not_a_share_count(self, cap, ref):
        assert F.shares_in_millions(cap, ref) is None


class TestThePriceColumnIsWrittenOldestFirst:
    """The 52-week window sits at the bottom of the column.

    The sheet reads its high, low and average from the last 253 rows of a
    1,364-row column, so a series written newest-first would report the
    oldest year as the recent one - a number that looks entirely
    reasonable and is off by the length of the history.
    """

    def test_the_series_comes_back_in_date_order(self):
        history = {"candles": [
            {"time": "2024-03-01", "close": 30.0},
            {"time": "2024-01-01", "close": 10.0},
            {"time": "2024-02-01", "close": 20.0}]}
        got = F.price_history("X", lambda s: history)
        assert got == [("2024-01-01", 10.0), ("2024-02-01", 20.0),
                       ("2024-03-01", 30.0)]

    def test_no_history_is_an_empty_list_not_a_zero(self):
        assert F.price_history("X", lambda s: {}) == []
        assert F.price_history("X", lambda s: None) == []

    def test_the_sheet_has_room_for_the_window_it_reads(self):
        """The 52-week formulas read C1122:C1374."""
        room = F.PRICE_LAST_ROW - F.PRICE_FIRST_ROW + 1
        assert room >= 1374 - 1122 + 1
        assert F.PRICE_FIRST_ROW > 10        # below the column header
