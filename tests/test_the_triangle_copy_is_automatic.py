"""A line the triangles publish must reach the record without being listed.

normalize_stock_data() used to rebuild its record from a hand-written tuple
of key names. Every value the triangles reconstructed and tiered but nobody
had thought to name was computed, given a provenance tier, and thrown away
one layer before the engine could read it.

That is not a hypothetical. The list was missing `da`, so the engine could
never compute EBITDA = EBIT + D&A and fell back on asserting that D&A is 25%
of EBIT for every company in the universe; and it was missing
`tangible_equity`, so `tbvps` resolved as imputed and the p_tbv model
refused. Both numbers existed, correctly tiered, at the moment they were
dropped. `dividend_per_share` was very nearly the third: it was derived
upstream, tiered, and vanished here until the copy was measured end to end.

So the copy is mechanical now, and these tests pin the four properties that
make it safe rather than merely convenient:

  1. a tiered numeric line arrives on its own, with its tier intact;
  2. an untiered value never arrives, because an untiered number at the top
     level reads as an observation - the exact failure the gate exists for;
  3. a key the record spells out itself always wins over the copy;
  4. `mcap` never arrives, because it is denominated in billions while every
     other absolute line here is in raw VND.
"""

import pytest

import services.unified_data_service as U
from services.unified_data_service import normalize_stock_data
from tests.test_absolute_lines_reach_the_engine import reported_payload, PRICE


# The two lines the hand-written list was dropping, and the internal witness
# whose tier each must inherit on arrival.
RESCUED_LINES = {
    "da": "da",
    "tangible_equity": "tangible_equity",
}


def full_payload():
    """Reported statement lines, plus the columns da and tangible_equity need."""
    tv = reported_payload()
    tv["dividend_yield_recent"] = 4.0
    # tangible_equity is published only when the vendor reports at least one
    # of these, which is the evidence that it reports this part of the
    # balance sheet for this company at all.
    tv["goodwill_fq"] = 1e12
    tv["intangibles_net_fq"] = 2e12
    return tv


@pytest.fixture(scope="module")
def record():
    return normalize_stock_data("TEST", tv_data=full_payload())


@pytest.fixture(scope="module")
def triangles():
    return U.reconstruct_financial_triangles(
        "TEST", PRICE, PRICE * 1e8, "STEEL", full_payload(), {}, {}
    )


class TestTheDroppedLinesArrive:
    @pytest.mark.parametrize("line", sorted(RESCUED_LINES))
    def test_the_line_reaches_the_top_level(self, record, line):
        assert record.get(line) is not None, (
            f"{line!r} is reconstructed and tiered upstream, then dropped at "
            f"the copy into the record - the defect this change removes"
        )

    @pytest.mark.parametrize("line", sorted(RESCUED_LINES))
    def test_the_value_is_the_one_that_was_published(self, record, triangles, line):
        assert record[line] == triangles[line]

    @pytest.mark.parametrize("line,witness", sorted(RESCUED_LINES.items()))
    def test_the_tier_survives_the_copy(self, record, line, witness):
        tiers = record["field_provenance"]
        assert tiers.get(line) == tiers.get(witness), (
            f"{line!r} must arrive carrying its tier; a line copied up "
            f"untiered fails closed and the copy has bought nothing"
        )

    def test_nothing_that_used_to_arrive_stopped_arriving(self, record):
        # The keys the hand-written list carried, which must all survive it.
        for line in (
            "total_assets", "total_liabilities", "equity", "debt", "cash",
            "revenue", "net_income", "ebit", "ebitda", "cfo", "capex",
            "shares_out", "dividend_per_share",
        ):
            assert record.get(line) is not None, (
                f"{line!r} was carried by the hand-written list and must "
                f"still be carried by the mechanical copy"
            )


class TestTheCopyStaysFailClosed:
    """An untiered number must not be lifted into the record."""

    def test_an_untiered_line_does_not_arrive(self, monkeypatch):
        real = U.reconstruct_financial_triangles

        def with_an_untiered_extra(*args, **kwargs):
            tri = real(*args, **kwargs)
            # A number with no entry in field_provenance: no evidence behind
            # it, so no claim about it may reach a consumer.
            tri["a_line_nobody_tiered"] = 123.0
            return tri

        monkeypatch.setattr(
            U, "reconstruct_financial_triangles", with_an_untiered_extra)
        record = normalize_stock_data("TEST", tv_data=full_payload())
        assert "a_line_nobody_tiered" not in record, (
            "an untiered value copied to the top level reads as observed, "
            "which is precisely what the provenance gate exists to prevent"
        )

    def test_a_newly_tiered_line_arrives_without_being_listed(self, monkeypatch):
        """The whole point: upstream adds a line, it gets here on its own."""
        real = U.reconstruct_financial_triangles

        def with_a_new_line(*args, **kwargs):
            tri = real(*args, **kwargs)
            tri["a_line_added_upstream"] = 456.0
            tri["field_provenance"]["a_line_added_upstream"] = 3
            return tri

        monkeypatch.setattr(
            U, "reconstruct_financial_triangles", with_a_new_line)
        record = normalize_stock_data("TEST", tv_data=full_payload())
        assert record.get("a_line_added_upstream") == 456.0, (
            "a tiered line published upstream must arrive here without "
            "anyone editing a list of names"
        )
        assert record["field_provenance"]["a_line_added_upstream"] == 3


class TestTheRecordKeepsItsOwnSpellings:
    def test_mcap_never_reaches_the_top_level(self, record, triangles):
        # mcap is tiered and numeric, so it passes every other test the copy
        # applies - and it is in BILLIONS. market_cap (billions, for the UI)
        # and market_cap_vnd (raw, for the engine) already publish this
        # value under names that say which unit they are in.
        assert "mcap" in triangles["field_provenance"], (
            "if mcap ever stops being tiered this test is no longer "
            "measuring what it claims to measure"
        )
        assert "mcap" not in record

    def test_an_explicit_key_overrides_the_copy(self, monkeypatch):
        real = U.reconstruct_financial_triangles

        def with_a_clashing_line(*args, **kwargs):
            tri = real(*args, **kwargs)
            # "symbol" is spelled out by the record itself. The copy must
            # never be able to redefine it.
            tri["change_pct"] = -999.0
            tri["field_provenance"]["change_pct"] = 3
            return tri

        monkeypatch.setattr(
            U, "reconstruct_financial_triangles", with_a_clashing_line)
        record = normalize_stock_data("TEST", tv_data=full_payload())
        assert record["change_pct"] != -999.0, (
            "the record's own spelling of a field must win; the copy is a "
            "floor under it, not a replacement for it"
        )
