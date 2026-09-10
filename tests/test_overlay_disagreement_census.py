"""Measuring whether the two vendors ever contradict each other.

The overlay is a cascade: `if not tv.get(x) and vnd.get(x)`. TradingView
wins whenever it answers, and VNDIRECT is then never read, so the two are
never compared and a contradiction between them cannot be seen from
anywhere in the pipeline.

Turning that into a union has been on the list for several sessions on the
assumption that it would raise coverage. It would not. Two vendors both
reporting a figure leaves it at tier 3, exactly where one vendor leaves
it, so no symbol becomes valuable that was not. The only thing a union
buys is noticing that the published number is wrong - which makes the
disagreement rate the entire case for doing the work, and this section
measures it before anybody spends a day on it.
"""
import json

import pytest

from scripts import vendor_census as census


class TestTheComparison:
    def test_equal_figures_agree(self):
        assert census._agreement(100.0, 100.0) == "agree"

    def test_a_rounding_difference_still_agrees(self):
        # Vendors round and restate; an exact-match test would report the
        # whole universe as contradictory and the run would say nothing.
        assert census._agreement(1000.0, 1001.0) == "agree"

    def test_a_real_difference_is_reported(self):
        assert census._agreement(100.0, 180.0) == "differ"

    def test_a_billion_fold_gap_is_a_unit_not_a_contradiction(self):
        # The engine keeps some fields in billions and the vendor sends raw
        # dong. Counting that as disagreement would send the next run
        # chasing a unit conversion it already knows about.
        assert census._agreement(5.0, 5.0e9) == "scaled"
        assert census._agreement(5.0e9, 5.0) == "scaled"

    def test_an_absent_figure_is_not_a_disagreement(self):
        # Absent is not disagreement - the same rule the cash flow identity
        # check follows. Without it a sparse vendor looks like a lying one.
        assert census._agreement(None, 5.0) is None
        assert census._agreement(5.0, None) is None

    def test_two_zeros_agree_rather_than_dividing_by_zero(self):
        assert census._agreement(0.0, 0.0) == "agree"

    def test_a_zero_against_a_number_is_a_disagreement(self):
        # One vendor saying nil and the other saying a billion is the most
        # consequential disagreement there is, and a relative test anchored
        # on the wrong side would swallow it.
        assert census._agreement(0.0, 1.0e9) == "differ"

    def test_a_string_is_not_compared(self):
        assert census._agreement("n/a", 5.0) is None


class TestThePopulation:
    def test_only_vendor_reported_fields_are_compared(self, monkeypatch,
                                                      tmp_path):
        # A tier-4 figure came from a filing and outranks both vendors; a
        # tier-2 one was triangulated, not reported. Comparing either
        # against a vendor measures something other than the question.
        snapshot = tmp_path / "snap.json"
        snapshot.write_text(json.dumps({"stocks": [
            {"symbol": "AAA", "revenue": 1.0,
             "field_provenance": {"revenue": 4}},
            {"symbol": "BBB", "revenue": 2.0,
             "field_provenance": {"revenue": 3}},
            {"symbol": "CCC", "revenue": 3.0,
             "field_provenance": {"revenue": 2}},
        ]}), encoding="utf-8")
        monkeypatch.setattr(
            "services.unified_data_service.screener_snapshot_file",
            lambda: str(snapshot))
        assert census.pick_overlay_symbols(None) == ["BBB"]

    def test_the_pairs_match_the_overlay_in_the_service(self):
        # The census must not keep its own idea of which VNDIRECT keys the
        # overlay reads. A key renamed in the service and not here would
        # make this section report a field as never compared, which reads
        # as agreement.
        import inspect
        from services import unified_data_service as uds

        source = inspect.getsource(uds)
        for vnd_key in census.OVERLAY_PAIRS.values():
            assert f'vnd.get("{vnd_key}")' in source, vnd_key
