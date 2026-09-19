"""Which TT200 code is the cost and which is the carrying amount.

The table said 221 was "Nguyên giá TSCĐ hữu hình" and 222 the accumulated
depreciation. A label is an assertion; a sum that closes is a
measurement. On SHS's filed balance sheet the sum closes the other way:

    221  11,712,020,172      tangible fixed assets
    227  18,539,970,404      intangible fixed assets
    220  30,251,990,576      fixed assets
    221 + 227 = 30,251,990,576 = 220, to the dong

so 221 is a carrying amount and cannot be a gross cost. 222 reads
54,833,959,695 - nearly five times 221 - which is what a cost looks like
beside a net book value. The cost sits at 222 and the accumulated
depreciation at 223, which the table did not carry at all.

These figures are one filing. They are enough to rule out the old
numbering, which is what they are used for here; they are not a claim
that every other code in the table has been checked.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.bctc_pdf_parser as P     # noqa: E402

# as extracted from SHS_SHS_2026_31507 in data/pdf_lake
SHS = {"220": 30251990576.0, "221": 11712020172.0,
       "222": 54833959695.0, "227": 18539970404.0}


class TestTheSumDecidesWhichCodeIsWhich:
    def test_the_parents_add_up_to_the_total(self):
        assert SHS["221"] + SHS["227"] == pytest.approx(SHS["220"], abs=1.0)

    def test_the_old_reading_does_not_add_up(self):
        """If 221 were the cost and 222 the depreciation, this would tie."""
        assert SHS["221"] + SHS["222"] != pytest.approx(SHS["220"], abs=1.0)

    def test_the_cost_is_bigger_than_the_carrying_amount(self):
        assert SHS["222"] > SHS["221"]


class TestTheTableSaysSo:
    def test_221_is_the_carrying_amount(self):
        assert P.TT200_BALANCE_SHEET_CODES[221] == "Tài sản cố định hữu hình"

    def test_the_cost_and_the_depreciation_have_their_own_codes(self):
        assert "Nguyên giá" in P.TT200_BALANCE_SHEET_CODES[222]
        assert "hao mòn" in P.TT200_BALANCE_SHEET_CODES[223]

    def test_finance_lease_assets_are_carried(self):
        """VAS capitalises finance leases; the table had no code for them."""
        for code in (224, 225, 226):
            assert code in P.TT200_BALANCE_SHEET_CODES

    @pytest.mark.parametrize("parent,cost,depreciation",
                             [(221, 222, 223), (224, 225, 226), (227, 228, 229)])
    def test_each_block_is_parent_cost_depreciation(
            self, parent, cost, depreciation):
        assert "Nguyên giá" in P.TT200_BALANCE_SHEET_CODES[cost]
        assert "hao mòn" in P.TT200_BALANCE_SHEET_CODES[depreciation]
        assert "Nguyên giá" not in P.TT200_BALANCE_SHEET_CODES[parent]
        assert "hao mòn" not in P.TT200_BALANCE_SHEET_CODES[parent]


class TestTheEquityBlockIsAlsoOffByOne:
    """The same shift, caught by a different identity.

    The table read 410 as "Vốn góp của chủ sở hữu" - a sub-line. The
    composition 400 = 410 + 430 is read whole off a filed consolidated
    balance sheet, and it cannot hold with 410 as a sub-line, because
    retained earnings would then sit outside the total. So 410 is the
    parent and 411 is the contributed capital under it.
    """

    def test_410_is_the_parent(self):
        assert P.TT200_BALANCE_SHEET_CODES[410] == "Vốn chủ sở hữu"

    def test_411_is_the_contributed_capital(self):
        assert P.TT200_BALANCE_SHEET_CODES[411] == "Vốn góp của chủ sở hữu"

    def test_a_consolidated_filing_has_somewhere_to_put_minority_interest(
            self):
        assert 429 in P.TT200_BALANCE_SHEET_CODES
        assert 430 in P.TT200_BALANCE_SHEET_CODES

    def test_the_composition_the_correction_rests_on_is_expressible(self):
        """400 = 410 + 430 needs all three codes to exist."""
        for code in (400, 410, 430):
            assert code in P.TT200_BALANCE_SHEET_CODES


class TestAnAmbiguousTitleClaimsNothing:
    """Three blocks print the same two words.

    The title list is scanned first-match-wins and a matched code is
    recorded once, so a bare "nguyen gia" pattern files the first block it
    meets under one code and drops the other two as duplicates. One wrong
    number and two missing ones is worse than three missing ones.
    """

    @pytest.mark.parametrize("pattern", ["nguyen gia", "gia tri hao mon luy ke"])
    def test_the_bare_pattern_is_gone(self, pattern):
        assert pattern not in [p for p, _ in P.TITLE_TO_BS_CODES]

    def test_the_patterns_that_remain_name_one_line_each(self):
        seen = {}
        for pattern, code in P.TITLE_TO_BS_CODES:
            assert pattern not in seen, f"{pattern} claims two codes"
            seen[pattern] = code
