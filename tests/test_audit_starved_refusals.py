"""The half of the refusals a new vendor could actually move.

The audit has always dissected the refusals whose drivers clear the gate
and are turned away anyway - a model-map problem no data fixes. It never
counted the complement: the companies refused because a driver the gate
needs is a stand-in or a fabrication. That group is the entire answer to
"is there anything left to do on the data", and reading a bare "89
refused" as a work queue is what this report exists to stop.

The count alone cannot say. 89 companies each short of one extractable
line and 89 companies the vendor returned nothing at all for are the same
number and opposite situations, so the report names drivers.
"""
import io
import contextlib

from scripts import audit_valuation_coverage as audit


def _report(rows):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        audit.report(rows, show_blocked=0)
    return buf.getvalue()


def _row(symbol, tier, starved=(), models=0, sector="VNIND"):
    return {
        "symbol": symbol,
        "worst_tier": tier,
        "starved_core": list(starved),
        "active_models": models,
        "fair_value": 0.0,
        "blocked_by": [],
        "error": None,
        "sector_code": sector,
        "models_offered": 6,
    }


class TestStarvedCore:
    def test_it_names_the_drivers_below_the_gate(self):
        rec = {"field_provenance": {"revenue": 3, "debt": 1, "cash": 0}}
        assert audit.starved_core(rec) == ["debt", "cash"]

    def test_a_driver_at_the_gate_is_not_starved(self):
        # Tier 2 is triangulated and the resolver accepts it. A report that
        # counted it as missing would send the next run chasing a line the
        # engine is already happy with.
        assert audit.starved_core({"field_provenance": {"cash": 2}}) == []

    def test_a_boolean_is_not_a_tier(self):
        # True == 1 in Python, so a flag stored beside the tiers would be
        # read as a tier-1 stand-in and invent a starved driver.
        assert audit.starved_core({"field_provenance": {"cash": True}}) == []

    def test_a_record_with_no_provenance_starves_nothing(self):
        # Nothing said otherwise is not the same as said to be fabricated.
        assert audit.starved_core({}) == []

    def test_the_gate_matches_the_resolver(self):
        from services.valuation_engine import InputResolver

        assert audit.TRUSTED == InputResolver.MIN_TRUSTED_UPSTREAM_TIER


class TestTheReportSeparatesReachableFromHopeless:
    def test_it_counts_the_starved_group(self):
        out = _report([_row("A", 1, ["revenue"]), _row("B", 3)])
        assert "Refused for want of trustworthy data: 1 of 2" in out

    def test_it_ranks_the_missing_drivers(self):
        rows = [_row("A", 1, ["debt"]), _row("B", 1, ["debt"]),
                _row("C", 0, ["revenue"])]
        out = _report(rows)
        assert "debt" in out and "revenue" in out
        # Ranked, so the line a fix should target is the first one.
        assert out.index("debt") < out.index("revenue")

    def test_a_company_short_of_one_driver_is_called_reachable(self):
        out = _report([_row("A", 1, ["cash"])])
        assert "short of exactly" in out
        assert "cash x1" in out

    def test_a_company_short_of_everything_is_called_unreachable(self):
        out = _report([_row("A", 0, list(audit.CORE_DRIVERS))])
        assert "no vendor on this route returned anything" in out

    def test_the_two_groups_do_not_overlap(self):
        # Every refusal belongs to exactly one of them: the gate accepted
        # its worst driver or it did not. A symbol counted twice would let
        # the report claim more work is available than exists.
        rows = [_row("A", 1, ["debt"]), _row("B", 3), _row("C", 2)]
        out = _report(rows)
        assert "Refused despite tier-2-or-better data: 2 of 3" in out
        assert "Refused for want of trustworthy data: 1 of 3" in out

    def test_a_valued_symbol_is_never_in_either_group(self):
        # Starved drivers do not stop a model that does not ask for them,
        # and counting a valued company as refused would report work that
        # has already been done.
        out = _report([_row("A", 1, ["debt"], models=4)])
        assert "Refused for want of trustworthy data: 0 of 0" in out
