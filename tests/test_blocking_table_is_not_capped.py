"""The blocking table counts every reason, not each symbol's first five.

evaluate() builds two lists now. blocked_by is capped at five, because the
per-symbol rows have to stay readable; blocked_all is complete, and the
aggregate table counts that.

Counting the capped list made the table move in response to fixes made
elsewhere. Wiring cash removed it from 150 symbols' complaints and affo rose
117 -> 124, landbank 113 -> 117, invested_capital 28 -> 30, with roe
appearing at 28 where it had not been listed - not because anything new
blocked them, but because each symbol's sixth reason was promoted into a
top-five that had just lost a member.

That matters past tidiness. This table is what the prioritisation reads: it
is the source of "wire cash next, it blocks 150". A ranking that reshuffles
itself whenever something is fixed cannot be used to decide what to fix.
"""
import io
import contextlib
import re

from scripts import audit_valuation_coverage as audit


def _report(rows):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        audit.report(rows, show_blocked=0)
    return buf.getvalue()


def _counts(out):
    """The blocking table, parsed back into {driver: count}."""
    body = out.split("Most common blocking drivers:")[1]
    body = body.split("\n\n")[0]
    return {m.group(1): int(m.group(2))
            for m in re.finditer(r"^\s+(\w+)\s+(\d+) symbols$", body, re.M)}


def _row(symbol, blocked_all, tier=3):
    return {
        "symbol": symbol, "worst_tier": tier, "active_models": 0,
        "fair_value": 0.0, "error": None, "sector_code": "VNIND",
        "models_offered": 6, "models_declined": 0,
        "blocked_by": blocked_all[:5],
        "blocked_all": blocked_all,
    }


SIX = ["cash", "debt", "ebit", "ebitda", "eps", "affo"]


class TestTheSixthReasonIsCounted:
    def test_a_driver_past_the_cap_still_appears(self):
        counts = _counts(_report([_row("AAA", SIX)]))
        assert counts.get("affo") == 1, (
            "the sixth reason was dropped; the table is counting the capped list")

    def test_every_reason_is_counted_once(self):
        counts = _counts(_report([_row("AAA", SIX), _row("BBB", SIX)]))
        assert counts == {d: 2 for d in SIX}


class TestFixingOneDriverDoesNotInflateAnother:
    """The regression this exists to prevent, stated as a before/after."""

    def test_removing_cash_leaves_every_other_count_unchanged(self):
        before = _counts(_report([_row("AAA", SIX), _row("BBB", SIX)]))
        after = _counts(_report([
            _row("AAA", [d for d in SIX if d != "cash"]),
            _row("BBB", [d for d in SIX if d != "cash"]),
        ]))
        assert "cash" not in after
        assert {d: c for d, c in before.items() if d != "cash"} == after, (
            "a driver's count moved when a different driver was fixed")


class TestThePerSymbolRowsStayCapped:
    """The cap was not wrong, only miscounted. Keep it where it belongs."""

    def test_a_refused_row_lists_at_most_five(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            audit.report([_row("AAA", SIX)], show_blocked=5)
        line = [ln for ln in buf.getvalue().splitlines() if "AAA" in ln][-1]
        assert "affo" not in line
        assert line.count("'") == 10


class TestEvaluateProducesTheUncappedList:
    """The report tests above feed blocked_all in; this one earns it.

    Without this, the aggregate's `row.get("blocked_all") or
    row["blocked_by"]` fallback would quietly keep the old behaviour if
    evaluate() ever stopped emitting the key, and every test above would
    still pass.

    The measured gap is not marginal. A payload carrying a price and a share
    count and nothing else draws eleven complaints, of which the table
    counted five - so the blocking table has been under-reporting more than
    half of every refused symbol's reasons, not merely reshuffling the tail.
    """

    @staticmethod
    def _bare():
        return {"symbol": "BARE", "price": 20_000.0, "shares_out": 3e8,
                "sector_code": "VNIND"}

    def test_the_key_exists_and_is_longer_than_the_capped_one(self):
        row = audit.evaluate(self._bare())
        assert len(row["blocked_by"]) == 5
        assert len(row["blocked_all"]) > 5

    def test_the_capped_list_is_a_prefix_of_the_full_one(self):
        row = audit.evaluate(self._bare())
        assert row["blocked_all"][:5] == row["blocked_by"]

    def test_no_driver_is_counted_twice(self):
        row = audit.evaluate(self._bare())
        assert len(set(row["blocked_all"])) == len(row["blocked_all"])
