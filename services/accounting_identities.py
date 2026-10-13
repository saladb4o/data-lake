"""A declarative catalogue of accounting identities, solved to a fixpoint.

Why this exists
---------------
reconstruct_financial_triangles() fills each field with a hand-written
ladder of rungs, and those ladders are good: they encode which vendor
column to prefer, which cross-check to trust, and what a figure is worth
when it comes from each. What they do not do is close the system. A ladder
knows the two or three routes somebody thought of while writing that
field; it does not know that the same number is recoverable from a fourth
direction that happens to be available for this particular company.

So this module holds the identities themselves - each one a statement that
is true of every set of books, written once, in one direction per unknown -
and applies them repeatedly to whatever the ladders left missing, until
nothing more can be recovered. It runs last and fills only gaps: a field a
ladder already answered is never overwritten, because the ladder knew
something this table does not.

Why it is not simply "list every formula"
-----------------------------------------
Two things make an unguarded identity table dangerous, and both have
already happened in this repository.

The first is circularity. total_equity = assets - liabilities and
total_liabilities = assets - equity are both true, and applying them in
sequence to a book that is missing two of the three recovers nothing: it
manufactures a pair of numbers that agree with each other and with no
observation. Worse, they agree PERFECTLY, so any downstream cross-check
sees a balance sheet that balances. The guard is lineage: an identity may
not consume an input whose derivation ancestry already contains the field
being solved for. A value never helps compute its own ancestor.

The second is depth. The provenance rule everywhere else in this service
is field = min(inputs), which is exactly right for one step and silently
wrong for five: a figure recovered through a chain of five subtractions
inherits the tier of the strongest evidence anywhere behind it, and reads
as though it were measured. The rule here is min(inputs) AND a penalty
once the chain is long, so a deep recovery degrades to a stand-in and the
provenance gate refuses it. That is the point of the exercise. Closing the
system must widen what can be *known*, never what can be *asserted*.

What it is not
--------------
This is not a source of new information. Every value it produces was
already implied by values the vendors stated. Where two unknowns sit in
one identity, no catalogue helps - fcf blocks 149 symbols because both cfo
and capex are absent, and a table of identities cannot invent a cash flow
statement. Coverage that this module adds is coverage that was arithmetic
all along.
"""

from __future__ import annotations

from typing import Callable, Dict, FrozenSet, List, Optional, Sequence, Tuple

__all__ = [
    "Identity",
    "MIN_PUBLISHABLE_TIER",
    "IDENTITIES",
    "MAX_TRUSTED_DEPTH",
    "DERIVED_TIER",
    "solve",
]

#: The tier a one-step recovery earns. Tier 3 is "the vendor stated it" and
#: nothing computed here was stated by anyone; tier 2 is this service's
#: existing convention for a figure triangulated from two reported lines,
#: and it clears InputResolver.MIN_TRUSTED_UPSTREAM_TIER.
DERIVED_TIER = 2

#: How many chained recoveries a figure may pass through before it stops
#: counting as evidence. A value two steps from reported lines is still a
#: reading of those lines; by the third the arithmetic has travelled far
#: enough from anything observed to be worth nothing.
MAX_TRUSTED_DEPTH = 2

#: The tier a recovery must reach to be worth emitting at all. It mirrors
#: InputResolver.MIN_TRUSTED_UPSTREAM_TIER, which is duplicated rather than
#: imported because valuation_engine sits downstream of this module; a test
#: pins the two together so they cannot drift apart in silence.
#:
#: Below it, a recovery is DECLINED rather than published as a stand-in.
#: This service already draws that line for ebit, whose ladder deliberately
#: leaves the field absent rather than emitting revenue times a sector
#: margin, and two tests pin it there. The reasoning generalises: every
#: model refuses a driver under this tier, so a low-tier recovery buys no
#: coverage and costs a field that reads as an answer. The catalogue
#: recovers something trustworthy or it recovers nothing.
MIN_PUBLISHABLE_TIER = 2


class Identity:
    """One accounting truth, solved for one unknown.

    `output` is recovered from `inputs` by `fn`. `guard` may reject a
    combination that is arithmetically valid and financially meaningless -
    a negative equity recovered from a mis-scaled pair, say - and returning
    None from either fn or guard means "this identity declines to answer",
    which leaves the field missing rather than filling it badly.
    """

    __slots__ = ("output", "inputs", "fn", "guard", "note")

    def __init__(
        self,
        output: str,
        inputs: Sequence[str],
        fn: Callable[..., Optional[float]],
        note: str = "",
        guard: Optional[Callable[[float], bool]] = None,
    ) -> None:
        self.output = output
        self.inputs = tuple(inputs)
        self.fn = fn
        self.guard = guard
        self.note = note

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<Identity {self.output} = f{self.inputs}>"


def _positive(value: float) -> bool:
    return value > 0


#: The catalogue. Each entry is an identity that holds for every set of
#: books, stated once per unknown it can solve for. Entries whose result
#: cannot be negative in a going concern carry a guard, so a payload whose
#: units are wrong fails to produce a figure rather than producing a
#: confident absurdity.
#:
#: Deliberately absent, and why:
#:   retained_earnings - not recoverable from the rest of the balance sheet
#:                       without assuming the solvency the score measures.
#:   total_debt        - borrowings are a SUBSET of liabilities, not a
#:                       synonym; recovering one from the other overstates
#:                       enterprise value by every trade payable and tax
#:                       accrual the company owes.
#:   cash              - nothing in the statements implies it.
#:   shares, market_cap - the share-count ladder upstream already runs eight
#:                       rungs including every recovery available here, and
#:                       it caps each by the tier of the price that fed it,
#:                       which this table has no way to see.
#:   tangible_equity   - goodwill and intangibles are read but never tiered,
#:                       so an identity over them would have no provenance
#:                       to inherit and would read as evidence.
IDENTITIES: List[Identity] = [
    # --- Balance sheet ------------------------------------------------
    Identity("total_assets", ("total_liabilities", "total_equity"),
             lambda l, e: l + e, "A = L + E", _positive),
    Identity("total_liabilities", ("total_assets", "total_equity"),
             lambda a, e: a - e, "L = A - E", _positive),
    Identity("total_equity", ("total_assets", "total_liabilities"),
             lambda a, l: a - l, "E = A - L", _positive),

    Identity("working_capital", ("current_assets", "current_liabilities"),
             lambda ca, cl: ca - cl, "WC = CA - CL"),
    Identity("current_assets", ("working_capital", "current_liabilities"),
             lambda wc, cl: wc + cl, "CA = WC + CL", _positive),
    Identity("current_liabilities", ("current_assets", "working_capital"),
             lambda ca, wc: ca - wc, "CL = CA - WC", _positive),

    # --- Income statement ---------------------------------------------
    Identity("ebitda", ("ebit", "da"), lambda e, d: e + d, "EBITDA = EBIT + D&A"),
    Identity("ebit", ("ebitda", "da"), lambda e, d: e - d, "EBIT = EBITDA - D&A"),
    Identity("da", ("ebitda", "ebit"), lambda eb, e: eb - e, "D&A = EBITDA - EBIT",
             _positive),

    Identity("net_income", ("eps", "shares"), lambda e, s: e * s, "NI = EPS x shares"),
    Identity("eps", ("net_income", "shares"),
             lambda n, s: n / s if s else None, "EPS = NI / shares"),

    Identity("revenue", ("prev_revenue", "rev_1y_growth"),
             lambda p, g: p * (1.0 + g / 100.0), "revenue = prior x (1 + g)",
             _positive),
    Identity("prev_revenue", ("revenue", "rev_1y_growth"),
             lambda r, g: r / (1.0 + g / 100.0) if g > -100.0 else None,
             "prior = revenue / (1 + g)", _positive),

    # --- Cash flow ------------------------------------------------------
    # No free-cash-flow identity, and the reason is a unit, not an opinion.
    # fcf_ttm is denominated in BILLIONS - it is a display field, rounded to
    # one decimal, like mcap - while cfo and capex on the same record are in
    # raw dong. FCF = CFO - capex written over those three names is off by
    # nine orders of magnitude, and it produces a confident number rather
    # than an error, which is the worst way for an identity to be wrong.
    #
    # This was written, wired, and caught by measuring the output rather
    # than by reading it. Restoring the identity means giving the service a
    # raw-dong free cash flow of its own to state it over; until then the
    # ladder that already computes fcf_ttm, and divides, stands alone.
]


def solve(
    values: Dict[str, Optional[float]],
    tiers: Dict[str, int],
    identities: Sequence[Identity] = IDENTITIES,
    max_passes: int = 8,
) -> Dict[str, Tuple[float, int, int, str]]:
    """Fill what is missing from what is present, and say how far it came.

    `values` maps field name to figure or None; `tiers` maps field name to
    provenance tier for the figures that have one. Neither is mutated.

    Returns only the fields this call recovered, each as
    ``(value, tier, depth, note)``. A field already present in `values` is
    never touched: the ladder that produced it knew things this table does
    not.

    The two guards that make a catalogue safe rather than merely complete:

      lineage  a field may not be recovered from an input whose own
               derivation ancestry contains it, so no value ever helps
               compute its own ancestor and a pair of identities cannot
               manufacture a balance sheet that balances by construction.

      depth    a recovery more than MAX_TRUSTED_DEPTH steps from reported
               evidence is declined outright, not emitted as a stand-in,
               and neither is one whose inputs drag it below
               MIN_PUBLISHABLE_TIER. Closing the system widens what can be
               known, never what can be asserted.
    """
    known: Dict[str, float] = {
        name: float(value) for name, value in values.items() if value is not None
    }
    known_tiers: Dict[str, int] = dict(tiers)
    # Ancestry of every field, for the lineage guard. A reported field has
    # an empty ancestry; a recovered one carries its inputs and everything
    # behind them.
    ancestry: Dict[str, FrozenSet[str]] = {name: frozenset() for name in known}
    depth: Dict[str, int] = {name: 0 for name in known}

    recovered: Dict[str, Tuple[float, int, int, str]] = {}

    for _ in range(max_passes):
        progressed = False
        for identity in identities:
            target = identity.output
            if target in known:
                continue
            if any(name not in known for name in identity.inputs):
                continue
            # Lineage: refuse an input that this field helped produce.
            if any(target in ancestry.get(name, frozenset())
                   for name in identity.inputs):
                continue
            try:
                result = identity.fn(*(known[name] for name in identity.inputs))
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            if result is None:
                continue
            result = float(result)
            if result != result or result in (float("inf"), float("-inf")):
                continue
            if identity.guard is not None and not identity.guard(result):
                continue

            step = 1 + max(depth.get(name, 0) for name in identity.inputs)
            if step > MAX_TRUSTED_DEPTH:
                continue
            tier = min(DERIVED_TIER,
                       *(known_tiers.get(name, 0) for name in identity.inputs))
            if tier < MIN_PUBLISHABLE_TIER:
                # Declined, and not recorded as known either: a figure this
                # module will not stand behind must not become the evidence
                # a later identity stands on.
                continue

            known[target] = result
            known_tiers[target] = tier
            depth[target] = step
            ancestry[target] = frozenset(identity.inputs).union(
                *(ancestry.get(name, frozenset()) for name in identity.inputs)
            )
            recovered[target] = (result, tier, step, identity.note)
            progressed = True
        if not progressed:
            break

    return recovered
