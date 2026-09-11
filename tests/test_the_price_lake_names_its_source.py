"""Prices come from a source that is tried, not from a source that is claimed.

The price stage advertised TradingView in two places - the module header
and the `source` field of the saved lake - while fetching from yfinance
with a vnstock fallback and never contacting TradingView at all. A label
nobody can check was read as evidence that TradingView already carried
the lake.

It is now DNSE, then vnstock, and the lake records which one answered
for each symbol. SSI, TCBS and yfinance were each tried on a full pass,
answered for nobody, and were deleted rather than left flagged off.
These tests pin the parser's refusals and the ordering; whether the
endpoint answers at all is a question only a runner can settle, and the
tally exists to settle it.
"""
from __future__ import annotations

import inspect

import pytest

from services.broker_prices import fetch_dnse, parse_udf


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class TestTheUdfParserRefusesWhatItCannotTrust:
    def test_a_well_formed_payload_becomes_rows(self):
        rows = parse_udf({"s": "ok", "t": [1451606400, 1451692800],
                          "o": [1.0, 2.0], "h": [3.0, 4.0], "l": [0.5, 1.5],
                          "c": [2.5, 3.5], "v": [100, 200]})
        assert rows is not None and len(rows) == 2
        assert rows[0]["time"] == "2016-01-01"
        assert rows[1]["close"] == 3.5

    def test_a_short_column_is_refused_rather_than_zipped(self):
        # Truncated response. Zipping unequal arrays pairs one day's close
        # with another day's open - silently, across years of history.
        assert parse_udf({"s": "ok", "t": [1, 2, 3], "o": [1.0, 2.0, 3.0],
                          "h": [1.0, 2.0, 3.0], "l": [1.0, 2.0, 3.0],
                          "c": [1.0, 2.0], "v": [1, 2, 3]}) is None

    def test_no_data_is_none_not_an_empty_frame(self):
        assert parse_udf({"s": "no_data"}) is None
        assert parse_udf({"s": "ok", "t": []}) is None
        assert parse_udf("not a dict") is None


class TestTheFetcherKeepsItsPromises:
    def test_the_whole_window_is_asked_for_in_one_request(self, monkeypatch):
        asked = []

        def _get(url, params=None, **kwargs):
            asked.append(params)
            return _Resp({"s": "ok", "t": [1451606400], "o": [1.0],
                          "h": [1.0], "l": [1.0], "c": [1.0], "v": [1]})

        monkeypatch.setattr("services.broker_prices.requests.get", _get)
        assert fetch_dnse("FPT")
        assert len(asked) == 1
        assert asked[0]["symbol"] == "FPT"
        # Not an intraday resolution: the 90-day ceiling vietfin documents
        # is a property of those, and asking for one would inherit a limit
        # that does not apply to daily bars.
        assert asked[0]["resolution"] == "1D"

    def test_a_symbol_with_nothing_is_none_not_an_empty_frame(
            self, monkeypatch):
        monkeypatch.setattr("services.broker_prices.requests.get",
                            lambda *a, **k: _Resp({"s": "no_data"}))
        # None, not [], so the caller can tell "this source has nothing"
        # from "this source returned no candles" and fall through.
        assert fetch_dnse("ZZZ") is None

    def test_a_non_200_falls_through_instead_of_raising(self, monkeypatch):
        monkeypatch.setattr("services.broker_prices.requests.get",
                            lambda *a, **k: _Resp({}, status=503))
        assert fetch_dnse("FPT") is None

    def test_verification_is_never_switched_off(self, monkeypatch):
        seen = {}

        def _get(url, params=None, **kwargs):
            seen.update(kwargs)
            return _Resp({"s": "no_data"})

        monkeypatch.setattr("services.broker_prices.requests.get", _get)
        fetch_dnse("FPT")
        # scripts/fetch_tradingview.js opens with
        # NODE_TLS_REJECT_UNAUTHORIZED = '0'. Not inheriting that was the
        # whole reason for going to the broker over HTTPS directly.
        assert seen.get("verify") is not False


class TestTheLakeRecordsWhoAnswered:
    def _body(self):
        import scripts.sync_historical_prices as sync
        return inspect.getsource(sync.sync_all_symbols)

    def test_the_saved_source_is_a_tally_not_a_slogan(self):
        body = self._body()
        assert "TradingView & Yahoo Finance Live Data Feeds" not in body
        assert "by_source" in body

    def test_the_broker_is_tried_before_the_fallback(self):
        body = self._body()
        assert body.index("_fetch_from_broker") < body.index('record("vnstock")')

    def test_yfinance_is_gone_from_the_price_path(self):
        import scripts.sync_historical_prices as sync
        # It answered for 0 of the 36 DNSE missed on run 34586582908,
        # has never been measured carrying one symbol of this lake, and
        # printed a "possibly delisted" block per ticker while doing it.
        assert not hasattr(sync, "fetch_from_yfinance")
        assert "yf.download" not in self._body()

    def test_a_source_measured_at_zero_is_gone_not_flagged_off(self):
        import services.broker_prices as bp
        import scripts.sync_historical_prices as sync
        # SSI and TCBS answered for nobody on a full pass. Code kept "in
        # case it works again" is code nobody measures again, and its
        # circuit breaker would spend eighty requests a pass re-deriving
        # a result already in the log.
        assert not hasattr(bp, "fetch_ssi")
        assert not hasattr(bp, "fetch_tcbs")
        # dnse is kept, behind TradingView, because it is the only source
        # ever measured carrying this lake: 1,364 of 1,400 on run
        # 34586582908. TradingView is in front of it on a reason, not a
        # measurement, so the measured source stays as the fallback
        # until a run says otherwise.
        assert "dnse" in sync.BROKER_SOURCES

    def test_the_tally_is_written_where_a_reader_can_reach_it(self):
        # The job log is not readable from where these results get read:
        # the artifact host is refused and the log API serves only the
        # tail. A table printed mid-stage is a table nobody sees.
        assert "price_sources.md" in self._body()

    def test_a_dead_endpoint_is_dropped_rather_than_asked_1500_times(self):
        import scripts.sync_historical_prices as sync
        assert sync.PROBE_BEFORE_GIVING_UP > 0
        assert "PROBE_BEFORE_GIVING_UP" in self._body()

    def test_every_named_source_can_actually_be_dispatched(self):
        # A name in BROKER_SOURCES with no fetcher behind it would raise
        # KeyError once per symbol and be swallowed as a failed fetch -
        # the source would report zero and look dead rather than absent.
        # It used to look for every fetcher in services.broker_prices,
        # which was true only while every source spoke HTTP. TradingView
        # speaks a WebSocket through a Node subprocess and lives in its
        # own module, so the requirement is that the dispatch table
        # resolves - not where the function happens to live.
        import inspect

        import scripts.sync_historical_prices as sync

        body = inspect.getsource(sync._fetch_from_broker)
        for source in sync.BROKER_SOURCES:
            assert f'"{source}"' in body, (source, body)


class TestNoUncheckableClaimSurvivesInThePricePath:
    """The TradingView banner was believed because nobody could check it.

    `compute_stock_quarterly_returns` advertised "VND scale normalization"
    in its docstring and performed none - the same species of defect, in
    the same file, and a more expensive one: the backtest compares the
    lake price *absolutely* against a fair value built from VND
    fundamentals, so a source quoting thousands would read as a 99.9%
    discount on every symbol rather than as an error.
    """

    def test_the_returns_function_does_not_promise_a_normalisation(self):
        import inspect

        import scripts.sync_historical_prices as sync

        doc = (sync.compute_stock_quarterly_returns.__doc__ or "")
        body = inspect.getsource(sync.compute_stock_quarterly_returns)
        claims = "scale normalization" in doc.lower()
        # Whatever the docstring says, it has to be visible in the body.
        performs = any(tok in body for tok in ("1000", "1_000", "scale_factor"))
        assert not claims or performs

    def test_every_filtered_out_symbol_is_reported_rather_than_dropped(self):
        # 1,400 of the universe's 1,524 symbols reach the price sync. The
        # other 124 were reported as "no price" by every table downstream,
        # indistinguishable from a symbol the sources actually refused.
        body = open(
            "scripts/sync_historical_prices.py", encoding="utf-8").read()
        assert "price_universe.md" in body
        assert "filtered out before any fetch" in body


class TestThePriceLakeIsInDong:
    """Run 34605559771 compared the lake against the screener's own price.

    Every one of 1,367 symbols came back a factor of ~941 apart - EVS at
    4,800 against a lake close of 5.10. DNSE quotes in thousands of dong,
    and so did the yfinance/vnstock path before it, which is why swapping
    vendors moved the backtest by 0.01 and read as confirmation that the
    scale was fine. Two sources wrong the same way cannot check each
    other.

    It is not cosmetic. `fair_value_backtest_service` compares this price
    absolutely against a fair value built from dong fundamentals, so a
    close of 5.10 is a ~100% discount on every symbol and the eps/bvps
    floors beat every real figure - which is why the lag sweep has never
    moved off 0.00 points.
    """

    def _frame(self, closes):
        import pandas as pd

        return pd.DataFrame({
            "time": [f"2020-01-{i + 1:02d}" for i in range(len(closes))],
            "open": closes, "high": closes, "low": closes,
            "close": closes, "volume": [1] * len(closes)})

    def test_a_series_in_thousands_is_multiplied_into_dong(self):
        import scripts.sync_historical_prices as sync

        df = self._frame([5.10, 5.20, 4.90])
        assert sync.normalise_to_dong("EVS", df) == "thousands"
        assert df["close"].tolist() == [5100.0, 5200.0, 4900.0]
        # Every OHLC column, not just close: a quarter's high and low are
        # read from the same frame and would otherwise stay in thousands.
        assert df["high"].iloc[0] == 5100.0
        assert df["low"].iloc[0] == 5100.0
        assert df["open"].iloc[0] == 5100.0

    def test_a_series_already_in_dong_is_left_alone(self):
        import scripts.sync_historical_prices as sync

        df = self._frame([48000.0, 47500.0, 49000.0])
        assert sync.normalise_to_dong("FPT", df) == "dong"
        assert df["close"].tolist() == [48000.0, 47500.0, 49000.0]

    def test_one_bad_print_does_not_decide_the_unit(self):
        import scripts.sync_historical_prices as sync

        # A decade of dong prices with a single stray decimal in it. A
        # mean would be dragged; the median is not, and the unit must be
        # decided for the series rather than by its worst bar.
        df = self._frame([48000.0, 47500.0, 0.48, 49000.0, 48500.0])
        assert sync.normalise_to_dong("FPT", df) == "dong"

    def test_the_scale_each_symbol_arrived_on_is_counted(self):
        import inspect

        import scripts.sync_historical_prices as sync

        body = inspect.getsource(sync.sync_all_symbols)
        # Counted next to the sources, for the same reason: a vendor that
        # changes units should be a number that moves, not a backtest
        # that quietly stops using its filings.
        assert "by_unit" in body
        assert "normalise_to_dong" in body

    def test_the_normalisation_is_applied_on_every_path(self):
        import inspect

        import scripts.sync_historical_prices as sync

        body = inspect.getsource(sync.sync_all_symbols)
        # Once for the broker loop and once for the vnstock fallback. A
        # source normalised on one path and not the other puts two scales
        # in one file, which is worse than one wrong scale.
        assert body.count("normalise_to_dong") == 2

    def test_the_probe_refuses_a_lake_off_the_screeners_scale(self):
        import inspect

        import scripts.probe_the_open_questions as probe

        body = inspect.getsource(probe.main)
        # The stage has to go red. A gate that only prints is how a
        # thousand-fold error survived every run that measured it.
        assert "return 0 if on_scale else 1" in body


class TestTheCarriedOverLakeCannotKeepTheOldScale:
    """A rerun on a pre-normalisation lake must not trust what it finds.

    The sync refetches only symbols it is missing or that hold fewer than
    eight quarters, so a lake built while the prices were in thousands
    would survive a rerun untouched and be merged, symbol by symbol, with
    records in dong. Nothing downstream compares two symbols' scales
    against each other, so the seam would be invisible.
    """

    def test_a_written_record_says_what_scale_it_is_on(self):
        import pandas as pd
        import scripts.sync_historical_prices as sync
        dates = pd.date_range("2020-01-01", periods=400, freq="D")
        df = pd.DataFrame({"time": dates, "open": 50000.0, "high": 50000.0,
                           "low": 50000.0, "close": 50000.0, "volume": 1000})
        out = sync.compute_stock_quarterly_returns("AAA", df)
        assert out["price_unit"] == sync.PRICE_UNIT == "dong"

    def test_a_cached_record_without_the_stamp_is_refetched(self):
        import scripts.sync_historical_prices as sync
        body = inspect.getsource(sync.sync_all_symbols)
        # The deep-enough test alone is what let the old scale through.
        assert 'price_unit") == PRICE_UNIT' in body
        assert "stale_scale" in body


class TestTradingViewWasMeasuredAndRemoved:
    """It was the source for exactly one run, and the run decided.

    Run 34627185323: 187 of 1,400 symbols in 1,800 seconds before the
    batch was killed on its timeout, 1,192 of them timing out, while
    DNSE answered for 1,177 of the remaining 1,213 in 140 seconds.
    Thirteen percent of the universe for thirteen times the wall clock.
    Removed on the rule that removed SSI and TCBS - a source is kept by
    the number next to it, not by preference.

    The run paid for itself anyway, and the payment is recorded in
    normalise_to_dong rather than here: it put 199 dong-quoted symbols
    and 1,228 thousands-quoted symbols into one file on one pass, and
    the median rule separated them per symbol with no vendor names
    involved. That is the only direct evidence the scale fix is a rule
    about data rather than a constant about DNSE.
    """

    def test_the_lake_is_back_on_the_source_that_was_measured_carrying_it(self):
        import scripts.sync_historical_prices as sync
        assert sync.BROKER_SOURCES == ("dnse",), sync.BROKER_SOURCES

    def test_the_measurement_is_written_down_where_the_next_attempt_reads_it(self):
        # Without the numbers, "we tried TradingView" is a memory, and
        # this path has already re-adopted a TradingView claim once on
        # nothing but a label.
        doc = __import__("scripts.sync_historical_prices",
                         fromlist=["x"]).__doc__ or ""
        assert "34627185323" in doc
        assert "187" in doc and "1,400" in doc

    def test_the_two_scale_run_is_recorded_next_to_the_rule_it_proved(self):
        import scripts.sync_historical_prices as sync
        doc = sync.normalise_to_dong.__doc__ or ""
        assert "199" in doc and "1,228" in doc, doc

    def test_no_javascript_here_turns_off_certificate_checking(self):
        import glob
        for path in sorted(glob.glob("scripts/*.js")):
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    if "NODE_TLS_REJECT_UNAUTHORIZED" in line:
                        # Only ever as prose describing what was removed.
                        # As an assignment it disables TLS for every
                        # connection the process makes, for the whole run.
                        assert line.lstrip().startswith("//"), (path, line)
