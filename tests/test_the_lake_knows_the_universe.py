"""The lake must not mistake the VN30 fallback for the listed universe.

data/*.json is gitignored, so a CI runner starts with no all_symbols.json
and services.stock_service falls back to a hardcoded VN30. A --universe
build then covered thirty symbols, exited zero, and produced an artifact
byte-identical to one that had been capped at forty. Nothing in the file
said which it was, and a thin lake read as the population the backtest
had to choose from.
"""
import sys
import os
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.build_historical_fundamentals as lake  # noqa: E402
from scripts.sync_unified_market_data import (  # noqa: E402
    MIN_PLAUSIBLE_UNIVERSE)


def _map_of(count):
    return {f"S{i:04d}": {"symbol": f"S{i:04d}"} for i in range(count)}


class TestATooSmallUniverseIsRefused:
    def test_a_vn30_sized_map_yields_nothing_when_the_listing_will_not_load(self):
        """Thirty symbols is the fallback, not the universe."""
        with mock.patch.object(lake, "logger"), \
                mock.patch("services.stock_service.ALL_SYMBOLS_MAP",
                           _map_of(30)), \
                mock.patch("services.stock_service.sync_universe_from_vnstock",
                           side_effect=RuntimeError("listing endpoint down")), \
                mock.patch("services.stock_service.load_master_universe"):
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
                mock.patch("services.stock_service.ALL_SYMBOLS_MAP", big), \
                mock.patch("services.stock_service.sync_universe_from_vnstock") as fetched:
            got = lake._universe_symbols(None)
        assert len(got) == len(big)
        assert not fetched.called, "a full map must not trigger a listing fetch"

    def test_the_limit_still_applies_to_a_real_universe(self):
        big = _map_of(MIN_PLAUSIBLE_UNIVERSE + 500)
        with mock.patch.object(lake, "logger"), \
                mock.patch("services.stock_service.ALL_SYMBOLS_MAP", big):
            assert len(lake._universe_symbols(40)) == 40


class TestTheListingIsFetchedBeforeGivingUp:
    def test_a_thin_map_triggers_the_listing_sync_then_reloads(self):
        """The refusal is a last resort, not the first response."""
        thin = _map_of(30)
        full = _map_of(MIN_PLAUSIBLE_UNIVERSE + 400)

        def _reload():
            # The listing arriving: the map the service reads now holds a
            # real universe. Filled in place rather than rebound - a bare
            # assignment onto an imported module has no teardown, and the
            # code under test re-reads the attribute either way.
            thin.update(full)

        with mock.patch.object(lake, "logger"), \
                mock.patch("services.stock_service.ALL_SYMBOLS_MAP", thin), \
                mock.patch("services.stock_service.sync_universe_from_vnstock",
                           return_value={"total_symbols": len(full)}) as fetched, \
                mock.patch("services.stock_service.load_master_universe",
                           side_effect=_reload):
            got = lake._universe_symbols(None)

        assert fetched.called, "a thin map must try the listing first"
        assert len(got) == len(full)


class TestTheThresholdHasOneHome:
    def test_the_lake_uses_the_same_threshold_as_the_screener_sync(self):
        """Restating 100 here would be one more copy that cannot hear a change."""
        source = open(lake.__file__, encoding="utf-8").read()
        assert "MIN_PLAUSIBLE_UNIVERSE" in source
        assert "from scripts.sync_unified_market_data import" in source
