"""Identify VNDIRECT's item codes by what their values do.

The vendor names none of its own codes ("vendor named 0 of these codes")
and the catalogue that was to name them holds nothing, so the operating
line cannot be looked up. An income statement is a set of exact arithmetic
relations, and two codes are already known good - revenue at 21001 and net
income at 23000, which the extractor reads and gets sensible numbers from
for hundreds of companies. The rest is recoverable by measurement.

Two earlier attempts are pinned here as the reason this one is shaped the
way it is:

  - Four identities under one proposed reading of the numbering. All four
    returned 0.0%. Wrong in the log rather than in a valuation.
  - Greedy term-by-term search: a term that genuinely belongs can increase
    the residual, so greedy stops early. On a statement with a known
    five-term operating line it gets three terms and reports 7.3% for a
    relation that is exact.
"""

import math
import random

import pytest

from services.unified_data_service import recover_item_code_relations


REV, COGS, GP = 21001, 22100, 23100
FIN_IN, FIN_EX, SELL, ADMIN, OPER = 22051, 22052, 23110, 22110, 22200
NOISE = 99999


def statement_rows(n=520, seed=3, noise=True):
    """A VAS income statement with the relations that actually hold.

    revenue      = cogs + gross profit
    gross profit = operating + selling + admin + fin expense - fin income
    """
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        rev = rng.uniform(1e11, 1e13)
        cogs = rev * rng.uniform(0.70, 0.92)
        gp = rev - cogs
        fi = rev * rng.uniform(0.0, 0.02)
        fe = rev * rng.uniform(0.0, 0.03)
        sell = rev * rng.uniform(0.01, 0.06)
        adm = rev * rng.uniform(0.01, 0.05)
        row = {
            REV: rev, COGS: cogs, GP: gp, FIN_IN: fi, FIN_EX: fe,
            SELL: sell, ADMIN: adm, OPER: gp + fi - fe - sell - adm,
        }
        if noise:
            row[NOISE] = rev * rng.random()
        rows.append(row)
    return rows


def _found(rows, target, **kw):
    codes = sorted({c for r in rows for c in r})
    for tgt, terms, rate, n in recover_item_code_relations(rows, codes, **kw):
        if tgt == target:
            return terms, rate, n
    return None


class TestItRecoversASubtotalNoPairCouldReach:
    """The pair search returned "no pair reproduces it" for 22200 at 3.6%.

    That was not a missing code. An operating line has five terms.
    """

    def test_the_operating_line_is_recovered(self):
        terms, rate, n = _found(statement_rows(), OPER)
        assert rate == pytest.approx(100.0, abs=0.5)
        assert n >= 200

    def test_it_finds_exactly_the_five_lines_that_make_it(self):
        terms, _, _ = _found(statement_rows(), OPER)
        assert {c for c, _ in terms} == {GP, SELL, ADMIN, FIN_EX, FIN_IN}

    def test_the_signs_are_right(self):
        terms, _, _ = _found(statement_rows(), OPER)
        sign = {c: b for c, b in terms}
        assert sign[GP] > 0 and sign[FIN_IN] > 0
        assert sign[SELL] < 0 and sign[ADMIN] < 0 and sign[FIN_EX] < 0

    def test_the_coefficients_are_whole_numbers(self):
        """A line of a statement is added or subtracted once. A coefficient
        of 0.83 would mean the relation is a proportion, not a line."""
        terms, _, _ = _found(statement_rows(), OPER)
        for _c, b in terms:
            assert abs(abs(b) - 1.0) < 0.02

    def test_a_true_term_can_increase_the_residual(self):
        """The reason greedy term-by-term does not work here, pinned.

        After gross profit, selling and admin are taken out, what is left
        is financial income minus financial expense. Removing the expense -
        a term that genuinely belongs - leaves financial income, which is
        the larger of the two, so the median residual goes UP. A search
        that subtracts one term at a time stops there, three terms into a
        five-term relation. Orthogonal matching pursuit re-solves the whole
        set each step, so no single term has to justify itself alone.
        """
        rows = statement_rows()

        def med(vals):
            vals = sorted(vals)
            return vals[len(vals) // 2]

        after_three = [r[OPER] - r[GP] + r[SELL] + r[ADMIN] for r in rows]
        after_four = [a + r[FIN_EX] for a, r in zip(after_three, rows)]
        assert med(map(abs, after_four)) > med(map(abs, after_three)), (
            "if a true term no longer increases the residual, greedy would "
            "work and the choice of algorithm should be revisited"
        )

    def test_the_algorithm_used_finds_it_anyway(self):
        terms, rate, _n = _found(statement_rows(), OPER)
        assert rate == pytest.approx(100.0, abs=0.5)
        assert len(terms) == 5


class TestItRefusesWhatIsNotALine:
    def test_a_random_column_gets_a_low_hit_rate(self):
        _terms, rate, _n = _found(statement_rows(), NOISE)
        assert rate < 50.0

    def test_a_random_column_gets_fractional_coefficients(self):
        """The log has to say "this is not a line of the statement", and a
        coefficient that is not a whole number is how it says it."""
        terms, _rate, _n = _found(statement_rows(), NOISE)
        assert any(abs(abs(b) - 1.0) >= 0.02 for _c, b in terms)


class TestItOnlyReportsWhatItMeasured:
    def test_a_code_carried_by_too_few_companies_is_not_reported(self):
        rows = statement_rows(n=520)
        for row in rows[50:]:
            row.pop(OPER, None)
        codes = sorted({c for r in rows for c in r})
        found = {t for t, *_ in recover_item_code_relations(rows, codes)}
        assert OPER not in found

    def test_an_empty_payload_yields_nothing(self):
        assert recover_item_code_relations([], []) == []

    def test_too_few_codes_yields_nothing(self):
        rows = [{REV: 1.0, COGS: 0.5} for _ in range(500)]
        assert recover_item_code_relations(rows, [REV, COGS]) == []

    def test_every_reported_relation_carries_its_sample_size(self):
        rows = statement_rows()
        codes = sorted({c for r in rows for c in r})
        for _t, _terms, rate, n in recover_item_code_relations(rows, codes):
            assert n >= 200
            assert 0.0 <= rate <= 100.0

    def test_a_missing_value_never_becomes_a_zero(self):
        """A None read as 0.0 would make absent lines look like reported
        zeroes and manufacture relations that are not there."""
        rows = statement_rows()
        for row in rows:
            row[FIN_IN] = None
        terms, _rate, _n = _found(rows, OPER)
        assert FIN_IN not in {c for c, _ in terms}


class TestItIsAMeasurementOnly:
    def test_it_returns_rather_than_publishes(self):
        """The relations are printed by the caller. This function may not
        write into a record, a provenance map or a statement line - naming
        a code is a measurement, and acting on the name is a separate
        change made once the log says the relation holds."""
        import inspect
        from services import unified_data_service as uds
        src = inspect.getsource(uds.recover_item_code_relations)
        for forbidden in ("unified_stocks[", "field_provenance", "print(",
                          "ebit_ttm", "_absolute_lines"):
            assert forbidden not in src


def test_a_negligible_column_is_not_fitted_as_a_relation():
    """The defect the first real census run exposed.

    23001 is a fraction of a millionth of the statement's scale for every
    company that carries it, and least squares gave it coefficients in the
    hundreds of thousands across five separate targets - a free parameter
    absorbing whatever the true terms left behind. This builds the same
    situation: an exact two-term relation, plus a column that is real, is
    present for every company, and is far too small to be a statement line.
    The search must return the two true terms and never the small one.
    """
    import random

    rng = random.Random(7)
    rows = []
    for _ in range(400):
        rev = rng.uniform(1e11, 9e12)
        cogs = rev * rng.uniform(0.6, 0.9)
        rows.append({
            21001: rev,
            22100: cogs,
            23100: rev - cogs,
            # Present for everyone, and a millionth of the scale.
            23001: rev * 1e-7 * rng.uniform(0.5, 1.5),
            22200: rev * rng.uniform(0.02, 0.1),
        })

    found = {
        t: (sorted(c for c, _b in terms), rate)
        for t, terms, rate, _n in recover_item_code_relations(
            rows, [21001, 22100, 23100, 23001, 22200], min_companies=100,
        )
    }

    codes, rate = found[23100]
    assert codes == [21001, 22100]
    assert rate == 100.0
    for target, (codes, _rate) in found.items():
        assert 23001 not in codes, f"{target} was fitted against 23001"


def test_a_median_zero_column_is_kept():
    """Median-zero is ordinary; scale-zero is not.

    Most companies report nothing for other profit, so a real statement
    line can sit at a median of exactly zero and still be a true term for
    the minority that report it. The guard above must discriminate on how
    large a column ever gets, not on where its centre is - otherwise it
    would throw away the very codes the pair search already proved exact.
    """
    import random

    rng = random.Random(11)
    rows = []
    for i in range(400):
        base = rng.uniform(1e11, 9e12)
        other = base * 0.3 if i % 4 == 0 else 0.0
        rows.append({
            22900: base,
            23900: other,
            21900: base + other,
            22100: base * rng.uniform(0.5, 0.9),
            23100: base * rng.uniform(0.1, 0.3),
        })

    found = {
        t: (sorted(c for c, _b in terms), rate)
        for t, terms, rate, _n in recover_item_code_relations(
            rows, [21900, 22900, 23900, 22100, 23100], min_companies=100,
        )
    }
    codes, rate = found[21900]
    assert codes == [22900, 23900]
    assert rate == 100.0
