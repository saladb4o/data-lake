"""The lake's universe must be the screener's universe - no more, no less.

Two ways it was neither. Too few: data/*.json is gitignored, so a CI
runner has no all_symbols.json and services.stock_service falls back to a
hardcoded VN30; a --universe build covered thirty symbols, exited zero,
and produced an artifact byte-identical to one capped at forty. Too many:
reading ALL_SYMBOLS_MAP directly filtered nothing, so covered warrants,
ETFs and funds came too - some five thousand codes, most of which file no
quarterly statements at all.

Both are answered by taking the population from load_local_symbols(),
which is where the screener takes it from.
"""
import sys
import os
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.build_historical_fundamentals as lake  # noqa: E402
import scripts.sync_unified_market_data as sync  # noqa: E402
from scripts.sync_unified_market_data import (  # noqa: E402
    MIN_PLAUSIBLE_UNIVERSE)


def _map_of(count):
    return {f"S{i:04d}": {"symbol": f"S{i:04d}"} for i in range(count)}


class TestATooSmallUniverseIsRefused:
    def test_a_vn30_sized_map_yields_nothing_when_the_listing_will_not_load(self):
        """Thirty symbols is the fallback, not the universe."""
        with mock.patch.object(lake, "logger"), \
                mock.patch.object(sync, "load_local_symbols",
                                  return_value=_map_of(30)), \
                mock.patch("services.stock_service.sync_universe_from_vnstock",
                           side_effect=RuntimeError("listing endpoint down")):
            assert lake._universe_symbols(None) == []

    def test_refusing_makes_the_run_fail_rather_than_publish(self):
        """main() must exit non-zero, not write a thirty-symbol lake."""
        argv = ["build_historical_fundamentals.py", "--universe"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(lake, "_universe_symbols", return_value=[]), \
                mock.patch.object(lake, "build_symbol") as built:
            assert lake.main() == 1
        assert not built.called, "nothing may be fetched once the universe is refused"

    def test_a_plausible_universe_is_accepted_untouched(self):
        big = _map_of(MIN_PLAUSIBLE_UNIVERSE + 500)
        with mock.patch.object(lake, "logger"), \
                mock.patch.object(sync, "load_local_symbols",
                                  return_value=big), \
                mock.patch("services.stock_service.sync_universe_from_vnstock") as fetched:
            got = lake._universe_symbols(None)
        assert len(got) == len(big)
        assert not fetched.called, "a full map must not trigger a listing fetch"

    def test_the_limit_still_applies_to_a_real_universe(self):
        big = _map_of(MIN_PLAUSIBLE_UNIVERSE + 500)
        with mock.patch.object(lake, "logger"), \
                mock.patch.object(sync, "load_local_symbols",
                                  return_value=big):
            assert len(lake._universe_symbols(40)) == 40


class TestTheListingIsFetchedBeforeGivingUp:
    def test_a_thin_map_triggers_the_listing_sync_then_reloads(self):
        """The refusal is a last resort, not the first response."""
        full = _map_of(MIN_PLAUSIBLE_UNIVERSE + 400)
        answers = [_map_of(0), full]

        with mock.patch.object(lake, "logger"), \
                mock.patch.object(sync, "load_local_symbols",
                                  side_effect=answers), \
                mock.patch("services.stock_service.sync_universe_from_vnstock",
                           return_value={"total_symbols": len(full)}) as fetched:
            got = lake._universe_symbols(None)

        assert fetched.called, "an empty listing must be fetched before giving up"
        assert len(got) == len(full)


class TestTheThresholdHasOneHome:
    def test_the_lake_uses_the_same_threshold_as_the_screener_sync(self):
        """Restating 100 here would be one more copy that cannot hear a change."""
        source = open(lake.__file__, encoding="utf-8").read()
        assert "MIN_PLAUSIBLE_UNIVERSE" in source
        assert "from scripts.sync_unified_market_data import" in source


class TestOnlyListedEquitiesAreAsked:
    """Covered warrants and funds file no quarterly statements."""

    def test_the_population_comes_from_the_screeners_own_filter(self):
        """Not ALL_SYMBOLS_MAP, which carries every instrument listed."""
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(lake._universe_symbols))
        func = tree.body[0]
        # The docstring explains what this must not do and names the map,
        # so it is dropped before reading the code - otherwise the guard
        # is tripped by its own explanation.
        body = func.body[1:] if ast.get_docstring(func) else func.body
        code = "\n".join(ast.unparse(node) for node in body)
        assert "load_local_symbols" in code
        assert "ALL_SYMBOLS_MAP" not in code, (
            "reading the raw map back would bring warrants and ETFs with it")

    def test_the_screeners_filter_keeps_equities_and_drops_the_rest(self):
        """The filter this now depends on: STOCK on a real exchange."""
        import inspect
        source = inspect.getsource(sync.load_local_symbols)
        assert '"STOCK", "CO_PHIEU"' in source
        assert '"HOSE", "HNX", "UPCOM"' in source

    def test_a_warrant_heavy_listing_yields_only_the_equities(self):
        """End to end through the real filter, with a listing on disk."""
        import json
        import tempfile
        listing = (
            [{"symbol": f"S{i:04d}", "type": "STOCK", "exchange": "HOSE",
              "organ_name": f"Cong ty {i}"}
             for i in range(MIN_PLAUSIBLE_UNIVERSE + 200)]
            + [{"symbol": f"CFPT{i:03d}", "type": "CW", "exchange": "HOSE"}
               for i in range(400)]
            + [{"symbol": f"FUE{i:03d}", "type": "ETF", "exchange": "HOSE"}
               for i in range(50)]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "all_symbols.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(listing, handle)
            with mock.patch.object(lake, "logger"), \
                    mock.patch.object(sync, "resolve_data_file",
                                      return_value=path):
                got = lake._universe_symbols(None)
        assert len(got) == MIN_PLAUSIBLE_UNIVERSE + 200
        assert not [s for s in got if s.startswith(("CFPT", "FUE"))], (
            "warrants and ETFs must not reach the filings endpoint")
