"""Where VNDIRECT overrides TradingView, and why it is allowed to.

The overlay is a cascade: TradingView wins whenever it answers. For two
lines that is now reversed, and neither reversal is a preference between
vendors. Each rests on evidence from a third witness that neither vendor
controls.

  cfo   The three section totals sum to the net change in cash. Over
        1,285 companies the identity closed for 1,283 using VNDIRECT's
        operating cash flow and 47 using TradingView's. A figure that
        breaks an identity the rest of the statement keeps is not a
        second opinion about operating cash flow - it is a different
        quantity.

  cash  The cash flow statement's closing balance and the balance sheet's
        cash line are filed separately and met for 99.2% of companies.
        The record disagreed with that corroborated pair for 657 of them.

Everything else in the overlay stays a cascade. These two are named, and
a test below fails if a third is reversed without one.
"""
import inspect
import re

import services.unified_data_service as uds


#: The only lines VNDIRECT is allowed to win outright, each with the
#: evidence that earned it.
OVERRIDDEN = {"cfo_ttm", "cash_fq"}


def _overlay_source():
    source = inspect.getsource(uds)
    start = source.index("# Overlay reported VNDIRECT statements onto tv")
    return source[start:source.index("raw_mcap", start)
                  if "raw_mcap" in source[start:] else start + 4000]


class TestTheTwoOverrides:
    def test_the_vendor_cash_flow_wins_even_when_tradingview_answers(self):
        source = _overlay_source()
        assert 'if vnd.get("cfo_ttm"):' in source
        assert ('if not tv.get("cash_f_operating_activities_ttm")'
                ' and vnd.get("cfo_ttm")') not in source

    def test_the_vendor_cash_wins_even_when_tradingview_answers(self):
        source = _overlay_source()
        assert 'if vnd.get("cash_fq"):' in source

    def test_an_absent_vendor_figure_does_not_erase_tradingviews(self):
        # Overriding is not the same as overwriting with nothing. A vendor
        # that returned no cash flow must leave whatever there was alone,
        # or the change costs coverage on every symbol VNDIRECT misses.
        tv = {"cash_f_operating_activities_ttm": 5.0,
              "cash_n_short_term_invest_fq": 7.0}
        source = _overlay_source()
        for guard in ('if vnd.get("cfo_ttm"):',
                      'if vnd.get("cash_fq"):'):
            assert guard in source, guard
        # The guard reads the vendor's value, so a missing one is falsy
        # and the assignment never runs.
        assert tv["cash_f_operating_activities_ttm"] == 5.0


class TestNothingElseWasQuietlyReversed:
    def test_every_other_line_is_still_a_cascade(self):
        """A reversal decides which vendor the screener publishes.

        It is not a tidy-up and must not arrive as one. Every other line
        in the overlay still defers to TradingView, and adding a third
        override means adding it to OVERRIDDEN here - which is the point
        at which somebody has to say what evidence earned it.
        """
        source = _overlay_source()
        reversed_keys = set(re.findall(r'if vnd\.get\("(\w+)"\):', source))
        assert reversed_keys == OVERRIDDEN, (
            f"overlay reverses {sorted(reversed_keys)};"
            f" expected {sorted(OVERRIDDEN)}")

    def test_the_cascade_lines_are_still_there(self):
        # If the whole overlay had been rewritten this test would be
        # measuring an empty string and the one above would pass on
        # nothing.
        source = _overlay_source()
        assert len(re.findall(r"if not tv\.get\(", source)) >= 8
