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
    def test_an_identical_figure_is_a_copy_not_a_corroboration(self):
        """The same float twice is the overlay having copied it.

        Where TradingView has no column, the overlay writes VNDIRECT's
        number into the record, so the census then compares the vendor
        with itself. da scored 464 of 464 "agree" on the first run - which
        read as perfect corroboration and meant TradingView has no D&A
        column at all. A copy counted as agreement inflates confidence in
        exactly the fields nothing can check.
        """
        assert census._agreement(100.0, 100.0) == "identical"

    def test_two_sources_that_merely_concur_are_kept_separate(self):
        assert census._agreement(1000.0, 1001.0) == "agree"

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

    def test_two_zeros_do_not_divide_by_zero(self):
        assert census._agreement(0.0, 0.0) == "identical"

    def test_a_sign_convention_is_not_a_disagreement(self):
        # Fixed by negating, not by picking a vendor.
        assert census._agreement(100.0, -100.0) == "sign"

    def test_a_short_history_extrapolated_is_this_pipelines_doing(self):
        # _sum_ttm scales by 4/n. A vendor figure that is the record's
        # times 4/n is not a contradiction; it is a different window, and
        # counting it as one would send a run hunting a vendor bug.
        assert census._agreement(100.0, 400.0, quarters=1) == "annualised"
        assert census._agreement(100.0, 200.0, quarters=2) == "annualised"

    def test_the_quarter_count_has_to_come_from_the_payload(self):
        # 4/2 is 2.0. A company that genuinely earned twice as much would
        # be explained away as an artefact if any doubling counted.
        assert census._agreement(100.0, 200.0, quarters=4) == "differ"
        assert census._agreement(100.0, 200.0) == "differ"

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

    def test_the_vendor_keys_match_the_overlay_in_the_service(self):
        # The census must not keep its own idea of which VNDIRECT keys the
        # overlay reads. A key renamed in the service and not here would
        # make this section report a field as never compared, which reads
        # as agreement.
        import inspect
        from services import unified_data_service as uds

        source = inspect.getsource(uds)
        for _prov, vnd_key in census.OVERLAY_PAIRS.values():
            assert f'vnd.get("{vnd_key}")' in source, vnd_key

    def test_the_value_key_and_the_tier_key_are_taken_from_the_service(self):
        """The two names differ, and assuming they matched cost a run.

        The service publishes equity under "equity" and tiers it as
        "total_equity"; likewise debt. This section read
        rec["total_equity"], found nothing for all 1,522 symbols, and
        printed "0 compared" - which reads as agreement rather than as a
        broken instrument. The debt question the run was dispatched to
        answer went unanswered, and the borrowings scoring reported "this
        cannot be decided from the snapshot" when what could not be
        decided was a lookup.

        _absolute_lines is a local inside a function and cannot be
        imported, so the pairing is read out of the source.
        """
        import inspect
        import re
        from services import unified_data_service as uds

        source = inspect.getsource(uds)
        table = source[source.index("_absolute_lines = {"):]
        table = table[:table.index("\n    }")]
        published = dict(re.findall(
            r'"([a-z_]+)":\s*\([a-z_0-9\.]+,\s*"([a-z_]+)"\)', table))
        assert published, "the published-line table could not be read"
        for value_key, (prov_key, _vnd) in census.OVERLAY_PAIRS.items():
            assert value_key in published, value_key
            assert published[value_key] == prov_key, (
                f"{value_key} is tiered as {published[value_key]!r},"
                f" not {prov_key!r}")

    def test_a_field_nothing_was_compared_for_is_called_out(self,
                                                           monkeypatch):
        # A row of noughts reads as agreement and means the opposite. This
        # is exactly how the equity and debt lookup bug presented: three
        # quiet rows of zeros, and a run that had answered nothing looked
        # like a run that had found no disagreement.
        import io
        import contextlib

        monkeypatch.setattr(census, "_held_overlay_fields", dict)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            census.vendor_disagreement([], 1, {})
        assert "NOTHING COMPARED" in buf.getvalue()
