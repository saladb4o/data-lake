"""
b8_service_enrichment.py — Builder B8: Enriched market treemap service layer.

WHAT get_market_treemap() RETURNS TODAY (services/stock_service.py ~line 881)
=============================================================================
Per child (stock tile), inside sector["children"]:
    {
        "symbol": str,        # e.g. "VCB"
        "name": str,          # company name
        "price": float,       # current matched price
        "change": float,      # absolute change vs reference price
        "change_pct": float,  # percent change vs reference
        "market_cap": float,  # in billion VND
        "volume": int,        # traded volume (shares)
        "exchange": str,      # HOSE / HNX / UPCOM
    }

Per sector, inside result["sectors"] and result["children"]:
    {
        "key": str,             # ICB sector code, e.g. "VNFIN"
        "code": str,            # same as key
        "name": str,            # display name
        "icon": str,            # emoji icon
        "color": str,           # hex color
        "total_cap": float,     # sum of market caps (billion VND)
        "avg_change_pct": float,# average change_pct across children
        "children": [ ... ],    # top 20 stocks sorted by market_cap desc
    }
Top-level: {"sectors": [...], "children": [...]} — both sorted by total_cap desc.
Result is cached under cache_key "market_treemap" with ttl_seconds=30.

WHAT THIS MODULE ADDS (additive only — zero breaking changes)
=============================================================
Per sector:
    - breadth_up / breadth_down / breadth_flat   -> counts of children by sign of change_pct
    - liquidity                                  -> sum(volume * price) per child,
                                                    falls back to sum(volume) when price missing
    - top_mover                                  -> {"symbol", "change_pct"} of the child with
                                                    the largest abs(change_pct)
Per child:
    - defensive fallback: volume defaults to 0 if missing/None

Frontend consumers (static/js/treemap.js) read symbol/name/price/change_pct/
market_cap/exchange/avg_change_pct/icon/code — none are touched, so the existing
renderer keeps working unchanged while new fields become available for upgrades.
"""

from typing import Any, Dict


def _enrich_child(child: Dict[str, Any]) -> Dict[str, Any]:
    """Defensive per-child enrichment. Additive only."""
    if child.get("volume") is None:
        child["volume"] = 0
    return child


def _enrich_sector(sector: Dict[str, Any]) -> Dict[str, Any]:
    """Compute breadth, liquidity and top_mover for one sector dict (in place)."""
    children = [_enrich_child(c) for c in sector.get("children", []) or []]
    sector["children"] = children

    up = sum(1 for c in children if c.get("change_pct", 0) > 0)
    down = sum(1 for c in children if c.get("change_pct", 0) < 0)
    flat = len(children) - up - down

    sector["breadth_up"] = up
    sector["breadth_down"] = down
    sector["breadth_flat"] = flat

    # Liquidity = notional value traded; fall back to raw volume when no price.
    liquidity = 0.0
    for c in children:
        price = c.get("price")
        if isinstance(price, (int, float)) and price > 0:
            liquidity += c.get("volume", 0) * price
        else:
            liquidity += c.get("volume", 0)
    sector["liquidity"] = round(liquidity)

    top_mover = None
    best_abs = -1.0
    for c in children:
        chg = c.get("change_pct") or 0.0
        if abs(chg) > best_abs:
            best_abs = abs(chg)
            top_mover = {"symbol": c.get("symbol"), "change_pct": chg}
    sector["top_mover"] = top_mover

    return sector


def get_market_treemap_enriched() -> Dict[str, Any]:
    """
    Drop-in enriched replacement for get_market_treemap().

    Reuses the original implementation (lazy import to avoid circular imports),
    then layers on additive per-sector analytics. The original response shape is
    fully preserved; existing fields are never modified or removed.
    """
    from services.stock_service import get_market_treemap

    data = get_market_treemap()

    for sector_list_key in ("sectors", "children"):
        enriched = [_enrich_sector(s) for s in data.get(sector_list_key, []) or []]
        data[sector_list_key] = enriched

    return data


# =============================================================================
# SERVER.PY ROUTER SNIPPET — serve it under the SAME endpoint, zero frontend breakage
# =============================================================================
# All added fields are purely additive; /api/market-treemap consumers that ignore
# unknown keys keep working. Swap ONE import + ONE call site in server.py:
#
# --- BEFORE (server.py ~line 102) ---
#
# @app.get("/api/market-treemap")
# def api_market_treemap():
#     """Returns hierarchical treemap data for all sectors and stocks"""
#     try:
#         data = get_market_treemap()
#         return JSONResponse(content={"status": "success", "data": data})
#     except Exception as e:
#         return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
#
# --- AFTER ---
#
# from gauntlet_out.builders.b8_service_enrichment import get_market_treemap_enriched
#
# @app.get("/api/market-treemap")
# def api_market_treemap():
#     """Returns hierarchical treemap data with breadth, liquidity, and top-mover enrichments"""
#     try:
#         data = get_market_treemap_enriched()  # superset of get_market_treemap()
#         return JSONResponse(content={"status": "success", "data": data})
#     except Exception as e:
#         return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
#
# No static/js/treemap.js changes are required — MarketTreemap.render() reads
# sector.icon/name/code/avg_change_pct and stock.symbol/name/price/change_pct/
# market_cap/exchange, all of which remain identical.

# =============================================================================
# WHY THIS HELPS
# =============================================================================
# 1. Size-by-liquidity tiles: `liquidity` lets a layout variant weight tiles by
#    value traded instead of market cap, surfacing where real money is moving
#    intraday rather than just which companies are biggest.
# 2. Breadth chips in sector headers: breadth_up/down/flat enable a compact
#    "▲ 12 │ ▬ 3 │ ▼ 5" chip next to each sector's avg_change_pct, showing
#    internal rotation even when the average is misleading (e.g. dragged by one
#    heavyweight).
# 3. Top-mover badges: `top_mover` lets headers show "VCB +4.2%" style badges so
#    users instantly see which ticker drives the sector's move without scanning
#    tiles — useful on dense sectors capped at 20 children.
# =============================================================================
