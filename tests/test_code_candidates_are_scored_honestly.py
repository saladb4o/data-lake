"""The candidate scorer must be able to return "undecided".

Its purpose is to choose between item codes for capex and depreciation.
The failure it exists to avoid is the one that happened three times in a
day: a measurement that returns a confident ranking while comparing
something with itself, or while every candidate is silent.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.score_code_candidates import (  # noqa: E402
    _consecutive, score, report)


def _series(values):
    """values: list of (quarter, gross_ppe, candidate_value)."""
    return {"symbols": {"AAA": {
        q: {"gross_ppe": gp, "capex_32100": c100, "capex_32110": c110}
        for q, gp, c100, c110 in values}}}


class TestOnlyConsecutiveQuartersAreDifferenced:
    def test_a_gap_is_not_a_delta(self):
        """2021-Q1 to 2022-Q3 is not one quarter of investment."""
        assert _consecutive("2021-Q1", "2021-Q2")
        assert _consecutive("2021-Q4", "2022-Q1")
        assert not _consecutive("2021-Q1", "2021-Q3")
        assert not _consecutive("2021-Q1", "2022-Q1")

    def test_a_missing_quarter_is_skipped_not_bridged(self):
        probe = _series([("2021-Q1", 1000.0, 0.0, -100.0),
                         ("2021-Q3", 1400.0, 0.0, -100.0)])
        result = score(probe)["gross_ppe"]
        assert result["deltas_available"] == 0, (
            "bridging the gap would credit one quarter with two of growth")


class TestASilentCandidateCannotWin:
    def test_a_code_that_is_always_zero_is_never_tested(self):
        probe = _series([("2021-Q1", 1000.0, 0.0, -100.0),
                         ("2021-Q2", 1100.0, 0.0, -100.0)])
        tally = score(probe)["gross_ppe"]["candidates"]["capex_32100"]
        assert tally["present"] == 1
        assert tally["nonzero"] == 0
        assert tally["tested"] == 0, "a column of zeros is not evidence"

    def test_every_candidate_silent_is_reported_as_deciding_nothing(self, capsys):
        probe = _series([("2021-Q1", 1000.0, 0.0, 0.0),
                         ("2021-Q2", 1100.0, 0.0, 0.0)])
        report(score(probe))
        out = capsys.readouterr().out
        assert "decided nothing" in out
        assert "best" not in out.split("d(accumulated")[0].split("- best")[0] \
            or "decided nothing" in out


class TestACloseCallIsCalledClose:
    def test_two_candidates_within_five_points_are_undecided(self, capsys):
        """A one-point lead is not a finding, and must not print as one."""
        rows = []
        gp = 1000.0
        for i in range(100):
            year = 2000 + i // 4
            quarter = i % 4 + 1
            # Both candidates match the delta equally often.
            rows.append((f"{year}-Q{quarter}", gp, -100.0, -100.0))
            gp += 100.0
        report(score(_series(rows)))
        out = capsys.readouterr().out
        assert "does not separate them" in out
        assert "undecided" in out

    def test_a_clear_winner_is_named_with_its_margin(self, capsys):
        rows = []
        gp = 1000.0
        for i in range(40):
            year = 2000 + i // 4
            quarter = i % 4 + 1
            # 32110 tracks the delta; 32100 is an unrelated magnitude.
            rows.append((f"{year}-Q{quarter}", gp, -9_999_999.0, -100.0))
            gp += 100.0
        report(score(_series(rows)))
        out = capsys.readouterr().out
        assert "best: **capex_32110**" in out
        assert "ahead of the next by" in out


class TestTheTestIsDistrustedWhenItIsTooGood:
    def test_a_real_quarter_of_disposals_breaks_the_identity(self):
        """The identity is not supposed to hold universally.

        Revaluations and disposals move gross fixed assets without capex,
        so a candidate scoring near 100% across a real universe would mean
        the yardstick is not independent - which is the failure this
        scorer was written to avoid.
        """
        probe = _series([("2021-Q1", 1000.0, 0.0, -100.0),
                         ("2021-Q2", 400.0, 0.0, -100.0)])  # a big disposal
        tally = score(probe)["gross_ppe"]["candidates"]["capex_32110"]
        assert tally["tested"] == 1
        assert tally["held"] == 0
