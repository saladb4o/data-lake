"""The identity catalogue must close the system without inventing anything.

The question this module answers is "why not just list every formula, so
whatever is missing gets filled by the others". The answer is that a
complete catalogue is safe only with two guards, and without them it is a
machine for producing confident numbers that rest on nothing.

  lineage  E = A - L and L = A - E are both true. Applied in sequence to a
           book missing two of the three, they recover nothing real - they
           manufacture a pair that agrees with each other and with no
           observation, and agrees PERFECTLY, so a downstream cross-check
           sees a balance sheet that balances. No value may help compute
           its own ancestor.

  depth    The rule everywhere else in this service is min(inputs), which
           is right for one step and silently wrong for five: a figure
           recovered through a long chain inherits the tier of the
           strongest evidence anywhere behind it and reads as measured.

Both are tested here as behaviour, not as implementation. The third pinned
property is that the catalogue never overwrites a field a ladder already
answered: the ladders know which vendor column to prefer, and this table
does not.
"""

import pytest

from services.accounting_identities import (
    DERIVED_TIER,
    IDENTITIES,
    MAX_TRUSTED_DEPTH,
    MIN_PUBLISHABLE_TIER,
    Identity,
    solve,
)
from services.valuation_engine import InputResolver

REPORTED = 3


def reported(**values):
    """Values with a vendor-reported tier for each."""
    return values, {name: REPORTED for name in values}


class TestItRecoversWhatIsImplied:
    def test_equity_from_the_other_two(self):
        got = solve(*reported(total_assets=100.0, total_liabilities=60.0))
        assert got["total_equity"][0] == 40.0

    def test_ebit_from_ebitda_and_da(self):
        got = solve(*reported(ebitda=46.0, da=6.0))
        assert got["ebit"][0] == 40.0

    def test_da_from_the_two_operating_lines(self):
        got = solve(*reported(ebitda=46.0, ebit=40.0))
        assert got["da"][0] == 6.0

    def test_a_recovery_clears_the_provenance_gate(self):
        got = solve(*reported(total_assets=100.0, total_liabilities=60.0))
        assert got["total_equity"][1] >= InputResolver.MIN_TRUSTED_UPSTREAM_TIER

    def test_a_recovery_is_never_tiered_as_reported(self):
        got = solve(*reported(total_assets=100.0, total_liabilities=60.0))
        assert got["total_equity"][1] <= DERIVED_TIER, (
            "nothing computed here was stated by anyone"
        )


class TestItInventsNothing:
    def test_two_unknowns_in_one_identity_recover_neither(self):
        # The whole of the fcf story: a table of identities cannot conjure
        # a cash flow statement out of a balance sheet.
        assert solve(*reported(total_assets=100.0)) == {}

    def test_the_circular_pair_manufactures_no_balance_sheet(self):
        # E = A - L and L = A - E are both in the catalogue. Given only A,
        # applying them in sequence would produce a book that balances by
        # construction and describes nothing.
        got = solve(*reported(total_assets=100.0))
        assert "total_equity" not in got
        assert "total_liabilities" not in got

    def test_no_value_helps_compute_its_own_ancestor(self):
        # Recover equity from A and L, then refuse to recover L back from
        # that equity - it is already downstream of L.
        got = solve(*reported(total_assets=100.0, total_liabilities=60.0))
        assert set(got) == {"total_equity"}

    def test_an_untiered_input_is_not_evidence(self):
        # A value with no tier must not seed a derivation, or the recovery
        # inherits a provenance nobody granted. It is declined outright,
        # not published as a stand-in.
        got = solve({"total_assets": 100.0, "total_liabilities": 60.0},
                    {"total_assets": REPORTED})
        assert "total_equity" not in got

    def test_a_stand_in_input_produces_no_recovery(self):
        # This service already draws this line by hand for ebit, whose
        # ladder leaves the field absent rather than emitting revenue times
        # a sector margin. Every model refuses a driver below the gate, so
        # a low-tier recovery buys no coverage and costs a field that reads
        # as an answer.
        assert solve({"ebitda": 46.0, "da": 6.0},
                     {"ebitda": REPORTED, "da": 1}) == {}

    def test_a_negative_result_is_declined_where_it_is_impossible(self):
        # Liabilities exceeding assets would give a negative equity here;
        # the guard declines rather than publishing an absurdity.
        assert "total_equity" not in solve(
            *reported(total_assets=60.0, total_liabilities=100.0))

    def test_a_division_by_zero_declines_instead_of_raising(self):
        assert "eps" not in solve(*reported(net_income=100.0, shares=0.0))

    def test_a_total_collapse_in_revenue_declines(self):
        assert "prev_revenue" not in solve(
            *reported(revenue=100.0, rev_1y_growth=-100.0))


class TestDepthDegradesTheTier:
    def test_a_one_step_recovery_is_trusted(self):
        got = solve(*reported(ebitda=46.0, da=6.0))
        value, tier, depth, _ = got["ebit"]
        assert depth == 1
        assert tier >= InputResolver.MIN_TRUSTED_UPSTREAM_TIER

    def test_a_chain_past_the_limit_is_declined(self):
        # A -> B -> C -> D, each one step further from anything reported.
        # min(inputs) alone would have kept D trusted: every link is tier 2
        # and the minimum of tier 2 is tier 2, however long the chain.
        chain = [
            Identity("b", ("a",), lambda a: a + 1.0),
            Identity("c", ("b",), lambda b: b + 1.0),
            Identity("d", ("c",), lambda c: c + 1.0),
        ]
        got = solve({"a": 1.0}, {"a": REPORTED}, identities=chain)
        assert got["b"][2] == 1 and got["c"][2] == 2
        assert "d" not in got

    def test_everything_published_clears_the_gate(self):
        chain = [Identity(chr(ord("b") + i), (chr(ord("a") + i),),
                          lambda x: x + 1.0) for i in range(4)]
        got = solve({"a": 1.0}, {"a": REPORTED}, identities=chain)
        for name, (_v, tier, depth, _n) in got.items():
            assert tier >= InputResolver.MIN_TRUSTED_UPSTREAM_TIER, name
            assert depth <= MAX_TRUSTED_DEPTH, name


class TestTheLaddersKeepPrecedence:
    def test_a_field_already_answered_is_not_recomputed(self):
        # The ladder's equity disagrees with the identity's. The ladder wins:
        # it knew which vendor column to prefer.
        got = solve(*reported(total_assets=100.0, total_liabilities=60.0,
                              total_equity=39.0))
        assert "total_equity" not in got

    def test_it_returns_only_what_it_recovered(self):
        got = solve(*reported(total_assets=100.0, total_liabilities=60.0))
        assert set(got) == {"total_equity"}


class TestTheGateIsTheEnginesGate:
    def test_the_duplicated_constant_has_not_drifted(self):
        # MIN_PUBLISHABLE_TIER is duplicated rather than imported, because
        # valuation_engine sits downstream of the identity module. This is
        # what keeps the duplicate honest.
        assert MIN_PUBLISHABLE_TIER == InputResolver.MIN_TRUSTED_UPSTREAM_TIER


class TestTheCatalogueItself:
    def test_no_identity_takes_itself_as_an_input(self):
        for identity in IDENTITIES:
            assert identity.output not in identity.inputs, identity

    def test_every_identity_carries_a_note(self):
        # The note is what a reader sees in the provenance trail; an
        # identity nobody can read is one nobody can check.
        for identity in IDENTITIES:
            assert identity.note, identity

    def test_free_cash_flow_is_deliberately_absent(self):
        # fcf_ttm is denominated in billions while cfo and capex on the same
        # record are in raw dong. An identity over those three names is off
        # by nine orders of magnitude and returns a confident number rather
        # than an error.
        assert not any(i.output == "fcf_ttm" for i in IDENTITIES)
        assert not any("fcf_ttm" in i.inputs for i in IDENTITIES)

    def test_debt_is_deliberately_absent(self):
        # Borrowings are a subset of liabilities, not a synonym. Recovering
        # one from the other overstates enterprise value by every trade
        # payable and tax accrual the company owes.
        assert not any(i.output == "total_debt" for i in IDENTITIES)
