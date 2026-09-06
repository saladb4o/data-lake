"""Market data must never be invented from the ticker's spelling.

ALL_SYMBOLS_MAP filled a missing reference price with
``15.0 + crc32(symbol) % 85`` and a missing market cap with
``1500 + crc32(symbol) % 145000``. The values were stable across runs, so they
read as real observations rather than as a function of how the ticker happens
to be spelled - and this map feeds the screener, the peer engine and the
backtest universe, so the fabrication propagated everywhere downstream.
"""
import pytest

import services.stock_service as ss


class TestMasterAccessors:
    @pytest.mark.parametrize("info", [
        {}, {"ref": None}, {"ref": 0}, {"ref": -5}, {"ref": "n/a"}, None,
    ])
    def test_unusable_reference_price_reads_as_absent(self, info):
        assert ss.master_ref_price(info) is None
        assert ss.master_price_vnd(info) is None

    def test_a_real_quote_is_returned_in_both_units(self):
        assert ss.master_ref_price({"ref": 42.5}) == 42.5
        assert ss.master_price_vnd({"ref": 42.5}) == 42_500.0

    @pytest.mark.parametrize("info", [{}, {"market_cap": None}, {"market_cap": 0}])
    def test_unusable_market_cap_reads_as_absent(self, info):
        assert ss.master_market_cap(info) is None

    def test_require_price_refuses_rather_than_defaulting(self):
        with pytest.raises(ValueError, match="No reference price"):
            ss.require_master_price_vnd("XYZ", {})

    def test_require_price_returns_a_real_quote(self):
        assert ss.require_master_price_vnd("HPG", {"ref": 27.0}) == 27_000.0


class TestFiniteGuard:
    @pytest.mark.parametrize("raw", [None, "", "abc", float("nan"), float("inf")])
    def test_unusable_values_read_as_absent(self, raw):
        assert ss._finite_or_none(raw) is None

    @pytest.mark.parametrize("raw,expected", [(0, 0.0), (-3.5, -3.5), ("12.5", 12.5)])
    def test_usable_values_pass_through(self, raw, expected):
        assert ss._finite_or_none(raw) == expected


def _code_of(func) -> str:
    """Source of a function with comments and docstrings stripped.

    The comments explaining the removed fabrication mention it by name, so a
    plain substring search over the source would match its own epitaph.
    """
    import inspect
    import io as _io
    import tokenize

    source = inspect.getsource(func)
    out = []
    readline = _io.StringIO(source).readline
    prev_type = None
    for tok in tokenize.generate_tokens(readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and prev_type in (
            None, tokenize.INDENT, tokenize.NEWLINE, tokenize.NL
        ):
            continue  # docstring
        out.append(tok.string)
        if tok.type not in (tokenize.NL, tokenize.NEWLINE):
            prev_type = tok.type
    return " ".join(out)


class TestNoHashDerivedData:
    def test_the_symbol_map_builder_no_longer_hashes_for_prices(self):
        """crc32(symbol) must not appear anywhere near price or market cap."""
        assert "deterministic_hash" not in _code_of(ss.sync_universe_from_vnstock), (
            "a hash-derived price or market cap has come back"
        )

    def test_peer_engine_does_not_hash_for_fundamentals(self):
        code = _code_of(ss.compute_algorithmic_peers)
        assert "deterministic_hash" not in code
        assert "hash" not in code, "peer fundamentals are being hashed again"


class TestPeerSimilarityUsesOnlyReportedFeatures:
    def test_dimensions_used_is_reported(self, monkeypatch):
        """A comparison made on industry alone must say so."""
        monkeypatch.setattr(ss, "ALL_SYMBOLS_MAP", {
            "AAA": {"symbol": "AAA", "type": "STOCK", "sector_code": "VNIND",
                    "exchange": "HOSE", "name": "A", "industry": "Thép",
                    "ref": 20.0, "market_cap": 5000, "pe": 10.0, "pb": 1.5,
                    "roe": 15.0, "roa": 7.0},
            "BBB": {"symbol": "BBB", "type": "STOCK", "sector_code": "VNIND",
                    "exchange": "HOSE", "name": "B", "industry": "Thép"},
        })
        monkeypatch.setattr(ss.cache, "get", lambda *a, **k: None)
        monkeypatch.setattr(ss.cache, "set", lambda *a, **k: None)

        result = ss.compute_algorithmic_peers("AAA", top_k=5)
        peer = next(p for p in result["peers"] if p["symbol"] == "BBB")
        # BBB reports nothing but its industry, so only that dimension counted.
        assert peer["similarity_dimensions_used"] == 1
        assert peer["pe"] is None and peer["roe"] is None
        assert peer["market_cap"] is None

    def test_a_fully_reported_peer_uses_every_dimension(self, monkeypatch):
        monkeypatch.setattr(ss, "ALL_SYMBOLS_MAP", {
            "AAA": {"symbol": "AAA", "type": "STOCK", "sector_code": "VNIND",
                    "exchange": "HOSE", "name": "A", "industry": "Thép",
                    "ref": 20.0, "market_cap": 5000, "pe": 10.0, "pb": 1.5,
                    "roe": 15.0, "roa": 7.0},
            "CCC": {"symbol": "CCC", "type": "STOCK", "sector_code": "VNIND",
                    "exchange": "HOSE", "name": "C", "industry": "Thép",
                    "ref": 22.0, "market_cap": 5600, "pe": 10.8, "pb": 1.6,
                    "roe": 14.0, "roa": 6.5},
        })
        monkeypatch.setattr(ss.cache, "get", lambda *a, **k: None)
        monkeypatch.setattr(ss.cache, "set", lambda *a, **k: None)

        result = ss.compute_algorithmic_peers("AAA", top_k=5)
        peer = next(p for p in result["peers"] if p["symbol"] == "CCC")
        assert peer["similarity_dimensions_used"] == 4
        assert peer["similarity_score"] > 80.0
