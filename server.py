import os
import sys
import services.tls_config
import json
import asyncio
import csv
import io
import itertools
import math
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, List
from dataclasses import asdict

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from services.stock_service import (
    get_trading_board,
    get_indices_analytics,
    get_foreign_flow,
    get_stock_history,
    get_company_overview,
    get_company_news,
    get_company_reports,
    get_company_financial_statements,
    get_company_financial_health,
    get_company_events,
    get_company_leadership,
    get_market_news,
    get_rss_news,
    get_top_movers,
    search_symbols,
    get_symbols_stats,
    sync_universe_from_vnstock,
    get_sector_indices_analytics,
    get_sector_history,
    get_company_peers,
    get_company_ecosystem,
    get_company_forensic_report,
    start_background_news_poller,
    get_quant_screener,
    get_company_earnings_engine,
    compute_quant_percentile_universe,
    get_data_lake_status,
    get_symbol_broker_recommendations,
    get_symbol_global_valuation,
    get_symbol_technical_consensus,
    get_macroeconomic_overview,
    get_market_wide_events_calendar,
    get_market_upgrade_tracker,
    STOCKS_MASTER,
    SECTOR_METADATA
)
from services.global_market_service import get_global_commodities_overview
from services.etf_rebalance_service import get_etf_rebalancing_overview
from services.macro_monetary_service import (
    get_macro_monetary_comprehensive_overview,
    get_macro_board_summary,
    get_macro_indicator_detail,
    get_macro_research_documents
)
from services.article_reader import extract_article
from services.backtest_service import (
    get_strategy_definitions,
    run_screener_backtest,
    compare_all_screener_strategies,
    STRATEGY_DEFINITIONS
)
from services.institutional_backtest_service import (
    run_bar_by_bar_backtest,
    run_parameter_sensitivity,
    run_walk_forward_analysis,
    run_monte_carlo_stress_test
)
from services.valuation_engine import ValuationEngine
from services.three_statement_engine import ThreeStatementEngine, forecast_3way
from services.financial_model_exporter import FinancialModelExporter
from services.fair_value_backtest_service import (
    fv_backtest_service,
    BacktestMode,
    SCREENER_PRESETS
)

# ==============================================================================
# SERVER-SIDE PRICE ALERTS ENGINE (in-memory rules + background poller)
# ==============================================================================

ICT_TZ = timezone(timedelta(hours=7))


class AlertRuleCreate(BaseModel):
    symbol: str
    condition: str  # price_above | price_below | pct_change
    value: float


_alert_rules_store = {}
_alert_id_seq = itertools.count(1)
ALERT_RULES_PATH = os.path.join("data", "alert_rules.json")


def _load_alert_rules() -> None:
    """Loads persisted alert rules from disk on startup (best-effort)."""
    global _alert_id_seq
    try:
        with open(ALERT_RULES_PATH, "r", encoding="utf-8") as f:
            rules = json.load(f)
        if isinstance(rules, list):
            max_id = 0
            for r in rules:
                try:
                    rid = int(r["id"])
                    _alert_rules_store[rid] = {**r, "id": rid}
                    max_id = max(max_id, rid)
                except (KeyError, TypeError, ValueError):
                    continue
            _alert_id_seq = itertools.count(max_id + 1)
        print(f"[ALERTS] Loaded {len(_alert_rules_store)} alert rule(s) from {ALERT_RULES_PATH}")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[ALERTS] Failed to load alert rules: {e}")


def _save_alert_rules() -> None:
    """Persists all alert rules to disk atomically (temp file + os.replace)."""
    try:
        os.makedirs(os.path.dirname(ALERT_RULES_PATH), exist_ok=True)
        tmp_path = ALERT_RULES_PATH + ".tmp"
        rules = sorted(_alert_rules_store.values(), key=lambda r: r["id"])
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, ALERT_RULES_PATH)
    except Exception as e:
        print(f"[ALERTS] Failed to save alert rules: {e}")


def _now_iso() -> str:
    return datetime.now(ICT_TZ).isoformat(timespec="seconds")


def _is_market_hours() -> bool:
    """Vietnam stock market hours (ICT): Mon-Fri, 09:00-11:30 and 13:00-14:45."""
    now = datetime.now(ICT_TZ)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return (540 <= minutes <= 690) or (780 <= minutes <= 885)


def _safe_rule_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


def _evaluate_rule(rule: dict, row: dict) -> bool:
    cond = rule.get("condition")
    value = _safe_rule_float(rule.get("value")) or 0.0
    p = _safe_rule_float(row.get("match_p"))
    if cond == "price_above":
        return p is not None and p >= value
    if cond == "price_below":
        return p is not None and p <= value
    if cond == "pct_change":
        pct = _safe_rule_float(row.get("match_pct"))
        return pct is not None and abs(pct) >= value
    return False


async def _alerts_poll_loop(poll_interval: int = 15):
    """Polls the board/quote service every ~15s during market hours and evaluates alert rules server-side."""
    while True:
        try:
            pending = [r for r in list(_alert_rules_store.values()) if r.get("active") and not r.get("fired")]
            if pending and _is_market_hours():
                symbols = ",".join(sorted({r["symbol"] for r in pending}))
                rows = await asyncio.to_thread(get_trading_board, custom_symbols=symbols)
                by_symbol = {row.get("symbol"): row for row in (rows or [])}
                for rule in pending:
                    row = by_symbol.get(rule["symbol"])
                    if row and _evaluate_rule(rule, row):
                        rule["fired"] = True
                        rule["fired_at"] = _now_iso()
                        rule["triggered_value"] = (
                            row.get("match_pct") if rule["condition"] == "pct_change" else row.get("match_p")
                        )
                        await asyncio.to_thread(_save_alert_rules)
                        print(f"[ALERTS] Rule #{rule['id']} fired for {rule['symbol']} at {rule['fired_at']} "
                              f"(condition={rule['condition']}, value={rule['triggered_value']})")
        except Exception as e:
            print(f"[ALERTS] Poll error: {e}")
        await asyncio.sleep(poll_interval)


def _rrg_disk_path() -> str:
    """Path of the RRG stale-while-revalidate disk cache file."""
    return os.path.join("data", "rrg_disk_cache.json")


def _warm_rrg_cache_async():
    """Pre-compute RRG payloads in a daemon thread so first user click hits warm cache."""
    import threading

    def _warm():
        try:
            import time as _time
            _time.sleep(5)  # let module init + event loop settle
            # Handler runs directly in-process (disk cache persists for restarts).
            api_sectors_rrg(benchmark="VNINDEX", interval="1W", tail=8, method="jdk")
            api_sectors_rrg(benchmark="VNINDEX", interval="1W", tail=8, method="enhanced")
        except Exception:
            pass

    threading.Thread(target=_warm, daemon=True, name="rrg-cache-warmer").start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Modern lifespan context manager for FastAPI.
    Consolidates background services startup (alert rules, poller loops, news poller, RRG cache prewarming)
    and graceful shutdown.
    """
    _load_alert_rules()
    alerts_task = asyncio.create_task(_alerts_poll_loop())
    start_background_news_poller()
    _warm_rrg_cache_async()
    try:
        yield
    finally:
        alerts_task.cancel()


def _error_response(exc: Exception) -> JSONResponse:
    """Maps an unhandled endpoint exception to a response.

    A ValueError from the service layer means the inputs were missing or
    unusable - no fundamentals, no price, an unparseable period - which is a
    data gap the caller can act on, not a server fault. Everything else is a
    genuine 500.
    """
    status = 422 if isinstance(exc, ValueError) else 500
    return JSONResponse(status_code=status, content={"status": "error", "message": str(exc)})


app = FastAPI(
    title="Vietnam Stock Trading Terminal Pro API",
    description="Backend API for Vietnamese Electronic Trading Board and Stock Analytics Terminal",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS.
# Origins are configurable via the CORS_ALLOW_ORIGINS env var (comma-separated).
# Defaults to localhost only: the app is normally served from the same origin as
# its static frontend, so no cross-origin access is required.
# Note: credentialed requests cannot use a wildcard origin, so allow_credentials
# is only enabled when an explicit origin list is in effect.
_cors_origins_env = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
if _cors_origins_env:
    CORS_ALLOW_ORIGINS = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
else:
    CORS_ALLOW_ORIGINS = [
        f"http://{_h}:{_p}"
        for _h in ("127.0.0.1", "localhost")
        for _p in (8000, 8080, 8008, 8888, 5000, 5001, 8050)
    ]

_cors_wildcard = "*" in CORS_ALLOW_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=not _cors_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

@app.get("/api/trading-board")
def api_trading_board(
    group: str = Query("VN30", description="VN30, HOSE, HNX, UPCOM, ETF, CW, BOND, Macro, or ICB Sector Code (VNREAL, VNFIN, VNIT, etc.)"),
    symbols: Optional[str] = Query(None, description="Comma-separated custom symbols"),
    limit: Optional[int] = Query(None, description="Max symbols to return, or omit for all"),
    exchange: Optional[str] = Query("ALL", description="Exchange filter: ALL, HOSE, HNX, UPCOM")
):
    """Returns real-time 3-tier bid/ask electronic price board data or macro board"""
    try:
        if group and group.strip().lower() in ["macro", "vimo", "vi_mo", "vĩ mô", "vĩ mô & tiền tệ"]:
            data = get_macro_board_summary()
            return JSONResponse(content={"status": "success", "data": data, "total": len(data)})
        data = get_trading_board(group=group, custom_symbols=symbols, limit=limit, exchange=exchange)
        return JSONResponse(content={"status": "success", "data": data, "total": len(data)})
    except Exception as e:
        return _error_response(e)

@app.get("/api/indices-analytics")
def api_indices_analytics():
    """Returns 5 index cards, market breadth counters, and liquidity in billion VND"""
    try:
        data = get_indices_analytics()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/market-treemap")
def api_market_treemap():
    """Returns hierarchical treemap data for all sectors and stocks (enriched with breadth/liquidity/top-mover)"""
    try:
        from services.treemap_service import get_market_treemap_enriched
        data = get_market_treemap_enriched()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/foreign-flow")
def api_foreign_flow():
    """Returns net foreign investor capital movements and top buy/sell rankings"""
    try:
        data = get_foreign_flow()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/quote/history")
@app.get("/api/stock/history")
def api_quote_history(
    symbol: str = Query("FPT", description="Stock ticker"),
    interval: str = Query("1D", description="Candle interval: 1m, 5m, 15m, 30m, 1H, 1D, 1W, 1M"),
    timeframe: str = Query("ALL", description="Zoom range or lookback: 1D, 1W, 1M, 3M, 6M, 1Y, ALL")
):
    """Returns candlestick OHLCV, indicators (MA, Bollinger, RSI, MACD), ladder depth, and signal across multi-timeframes"""
    try:
        data = get_stock_history(symbol=symbol, interval=interval, timeframe=timeframe)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/overview")
def api_company_overview(symbol: str = Query("FPT")):
    """Returns company profile and fundamental valuation metrics"""
    try:
        data = get_company_overview(symbol=symbol)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/news")
def api_company_news(symbol: str = Query("FPT"), deep_scan: bool = Query(False)):
    """Returns news articles for a company from shared lake or on-demand deep scan"""
    try:
        data = get_company_news(symbol=symbol, deep_scan=deep_scan)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/reports")
def api_company_reports(
    symbol: str = Query("FPT", description="Stock ticker symbol"),
    report_type: str = Query("all", description="all, bctc, annual, governance, resolution, dividend, insider, other"),
    fetch_pdf: bool = Query(True, description="Concurrently extract direct PDF links"),
    page: int = Query(1, description="Page number for historical reports"),
    page_size: int = Query(30, description="Number of reports per page"),
    year: str = Query("all", description="Specific year filter or all")
):
    """Returns official corporate financial reports (BCTC), annual reports, resolutions, and disclosures with direct PDF download links"""
    try:
        data = get_company_reports(symbol=symbol, report_type=report_type, fetch_pdf=fetch_pdf, page=page, page_size=page_size, year=year)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/financials")
def api_company_financials(
    symbol: str = Query("FPT", description="Stock ticker symbol"),
    statement_type: str = Query("income", description="income (KQKD), balance (CĐKT), cashflow (LCTT), ratios (Chỉ số)"),
    period: str = Query("quarter", description="quarter (Theo Quý) or year (Theo Năm)"),
    periods_count: str = Query("8", description="Number of periods (4, 8, 12, 16, 40, or 'all')")
):
    """Returns structured, interactive financial statement tables (Income, Balance, CashFlow, Ratios) across multiple periods (up to 40 quarters / 10 years)"""
    try:
        data = get_company_financial_statements(symbol=symbol, statement_type=statement_type, period=period, periods_count=periods_count)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/health")
def api_company_financial_health(symbol: str = Query("FPT", description="Stock ticker symbol")):
    """Returns Financial Health Scorecard (0-100, Ratings AAA-D), 4 Pillars, Fair Value Estimates, and Industry Peers"""
    try:
        data = get_company_financial_health(symbol=symbol)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/events")
def api_company_events(symbol: str = Query("FPT")):
    """Returns corporate events, dividends, and shareholder meetings"""
    try:
        data = get_company_events(symbol=symbol)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/leadership")
def api_company_leadership(symbol: str = Query("FPT")):
    """Returns board of directors, executive officers, and major shareholders"""
    try:
        data = get_company_leadership(symbol=symbol)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/ecosystem")
def api_company_ecosystem(
    symbol: str = Query(..., description="Stock ticker symbol (e.g. VHM, GEX, FPT)"),
    depth: int = Query(2, description="Network Depth: 1 (Direct), 2 (Extended Sister/Grandchild), 3 (Full)"),
    min_ownership: float = Query(0.0, description="Minimum ownership percentage threshold: 0, 5, 20, 50")
):
    """Returns bidirectional multi-hop ecosystem & weighted ownership network, member quotes, and graph data"""
    try:
        data = get_company_ecosystem(symbol=symbol, depth=depth, min_ownership=min_ownership)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/commodity-spread")
def api_company_commodity_spread(symbol: str = Query(..., description="Stock ticker symbol (e.g. HPG, DPM, DBC, BSR)")):
    """Returns Commodity Crack Spread, Peter Lynch Cycle Phase, and Margin Forecasts"""
    try:
        from services.stock_service import get_commodity_spread_analysis
        data = get_commodity_spread_analysis(symbol=symbol)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/forensics")
def api_company_forensics(symbol: str = Query(..., description="Stock ticker symbol (e.g. HPG, VNM, FPT)")):
    """Returns comprehensive Forensic Accounting Intelligence, 5-Triangle Matrix, Debt Wall, CapEx Projects & Integrity Score"""
    try:
        data = get_company_forensic_report(symbol=symbol)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/document-dossier")
def api_company_document_dossier(
    symbol: str = Query(..., description="Stock ticker symbol"),
    doc_id: Optional[str] = Query(None, description="Document ID or PDF filename")
):
    """Returns deep-extracted structured intelligence of a specific document for instant inline preview"""
    try:
        from services.bctc_batch_processor import _get_lake_data, _get_corporate_actions_lake
        lake = _get_lake_data()
        corp_lake = _get_corporate_actions_lake()

        target_record = None
        if doc_id:
            if doc_id in lake:
                target_record = lake[doc_id]
            elif doc_id in corp_lake:
                target_record = corp_lake[doc_id]
            else:
                for k, v in lake.items():
                    if doc_id.lower() in k.lower() or doc_id.lower() in v.get("title", "").lower():
                        target_record = v
                        break
                if not target_record:
                    for k, v in corp_lake.items():
                        if doc_id.lower() in k.lower() or doc_id.lower() in v.get("title", "").lower():
                            target_record = v
                            break

        if not target_record:
            for k, v in lake.items():
                if v.get("symbol") == symbol.upper().strip():
                    target_record = v
                    break

        if not target_record:
            return JSONResponse(content={"status": "not_found", "message": f"Chưa có dữ liệu bóc tách sẵn cho tài liệu {doc_id} của mã {symbol}."})

        return JSONResponse(content={"status": "success", "data": target_record})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/recommendations")
def api_company_recommendations(symbol: str = Query("FPT", description="Stock ticker symbol")):
    """Returns broker research recommendations, consensus rating, and analyst target prices"""
    try:
        data = get_symbol_broker_recommendations(symbol=symbol)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/global-valuation")
def api_company_global_valuation(symbol: str = Query("FPT", description="Stock ticker symbol")):
    """Returns Simply Wall St 2-Stage DCF Fair Value, discount/premium %, and Snowflake rating"""
    try:
        data = get_symbol_global_valuation(symbol=symbol)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/technical-consensus")
def api_company_technical_consensus(symbol: str = Query("FPT", description="Stock ticker symbol")):
    """Returns Investing.com and TradingView multi-timeframe technical indicator consensus & pivot points"""
    try:
        data = get_symbol_technical_consensus(symbol=symbol)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/market/macro-indicators")
def api_market_macro_indicators():
    """Returns macroeconomic overview (CPI inflation, GDP growth, exchange rates, SBV + GSO)"""
    try:
        data = get_macro_monetary_comprehensive_overview()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/market/macro-board")
def api_market_macro_board():
    """Returns concise macro & intermarket indicators for the Trading Board tab / ticker ribbon"""
    try:
        data = get_macro_board_summary()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/market/macro-detail")
def api_market_macro_detail(indicator: str = Query("USDVND", description="Macro indicator code (e.g. USDVND, VN10Y, SBV_OMO, CPI_VN, GDP_VN, PMI_VN, FDI_VN, DXY, BRENT)")):
    """Returns full 6-pillar analysis dataset for a specific macro indicator"""
    try:
        data = get_macro_indicator_detail(indicator_code=indicator)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/market/macro-documents")
def api_market_macro_documents(
    category: str = Query("all", description="Filter by category (all, GSO, World Bank, IMF, CTCK, Quỹ)"),
    year: str = Query("all", description="Filter by year (all, 2025, 2024, 2023)"),
    keyword: str = Query("", description="Keyword search in title or summary")
):
    """Returns master registry of downloadable PDF macro reports & research studies"""
    try:
        data = get_macro_research_documents(category=category, year=year, keyword=keyword)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/global/commodities")
def api_global_commodities():
    """Returns real-time global commodities, DXY, US 10Y yield, and VN impact analysis"""
    try:
        data = get_global_commodities_overview()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/etf/rebalancing")
def api_etf_rebalancing():
    """Returns foreign & domestic ETF review schedule, countdowns, and key holdings"""
    try:
        data = get_etf_rebalancing_overview()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/market/events-calendar")
def api_market_events_calendar(
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD or DD/MM/YYYY"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD or DD/MM/YYYY"),
    event_type: str = Query("all", description="all, DIVIDEND, ISSUE, MEETING, RESOLUTION, LISTING"),
    group: str = Query("ALL", description="ALL, VN30"),
    limit: int = Query(50, description="Items per page"),
    offset: int = Query(0, description="Pagination offset")
):
    """Returns interactive market-wide corporate action calendar (GDKHQ Dividends, AGMs, Rights)"""
    try:
        data = get_market_wide_events_calendar(
            start_date=start_date,
            end_date=end_date,
            event_type=event_type,
            group=group,
            limit=limit,
            offset=offset
        )
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/market/upgrade-tracker")
def api_market_upgrade_tracker():
    """Returns FTSE & MSCI Vietnam Market Upgrade Readiness Matrix & Institutional Intelligence"""
    try:
        data = get_market_upgrade_tracker()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/macro/monetary-policy")
def api_macro_monetary_policy():
    """Returns official SBV central rates, OMO/T-Bills net liquidity, interbank curve, and GSO GDP/CPI/IIP/FDI/Trade/PMI"""
    try:
        data = get_macro_monetary_comprehensive_overview()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/market-news")
def api_market_news():
    """Returns market-wide curated news feed"""
    try:
        data = get_market_news()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/rss-news")
def api_rss_news(
    source: str = Query("all", description="all, Vietstock, CafeF, VnEconomy, baodautu, Dân trí, VnExpress, Tin nhanh chứng khoán, CafeBiz..."),
    category: str = Query("all", description="all, ck (Chứng khoán), dn (Doanh nghiệp), tc (Tài chính), kd (Kinh doanh)"),
    topic: str = Query("all", description="all, bctc, dividend, insider, risk, macro, market"),
    sentiment: str = Query("all", description="all, BULLISH, BEARISH, NEUTRAL"),
    keyword: str = Query("", description="Ticker symbol (e.g. FPT, HPG) or keyword to filter articles"),
    limit: int = Query(30, description="Number of news articles per page"),
    offset: int = Query(0, description="Offset index for pagination")
):
    """Returns live paginated financial news across 21+ top Vietnamese sources with topic and sentiment intelligence"""
    try:
        data = get_rss_news(
            source=source,
            category=category,
            topic=topic,
            sentiment=sentiment,
            keyword=keyword,
            limit=limit,
            offset=offset
        )
        return JSONResponse(content={
            "status": "success", 
            "data": data.get("articles", []),
            "total": data.get("total", 0),
            "offset": data.get("offset", 0),
            "limit": data.get("limit", limit),
            "has_more": data.get("has_more", False)
        })
    except Exception as e:
        return _error_response(e)

@app.get("/api/top-movers")
def api_top_movers():
    """Returns gainers, losers, volume leaders, and value leaders"""
    try:
        data = get_top_movers()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/sectors/overview")
def api_sectors_overview():
    """Returns analytics for all 10 HOSE / ICB Sector Indices"""
    try:
        data = get_sector_indices_analytics()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/sectors/history")
def api_sectors_history(
    sector: str = Query("VNREAL", description="HOSE Sector code: VNREAL, VNFIN, VNIT, VNMAT, VNIND, VNCONS, VNCOND, VNENE, VNUTI, VNHEAL"),
    interval: str = Query("1D", description="Candle interval: 1D, 1W, 1M"),
    timeframe: str = Query("ALL", description="1W, 1M, 3M, 6M, 1Y, ALL")
):
    """Returns OHLCV candlestick time series and technical indicators for a specific Sector Index"""
    try:
        data = get_sector_history(sector_code=sector, interval=interval, timeframe=timeframe)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/sectors/rrg")
def api_sectors_rrg(
    benchmark: str = Query("VNINDEX", description="Benchmark symbol: VNINDEX, VN30, HNXINDEX, UPCOM"),
    interval: str = Query("1W", description="Candle interval: 1D, 1W, 1M"),
    tail: int = Query(8, description="Number of trailing RRG trail points per sector"),
    method: str = Query("jdk", description="RRG calculation method: jdk or enhanced")
):
    """Returns Relative Rotation Graph (RRG) points for all HOSE / ICB Sector Indices vs a benchmark"""
    try:
        from datetime import datetime as _dt
        from services.stock_service import SECTOR_ICB_REGISTRY, cache as _cache, executor as _executor
        from services.sector_index_service import build_sector_index
        from services.benchmark_service import get_benchmark_history
        from services.rrg_service import build_rrg_matrix

        m = (method or "jdk").lower()
        if m not in ("jdk", "enhanced"):
            m = "jdk"
        ivl = interval if interval in ("1D", "1W", "1M") else "1W"
        tail_n = max(1, min(int(tail), 60))

        rrg_cache_key = f"sectors_rrg_{benchmark}_{ivl}_{tail_n}_{m}"
        cached = _cache.get(rrg_cache_key)
        if cached:
            return JSONResponse(content={"status": "success", "data": cached})

        # Stale-while-revalidate disk cache: instant serve across server restarts.
        import json as _json
        _disk_path = _rrg_disk_path()
        _disk = {}
        try:
            if os.path.exists(_disk_path):
                with open(_disk_path, "r", encoding="utf-8") as _f:
                    _disk = _json.load(_f)
        except Exception:
            _disk = {}
        _disk_entry = _disk.get(rrg_cache_key)
        if isinstance(_disk_entry, dict) and (_dt.now(timezone.utc).timestamp() - _disk_entry.get("ts", 0) < 6 * 3600):
            return JSONResponse(content={"status": "success", "data": _disk_entry.get("payload")})

        bench_bm = (benchmark or "VNINDEX").upper()

        # Different feeds label weekly/monthly bars differently (period-start
        # vs period-end). Bucket times to a common key so RRG alignment works.
        def _norm_time_key(t) -> str:
            s = str(t)[:10]
            if ivl == "1M":
                return s[:7]
            if ivl == "1W":
                try:
                    iso = _dt.strptime(s, "%Y-%m-%d").isocalendar()
                    return f"{iso[0]}-W{iso[1]:02d}"
                except ValueError:
                    return s
            return s

        def _normalized(candles: list) -> list:
            out = []
            for c in candles:
                if isinstance(c, dict):
                    c = dict(c)
                    c["time"] = _norm_time_key(c.get("time", ""))
                    out.append(c)
            return out

        def _fetch_benchmark():
            try:
                b = get_benchmark_history(symbol=bench_bm, interval=ivl, lookback_days=500)
                return b.get("candles") or []
            except Exception:
                return []

        def _fetch_sector(code_sec):
            code, sec = code_sec
            try:
                idx = build_sector_index(code, interval=ivl, lookback_days=500) or {}
                return code, _normalized(idx.get("candles") or [])
            except Exception:
                return code, []

        # Parallelize all I/O-bound upstream fetches (Node subprocess + HTTP).
        sector_names = {code: sec.get("name") or code for code, sec in SECTOR_ICB_REGISTRY.items()}
        _bench_fut = _executor.submit(_fetch_benchmark)
        _sec_futs = [_executor.submit(_fetch_sector, item) for item in SECTOR_ICB_REGISTRY.items()]

        bench_candles = _normalized(_bench_fut.result())
        sectors_hist = {}
        for _f in _sec_futs:
            code, candles = _f.result()
            sectors_hist[code] = candles

        matrix = build_rrg_matrix(
            sectors_hist,
            bench_candles,
            tail=tail_n,
            method=m,
            sector_names=sector_names
        )

        payload = {
            "benchmark": bench_bm,
            "interval": ivl,
            "method": matrix.get("method", m),
            "generated_at": _dt.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "points": matrix.get("points", [])
        }
        _cache.set(rrg_cache_key, payload, ttl_seconds=300)
        try:
            _disk[rrg_cache_key] = {"ts": _dt.now(timezone.utc).timestamp(), "payload": payload}
            with open(_disk_path, "w", encoding="utf-8") as _f:
                _json.dump(_disk, _f)
        except Exception:
            pass
        return JSONResponse(content={"status": "success", "data": payload})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/peers")
def api_company_peers(
    symbol: str = Query(..., description="Stock symbol to compare with industry peers"),
    top_k: int = Query(10, description="Max peers to return: 5, 10, 20, 50, or 0 for all in sector"),
    exchange: Optional[str] = Query("ALL", description="Exchange filter: ALL, HOSE, HNX, UPCOM")
):
    """Returns comparison metrics with same ICB industry peers across 3 exchanges"""
    try:
        data = get_company_peers(symbol=symbol, top_k=top_k, exchange=exchange)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/symbols/stats")
def api_symbols_stats():
    """Returns total symbols count and breakdown by exchange, type, and sector"""
    try:
        data = get_symbols_stats()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.post("/api/symbols/sync")
def api_symbols_sync(force: bool = Query(False, description="Force re-fetch from all providers")):
    """Live syncs all symbols across HOSE, HNX, UPCOM, ETF, CW, BOND from vnstock"""
    try:
        data = sync_universe_from_vnstock(force=force)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/search")
def api_search(q: str = Query("", description="Query symbol or name")):
    """Search stocks and macro indicators by symbol or name"""
    try:
        data = search_symbols(q=q)
        if q:
            ql = q.lower().strip()
            macro_items = get_macro_board_summary()
            matched_macro = []
            
            MACRO_SEARCH_ALIASES = {
                "USDVND": ["usd", "vnd", "usdvnd", "tỷ giá", "ty gia", "ngoại hối", "ngoai hoi", "ngoại tệ", "vietcombank", "vcb", "sbv"],
                "VN10Y": ["vn10y", "trái phiếu", "trai phieu", "lợi suất", "loi suat", "lãi suất", "lai suat", "yield", "10y", "10 năm"],
                "SBV_OMO": ["omo", "tín phiếu", "tin phieu", "sbv", "ngân hàng nhà nước", "bơm tiền", "hút tiền", "lãi suất", "lai suat", "thanh khoản", "thanh khoan", "repo"],
                "CPI_VN": ["cpi", "lạm phát", "lam phat", "giá cả", "gia ca", "tiêu dùng", "tieu dung", "gso", "rổ hàng hóa"],
                "GDP_VN": ["gdp", "tăng trưởng", "tang truong", "tổng sản phẩm", "tong san pham", "kinh tế", "kinh te", "gso"],
                "PMI_VN": ["pmi", "sản xuất", "san xuat", "mua hàng", "mua hang", "s&p global", "đơn hàng", "don hang"],
                "FDI_VN": ["fdi", "đầu tư", "dau tu", "vốn ngoại", "von ngoai", "trực tiếp nước ngoài", "kcn", "khu công nghiệp"],
                "DXY": ["dxy", "dollar", "đô la", "do la", "sức mạnh usd", "us dollar"],
                "BRENT": ["brent", "dầu", "dau", "oil", "xăng dầu", "xang dau", "dầu thô", "dau tho", "opec", "năng lượng"]
            }

            for m in macro_items:
                sym = m["symbol"]
                aliases = MACRO_SEARCH_ALIASES.get(sym, [])
                is_match = (
                    ql in sym.lower() or 
                    ql in m["name"].lower() or 
                    ql in m.get("category", "").lower() or
                    ql in m.get("target_desc", "").lower() or
                    any(ql in a or a in ql for a in aliases)
                )
                if is_match:
                    matched_macro.append({
                        "symbol": m["symbol"],
                        "name": f"{m['icon']} {m['name']} ({m.get('target_desc', '')})",
                        "exchange": m.get("category", "Vĩ Mô"),
                        "type": "MACRO"
                    })
            data = matched_macro + data
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/article-content")
def api_article_content(url: str = Query(..., description="Full URL of the article to extract")):
    """Fetches clean, distraction-free article text, sapo, images, and metadata for In-App Reader View"""
    try:
        data = extract_article(url=url)
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)})

# ==============================================================================
# VNSTOCK QUANT SCREENER & 3-SCENARIO EARNINGS VALUATION API ENDPOINTS
# ==============================================================================

@app.get("/api/screener/quant-ranking")
@app.get("/api/screener/quant")
def api_quant_screener(
    sector: str = Query("ALL", description="Sector ICB code: ALL, VNMAT, VNFIN, VNREAL, VNIT, VNCONS, VNCOND, VNENE, VNUTI, VNIND, VNHEAL"),
    quintile: str = Query("ALL", description="Quintile rank: ALL, Q1 (Top 20%), Q2, Q3, Q4, Q5"),
    exchange: str = Query("ALL", description="Exchange: ALL, HOSE, HNX, UPCOM"),
    strategy: str = Query("ALL", description="Strategy filter: ALL, deep_value_klarman, ps_focus_fisher, contrarian_dreman, growth_philip_fisher, peter_lynch_garp, defensive_graham, value_buffett, hello_lower_risk, hello_balanced_risk, hello_full_throttle, tsmom_moskowitz"),
    min_growth: float = Query(0.0, description="Minimum 5-Year Revenue Growth % (e.g. 50.0)"),
    max_pe: Optional[float] = Query(None, description="Max P/E; stocks with missing P/E are excluded"),
    min_roe: Optional[float] = Query(None, description="Minimum ROE %"),
    min_dy: Optional[float] = Query(None, description="Minimum Dividend Yield %"),
    max_de: Optional[float] = Query(None, description="Max Debt/Equity ratio"),
    max_peg: Optional[float] = Query(None, description="Max PEG ratio"),
    min_mcap: Optional[float] = Query(None, description="Min Market Cap in nghìn tỷ VNĐ (records store tỷ, compared as min_mcap*1000)"),
    sort_by: str = Query("composite", description="Sort by: composite, growth, quality, health, valuation, rev_5y_growth, rev_1y_growth, pat_1y_growth, roe, pe, pb, ps, peg, dividend_yield, fcf_ttm, market_cap"),
    sort_dir: str = Query("desc", description="desc or asc"),
    limit: int = Query(50, description="Max results per page"),
    offset: int = Query(0, description="Pagination offset"),
    survival_filter: bool = Query(False, description="Enable Universal Survival & Quality Anchors firewall"),
    tsmom_filter: bool = Query(False, description="Enable Time Series Momentum (TSMOM) 12M Trend Filter"),
    forensic_filter: bool = Query(False, description="Enable Forensic Accounting Firewall (F-Score >= 7 & M-Score < -1.78)")
):
    """Returns Multi-Factor Percentile Screener data with Q1-Q5 Quintiles, 4 Pillar Percentiles, and 10+ Investment Strategy filters."""
    try:
        data = get_quant_screener(
            sector=sector,
            quintile=quintile,
            exchange=exchange,
            strategy=strategy,
            min_growth_pct=min_growth,
            max_pe=max_pe,
            min_roe=min_roe,
            min_dy=min_dy,
            max_de=max_de,
            max_peg=max_peg,
            min_mcap=min_mcap,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
            survival_filter=survival_filter,
            tsmom_filter=tsmom_filter,
            forensic_filter=forensic_filter
        )
        try:
            from services.quant_scoring import _pillar_weights
            names = ["growth", "quality", "health", "valuation"]
            pillar_specs = _pillar_weights()
            data["factor_weights"] = {
                **{n: dict(zip(fields, weights)) for n, (fields, weights) in zip(names, pillar_specs)},
                "composite": {"growth": 0.35, "quality": 0.25, "health": 0.20, "valuation": 0.20}
            }
        except Exception:
            pass
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/company/earnings-engine")
def api_company_earnings_engine(symbol: str = Query("FPT", description="Stock ticker symbol")):
    """Returns 5-Way Growth Attribution, Core PAT Normalization, 4 Corrections, and 3-Scenario Valuation (Bear, Base, Bull) with Margin of Safety."""
    try:
        data = get_company_earnings_engine(symbol=symbol)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.post("/api/screener/quant-sync")
def api_quant_sync(force: bool = Query(True, description="Force re-compute full universe snapshot")):
    """Recomputes and saves full market-wide Quant Percentile rankings to snapshot cache."""
    try:
        data = compute_quant_percentile_universe(force_recompute=force)
        return JSONResponse(content={"status": "success", "total_symbols": data.get("total_symbols", 0), "updated_at": data.get("updated_at")})
    except Exception as e:
        return _error_response(e)

# ==============================================================================
# VNSTOCK QUANT SCREENER HISTORICAL BACKTESTING API ENDPOINTS
# ==============================================================================

@app.get("/api/backtest/strategies")
def api_backtest_strategies():
    """Returns metadata and rule descriptions for all built-in quantitative screener strategies."""
    try:
        data = get_strategy_definitions()
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.post("/api/backtest/compare")
def api_backtest_compare(
    time_horizon_years: int = Query(5, description="Backtest duration: 1, 3, 5, or 10 years"),
    rebalance_cadence: str = Query("quarterly", description="quarterly, semi_annual, annual"),
    top_k: int = Query(10, description="Number of holdings per strategy (e.g. 5, 10, 15)"),
    initial_capital: float = Query(100000000.0, description="Initial capital in VND"),
    exchange: str = Query("ALL", description="Exchange filter: ALL, HOSE, HNX, UPCOM or comma-separated e.g. HOSE,HNX"),
    survival_filter: bool = Query(False, description="Enable Universal Survival & Quality Anchors firewall"),
    fill_mode: str = Query("strict", description="Basket sizing: 'strict' keeps only stocks meeting all criteria (basket may be smaller than top_k); 'fill' pads with nearest-miss stocks ranked by that strategy's own criteria"),
    tsmom_filter: bool = Query(False, description="Enable Time Series Momentum (TSMOM) 12M Trend Filter"),
    forensic_filter: bool = Query(False, description="Enable Forensic Accounting (F-Score >= 7 & M-Score < -1.78) firewall")
):
    """Simultaneously runs and ranks multi-factor screener strategies vs VN-Index benchmark."""
    try:
        data = compare_all_screener_strategies(
            time_horizon_years=time_horizon_years,
            rebalance_cadence=rebalance_cadence,
            top_k=top_k,
            initial_capital=initial_capital,
            exchange=exchange,
            survival_filter=survival_filter,
            fill_mode=fill_mode,
            tsmom_filter=tsmom_filter,
            forensic_filter=forensic_filter
        )
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.post("/api/backtest/run")
def api_backtest_run(
    strategy_id: str = Query("quant_q1", description="Strategy ID"),
    time_horizon_years: int = Query(5, description="1, 3, 5, or 10 years"),
    rebalance_cadence: str = Query("quarterly", description="quarterly, semi_annual, annual"),
    top_k: int = Query(10, description="Top K stocks"),
    initial_capital: float = Query(100000000.0, description="Initial capital in VND"),
    exchange: str = Query("ALL", description="Exchange filter: ALL, HOSE, HNX, UPCOM or comma-separated e.g. HOSE,HNX"),
    survival_filter: bool = Query(False, description="Enable Universal Survival & Quality Anchors firewall"),
    fill_mode: str = Query("strict", description="Basket sizing: 'strict' keeps only stocks meeting all criteria (basket may be smaller than top_k); 'fill' pads with nearest-miss stocks ranked by that strategy's own criteria"),
    tsmom_filter: bool = Query(False, description="Enable Time Series Momentum (TSMOM) 12M Trend Filter"),
    forensic_filter: bool = Query(False, description="Enable Forensic Accounting (F-Score >= 7 & M-Score < -1.78) firewall")
):
    """Runs detailed historical simulation and generates equity curve + rebalance log for a single strategy."""
    try:
        data = run_screener_backtest(
            strategy_id=strategy_id,
            time_horizon_years=time_horizon_years,
            rebalance_cadence=rebalance_cadence,
            top_k=top_k,
            initial_capital=initial_capital,
            exchange=exchange,
            survival_filter=survival_filter,
            fill_mode=fill_mode,
            tsmom_filter=tsmom_filter,
            forensic_filter=forensic_filter
        )
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.api_route("/api/screener/quick-backtest", methods=["GET", "POST"])
def api_screener_quick_backtest(
    sector: str = Query("ALL", description="Sector ICB code"),
    quintile: str = Query("ALL", description="Quintile rank"),
    exchange: str = Query("ALL", description="Exchange: ALL, HOSE, HNX, UPCOM"),
    strategy: str = Query("ALL", description="Strategy preset"),
    min_growth: float = Query(0.0, description="Minimum 5-Year Revenue Growth %"),
    max_pe: Optional[float] = Query(None, description="Max P/E"),
    min_roe: Optional[float] = Query(None, description="Minimum ROE %"),
    min_dy: Optional[float] = Query(None, description="Minimum Dividend Yield %"),
    max_de: Optional[float] = Query(None, description="Max Debt/Equity ratio"),
    max_peg: Optional[float] = Query(None, description="Max PEG ratio"),
    min_mcap: Optional[float] = Query(None, description="Min Market Cap in nghìn tỷ"),
    survival_filter: bool = Query(False, description="Enable Universal Survival Firewall"),
    tsmom_filter: bool = Query(False, description="Enable Time Series Momentum (TSMOM) 12M Trend Filter"),
    forensic_filter: bool = Query(False, description="Enable Forensic Accounting Firewall"),
    time_horizon_years: int = Query(5, description="Backtest duration in years: 1, 3, 5, 10"),
    rebalance_cadence: str = Query("quarterly", description="quarterly, semi_annual, annual"),
    top_k: int = Query(10, description="Holding basket size"),
    initial_capital: float = Query(100000000.0, description="Initial capital in VND"),
    fill_mode: str = Query("strict", description="strict or fill")
):
    """Executes fast Point-in-Time backtest simulation for current screener filters/strategy without charts."""
    try:
        screener_res = get_quant_screener(
            sector=sector,
            quintile=quintile,
            exchange=exchange,
            strategy=strategy,
            min_growth_pct=min_growth,
            max_pe=max_pe,
            min_roe=min_roe,
            min_dy=min_dy,
            max_de=max_de,
            max_peg=max_peg,
            min_mcap=min_mcap,
            survival_filter=survival_filter,
            tsmom_filter=tsmom_filter,
            forensic_filter=forensic_filter,
            limit=500
        )
        stocks = screener_res.get("results", [])

        strat_key = strategy.lower().strip()
        if strat_key != "all" and strat_key in STRATEGY_DEFINITIONS:
            backtest_strat_id = strat_key
        else:
            backtest_strat_id = "custom"

        sim = run_screener_backtest(
            strategy_id=backtest_strat_id,
            time_horizon_years=time_horizon_years,
            rebalance_cadence=rebalance_cadence,
            top_k=top_k,
            initial_capital=initial_capital,
            exchange=exchange,
            min_growth_pct=min_growth,
            survival_filter=survival_filter,
            fill_mode=fill_mode,
            quant_universe=stocks,
            tsmom_filter=tsmom_filter,
            forensic_filter=forensic_filter
        )

        return JSONResponse(content={
            "status": "success",
            "data": {
                "strategy": sim.get("strategy", {}),
                "parameters": sim.get("parameters", {}),
                "metrics": sim.get("metrics", {}),
                "annual_matrix": sim.get("annual_matrix", {}),
                "matched_stocks_count": len(stocks)
            }
        })
    except Exception as e:
        return _error_response(e)

# ==============================================================================
# INSTITUTIONAL-GRADE QUANT VALIDATION LAB API ENDPOINTS
# ==============================================================================

@app.api_route("/api/quant/institutional/run", methods=["GET", "POST"])
def api_quant_institutional_run(
    symbol: str = Query("ALL", description="Universe (ALL, VN30, VN70, HOSE, HNX, UPCOM) or Stock symbol (FPT, HPG)"),
    strategy_type: str = Query("quant_q1", description="Strategy type: 32 factor/guru strategies or technical rules"),
    time_horizon_years: int = Query(3, description="Backtest duration in years: 1, 2, 3, 5, 10"),
    initial_capital: float = Query(100000000.0, description="Initial capital in VND"),
    risk_per_trade_pct: float = Query(1.5, description="Fixed Risk per trade %"),
    max_capital_fraction: float = Query(0.25, description="Max capital allocation fraction per trade"),
    top_k: int = Query(10, description="Holding basket size"),
    rebalance_cadence: str = Query("quarterly", description="quarterly, semi_annual, annual"),
    survival_filter: bool = Query(False, description="Enable Universal Survival Firewall"),
    tsmom_filter: bool = Query(False, description="Enable Time Series Momentum 12M Trend Filter"),
    fill_mode: str = Query("strict", description="strict or near_miss"),
    forensic_filter: bool = Query(False, description="Enable Forensic Accounting Firewall (F-Score >= 7 & M-Score < -1.78)"),
    atr_period: int = Query(14, description="ATR Lookback period"),
    atr_stop_multiplier: float = Query(2.5, description="ATR Trailing Stop distance multiplier"),
    take_profit_atr_multiplier: Optional[float] = Query(4.0, description="Take Profit ATR multiplier"),
    fast_period: int = Query(20, description="Fast MA / Donchian Entry period"),
    slow_period: int = Query(50, description="Slow MA / Trend baseline period"),
    commission_pct: float = Query(0.15, description="Brokerage commission % per trade"),
    tax_pct: float = Query(0.10, description="Selling withholding tax %"),
    slippage_pct: float = Query(0.10, description="Market execution slippage %"),
    t_plus_settlement: int = Query(2, description="Vietnam T+2.5 settlement cycle days"),
    margin_of_safety_pct: float = Query(15.0, description="Margin of Safety % for Valuation strategies"),
    composite_mode: str = Query("blended", description="blended or omnibus"),
    omnibus_metric: str = Query("smape", description="smape, male, wmape, rmsle, ivw"),
    fundamentals_mode: str = Query(
        "point_in_time",
        description=(
            "point_in_time (real filings published by the rebalance date) or "
            "snapshot_projected (legacy price-derived fundamentals)"
        ),
    ),
    use_dynamic_beta_mos: bool = Query(False, description="Enable dynamic beta MoS adjustment"),
    filter_rkv_value_trap: bool = Query(True, description="Enable Rhodes-Kropf value trap filter"),
    backtest_mode: Optional[str] = Query(None, description="factor, valuation, or hybrid"),
    screening_strategy: Optional[str] = Query(None, description="Screening strategy ID for Stage 1"),
    valuation_model_id: Optional[str] = Query(None, description="Valuation model ID for Stage 2")
):
    """Executes institutional backtest across any Index Universe or Single Stock for all 32 Quantitative/Guru Strategies + 22 Valuation Models."""
    try:
        data = run_bar_by_bar_backtest(
            symbol=symbol,
            strategy_type=strategy_type,
            time_horizon_years=time_horizon_years,
            initial_capital=initial_capital,
            risk_per_trade_pct=risk_per_trade_pct,
            max_capital_fraction=max_capital_fraction,
            top_k=top_k,
            rebalance_cadence=rebalance_cadence,
            survival_filter=survival_filter,
            tsmom_filter=tsmom_filter,
            fill_mode=fill_mode,
            forensic_filter=forensic_filter,
            atr_period=atr_period,
            atr_stop_multiplier=atr_stop_multiplier,
            take_profit_atr_multiplier=take_profit_atr_multiplier,
            fast_period=fast_period,
            slow_period=slow_period,
            commission_pct=commission_pct,
            tax_pct=tax_pct,
            slippage_pct=slippage_pct,
            t_plus_settlement=t_plus_settlement,
            margin_of_safety_pct=margin_of_safety_pct,
            composite_mode=composite_mode,
            omnibus_metric=omnibus_metric,
            fundamentals_mode=fundamentals_mode,
            use_dynamic_beta_mos=use_dynamic_beta_mos,
            filter_rkv_value_trap=filter_rkv_value_trap,
            backtest_mode=backtest_mode,
            screening_strategy=screening_strategy,
            valuation_model_id=valuation_model_id
        )
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.api_route("/api/quant/institutional/sensitivity", methods=["GET", "POST"])
def api_quant_institutional_sensitivity(
    symbol: str = Query("ALL", description="Universe or Stock symbol"),
    strategy_type: str = Query("quant_q1", description="Strategy type"),
    param1_name: str = Query("top_k", description="Parameter 1 name"),
    param2_name: str = Query("cadence", description="Parameter 2 name"),
    time_horizon_years: int = Query(3, description="Duration in years"),
    backtest_mode: Optional[str] = Query(None, description="factor, valuation, or hybrid"),
    screening_strategy: Optional[str] = Query(None, description="Screening strategy ID"),
    valuation_model_id: Optional[str] = Query(None, description="Valuation model ID"),
    composite_mode: str = Query("blended", description="blended or omnibus"),
    omnibus_metric: str = Query("smape", description="smape, male, wmape, rmsle, ivw")
):
    """Executes 2D parameter grid scan and detects Parameter Plateaus vs Overfitted Cliffs for any strategy."""
    try:
        data = run_parameter_sensitivity(
            symbol=symbol,
            strategy_type=strategy_type,
            param1_name=param1_name,
            param2_name=param2_name,
            time_horizon_years=time_horizon_years,
            backtest_mode=backtest_mode,
            screening_strategy=screening_strategy,
            valuation_model_id=valuation_model_id,
            composite_mode=composite_mode,
            omnibus_metric=omnibus_metric
        )
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.api_route("/api/quant/institutional/walk-forward", methods=["GET", "POST"])
def api_quant_institutional_walk_forward(
    symbol: str = Query("ALL", description="Universe or Stock symbol"),
    strategy_type: str = Query("quant_q1", description="Strategy type"),
    train_window_bars: int = Query(350, description="In-sample training window bars"),
    test_window_bars: int = Query(100, description="Out-of-sample forward evaluation bars"),
    initial_capital: float = Query(100000000.0, description="Initial capital in VND")
):
    """Executes multi-window rolling Walk-Forward Analysis and stitches continuous Out-of-Sample equity curve."""
    try:
        data = run_walk_forward_analysis(
            symbol=symbol,
            strategy_type=strategy_type,
            train_window_bars=train_window_bars,
            test_window_bars=test_window_bars,
            initial_capital=initial_capital
        )
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.api_route("/api/quant/institutional/monte-carlo", methods=["GET", "POST"])
def api_quant_institutional_monte_carlo(
    symbol: str = Query("ALL", description="Universe or Stock symbol"),
    strategy_type: str = Query("quant_q1", description="Strategy type"),
    time_horizon_years: int = Query(3, description="Duration in years"),
    top_k: int = Query(10, description="Top K stocks"),
    rebalance_cadence: str = Query("quarterly", description="Rebalance cadence"),
    survival_filter: bool = Query(False, description="Survival firewall"),
    tsmom_filter: bool = Query(False, description="TSMOM filter"),
    fill_mode: str = Query("strict", description="strict or near_miss"),
    forensic_filter: bool = Query(False, description="Forensic firewall"),
    iterations: int = Query(1000, description="Number of Bootstrap & Permutation iterations"),
    margin_of_safety_pct: float = Query(15.0, description="Margin of Safety % for Valuation strategies"),
    composite_mode: str = Query("blended", description="blended or omnibus"),
    omnibus_metric: str = Query("smape", description="smape, male, wmape, rmsle, ivw"),
    backtest_mode: Optional[str] = Query(None, description="factor, valuation, or hybrid"),
    screening_strategy: Optional[str] = Query(None, description="Screening strategy ID"),
    valuation_model_id: Optional[str] = Query(None, description="Valuation model ID")
):
    """Runs 1,000 Bootstrap Resamplings (95% CI) and 1,000 Permutations for any Strategy or Universe."""
    try:
        sim = run_bar_by_bar_backtest(
            symbol=symbol,
            strategy_type=strategy_type,
            time_horizon_years=time_horizon_years,
            top_k=top_k,
            rebalance_cadence=rebalance_cadence,
            survival_filter=survival_filter,
            tsmom_filter=tsmom_filter,
            fill_mode=fill_mode,
            forensic_filter=forensic_filter,
            margin_of_safety_pct=margin_of_safety_pct,
            composite_mode=composite_mode,
            omnibus_metric=omnibus_metric,
            backtest_mode=backtest_mode,
            screening_strategy=screening_strategy,
            valuation_model_id=valuation_model_id
        )
        trades = sim.get("trades", [])
        data = run_monte_carlo_stress_test(
            trades=trades,
            initial_capital=sim.get("parameters", {}).get("initial_capital", 100000000.0),
            iterations=iterations
        )
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

@app.get("/api/data-lake-status")
def api_data_lake_status():
    """Returns live multi-source data lake statistics and stock pool coverage counters."""
    try:
        from services.stock_service import cache as _cache
        cached = _cache.get("api_data_lake_status")
        if cached is not None:
            return JSONResponse(content={"status": "success", "data": cached})
        data = get_data_lake_status()
        _cache.set("api_data_lake_status", data, ttl_seconds=300)
        return JSONResponse(content={"status": "success", "data": data})
    except Exception as e:
        return _error_response(e)

# ==============================================================================
# 22-MODEL QUANTITATIVE VALUATION & 3-MODE MODULAR BACKTEST API ENDPOINTS
# ==============================================================================

_valuation_engine_instance = ValuationEngine()

@app.get("/api/valuation/comprehensive/{symbol}")
@app.get("/api/valuation/matrix/{symbol}")
def api_get_comprehensive_valuation(
    symbol: str,
    mode: str = Query("blended", description="blended (Sector structural blend) or omnibus (Loss metric error weighting)"),
    metric: str = Query("smape", description="smape, male, wmape, rmsle, ivw (Only when mode=omnibus)")
):
    """
    Returns full 22-model valuation matrix, WACC breakdown, 4-quadrant Z+M risk firewalls,
    3-scenario Bear/Base/Bull analysis, and 5x5 sensitivity grid for a stock symbol.
    """
    try:
        sym = symbol.upper().strip()
        # Fetch fundamental snapshot if available in screener lake
        screener_data = get_quant_screener(limit=5000)
        matched_stock = None
        for s in screener_data.get("results", []):
            if str(s.get("symbol", "")).upper() == sym:
                matched_stock = s
                break

        val_res = _valuation_engine_instance.get_comprehensive_valuation(
            symbol=sym,
            fundamental_data=matched_stock,
            composite_mode=mode,
            omnibus_metric=metric,
        )
        return JSONResponse(content={"status": "success", "data": val_res.to_dict()})
    except ValueError as e:
        # Missing or unusable inputs (no fundamentals, no price): a data gap,
        # not a server fault. Surfaced so the UI can say why rather than
        # rendering a valuation built on defaults.
        return JSONResponse(status_code=422, content={"status": "error", "message": str(e)})
    except Exception as e:
        return _error_response(e)


@app.get("/api/valuation/matrix")
def api_get_valuation_matrix_query(
    symbol: Optional[str] = Query(None, description="Ticker symbol e.g. VCB, HPG, FPT"),
    mode: str = Query("blended", description="blended (Sector structural blend) or omnibus (Loss metric error weighting)"),
    metric: str = Query("smape", description="smape, male, wmape, rmsle, ivw (Only when mode=omnibus)")
):
    """
    Alias for comprehensive valuation matrix accessed via query parameter (?symbol=...).
    """
    if not symbol:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Symbol query parameter is required"})
    return api_get_comprehensive_valuation(symbol=symbol, mode=mode, metric=metric)


@app.get("/api/valuation/3-way-forecast/{symbol}")
def api_get_three_statement_forecast(
    symbol: str,
    start_year: Optional[int] = Query(None, description="Initial forecast year; defaults to the current year"),
    tax_rate: float = Query(0.20, description="Corporate income tax rate (default 20%)"),
):
    """
    Returns 5-Year Dynamic 3-Way Integrated Financial Statement Forecast
    (Income Statement, Balance Sheet, Direct Method CFS, Working Capital, Debt Schedule, Liquidity Distress).
    """
    try:
        sym = symbol.upper().strip()
        forecast_res = ThreeStatementEngine.build_forecast_from_screener(
            symbol=sym,
            tax_rate=tax_rate,
            start_year=start_year,
        )
        return JSONResponse(content={"status": "success", "data": forecast_res.to_dict()})
    except Exception as e:
        return _error_response(e)


@app.get("/api/valuation/export-excel/{symbol}")
def api_export_financial_model_excel(
    symbol: str,
    scale_unit: str = Query("billion", description="Scale unit: 'billion' (default, in Billion VND) or 'raw'"),
    start_year: Optional[int] = Query(None, description="Initial forecast year; defaults to the current year"),
    tax_rate: float = Query(0.20, description="Corporate income tax rate"),
):
    """
    Generates and downloads the 7-Tab Modano-compliant dynamic financial model in Microsoft Excel (.xlsx) format.
    """
    try:
        sym = symbol.upper().strip()
        forecast_res = ThreeStatementEngine.build_forecast_from_screener(
            symbol=sym,
            tax_rate=tax_rate,
            start_year=start_year,
        )
        export_dir = os.path.join("data", "exports")
        os.makedirs(export_dir, exist_ok=True)
        filename = f"{sym}_3Way_Financial_Model.xlsx"
        filepath = os.path.join(export_dir, filename)

        FinancialModelExporter.export_to_excel(
            forecast_result=forecast_res,
            output_path=filepath,
            scale_unit=scale_unit,
        )

        return FileResponse(
            path=filepath,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        return _error_response(e)


@app.get("/api/backtest/fair_value/presets")
@app.get("/api/backtest/fair-value/presets")
def api_get_fair_value_backtest_presets():
    """
    Returns available presets, modes, strategies, and valuation models for the 3-mode backtest engine.
    """
    return JSONResponse(content={
        "status": "success",
        "data": fv_backtest_service.get_presets()
    })


@app.api_route("/api/backtest/fair_value/run", methods=["GET", "POST"])
@app.api_route("/api/backtest/fair-value/run", methods=["GET", "POST"])
def api_run_fair_value_backtest(
    mode: str = Query(BacktestMode.HYBRID_FUNNEL, description="valuation_only, screening_only, hybrid_funnel"),
    screening_strategy: str = Query("peter_lynch_garp", description="Screening strategy ID"),
    valuation_model_id: str = Query("composite_fair_value", description="Valuation model ID"),
    margin_of_safety_pct: float = Query(15.0, description="Margin of Safety % discount for entry"),
    exit_premium_pct: float = Query(20.0, description="Take profit exit premium % over fair value"),
    use_dynamic_beta_mos: bool = Query(True, description="Scale MoS dynamically by Downside Beta"),
    filter_z_score_safe: bool = Query(True, description="Filter out Z-Score toxic / manipulation traps"),
    filter_rkv_value_trap: bool = Query(True, description="Filter out Rhodes-Kropf value traps"),
    exchange: str = Query("ALL", description="Exchange / Index universe: ALL, VN30, VN70, VNMID, HOSE, HNX, UPCOM"),
    top_k: int = Query(10, description="Number of top stocks per rebalance"),
    rebalance_cadence: str = Query("quarterly", description="quarterly, semi_annual, annual, monthly"),
    fill_mode: str = Query("strict", description="strict (with fees/tax/slippage) or ideal"),
    survival_filter: bool = Query(True, description="Universal Survival Firewall filter"),
    tsmom_filter: bool = Query(False, description="Time-Series Momentum 12M trend filter"),
    forensic_filter: bool = Query(False, description="Forensic Accounting M-Score filter"),
    initial_capital: float = Query(100_000_000.0, description="Starting capital in VND"),
    holding_period_months: int = Query(12, description="Target holding horizon in months"),
    start_year: int = Query(2021, description="Start year"),
    end_year: Optional[int] = Query(None, description="End year; defaults to the current year"),
    composite_mode: str = Query("blended", description="blended or omnibus"),
    omnibus_metric: str = Query("smape", description="smape, male, wmape, rmsle, ivw"),
    fundamentals_mode: str = Query(
        "point_in_time",
        description=(
            "point_in_time (real quarterly filings, published by the rebalance "
            "date; symbols without one are skipped) or snapshot_projected "
            "(legacy: today's multiples projected onto historical prices, which "
            "makes every fair value a fixed multiple of the entry price)"
        ),
    ),
):
    """
    Executes an Institutional 3-Mode Modular Fair Value Quant Backtest across the Vietnamese equity universe.
    """
    try:
        res = fv_backtest_service.run_backtest(
            mode=mode,
            screening_strategy=screening_strategy,
            valuation_model_id=valuation_model_id,
            margin_of_safety_pct=margin_of_safety_pct,
            exit_premium_pct=exit_premium_pct,
            use_dynamic_beta_mos=use_dynamic_beta_mos,
            filter_z_score_safe=filter_z_score_safe,
            filter_rkv_value_trap=filter_rkv_value_trap,
            exchange=exchange,
            top_k=top_k,
            rebalance_cadence=rebalance_cadence,
            fill_mode=fill_mode,
            survival_filter=survival_filter,
            tsmom_filter=tsmom_filter,
            forensic_filter=forensic_filter,
            initial_capital=initial_capital,
            holding_period_months=holding_period_months,
            start_year=start_year,
            end_year=end_year,
            composite_mode=composite_mode,
            omnibus_metric=omnibus_metric,
            fundamentals_mode=fundamentals_mode,
        )
        return JSONResponse(content={"status": "success", "data": res.to_dict()})
    except Exception as e:
        return _error_response(e)

# ==============================================================================
# PRICE ALERTS API ENDPOINTS
# ==============================================================================

@app.get("/api/alerts")
def api_list_alerts():
    """Returns all price alert rules with their fired state"""
    rules = sorted(_alert_rules_store.values(), key=lambda r: r["id"])
    return JSONResponse(content={"status": "success", "data": rules})

@app.post("/api/alerts")
def api_create_alert(rule: AlertRuleCreate):
    """Creates a new server-side price alert rule {symbol, condition, value}"""
    try:
        symbol = rule.symbol.strip().upper()
        if not symbol:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Symbol is required"})
        cond = rule.condition if rule.condition in ("price_above", "price_below", "pct_change") else "price_above"
        item = {
            "id": next(_alert_id_seq),
            "symbol": symbol,
            "condition": cond,
            "value": float(rule.value),
            "active": True,
            "fired": False,
            "created_at": _now_iso(),
            "fired_at": None,
            "triggered_value": None
        }
        _alert_rules_store[item["id"]] = item
        _save_alert_rules()
        return JSONResponse(content={"status": "success", "data": item})
    except Exception as e:
        return _error_response(e)

@app.delete("/api/alerts/{rule_id}")
def api_delete_alert(rule_id: int):
    """Deletes a price alert rule by id"""
    removed = _alert_rules_store.pop(rule_id, None)
    if removed is None:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Alert not found"})
    _save_alert_rules()
    return JSONResponse(content={"status": "success"})

@app.post("/api/alerts/{rule_id}/rearm")
def api_rearm_alert(rule_id: int):
    """Re-arms a fired alert rule so it can trigger again"""
    rule = _alert_rules_store.get(rule_id)
    if not rule:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Alert not found"})
    rule["fired"] = False
    rule["fired_at"] = None
    rule["triggered_value"] = None
    _save_alert_rules()
    return JSONResponse(content={"status": "success", "data": rule})

@app.get("/api/screener/quant/export.csv")
def api_quant_screener_export_csv(
    sector: str = Query("ALL"),
    quintile: str = Query("ALL"),
    exchange: str = Query("ALL"),
    strategy: str = Query("ALL"),
    min_growth: float = Query(0.0),
    max_pe: Optional[float] = Query(None),
    min_roe: Optional[float] = Query(None),
    min_dy: Optional[float] = Query(None),
    max_de: Optional[float] = Query(None),
    max_peg: Optional[float] = Query(None),
    min_mcap: Optional[float] = Query(None),
    sort_by: str = Query("composite"),
    sort_dir: str = Query("desc"),
    survival_filter: bool = Query(False),
    tsmom_filter: bool = Query(False)
):
    """Exports the current ranked quant screener table as a CSV download"""
    try:
        from services.stock_service import cache as _cache
        csv_cache_key = f"screener_csv_{sector}_{quintile}_{exchange}_{strategy}_{min_growth}_{max_pe}_{min_roe}_{min_dy}_{max_de}_{max_peg}_{min_mcap}_{sort_by}_{sort_dir}_{survival_filter}_{tsmom_filter}"
        cached_csv = _cache.get(csv_cache_key)
        if cached_csv:
            return Response(
                content=cached_csv,
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": "attachment; filename=quant_screener.csv"}
            )

        data = get_quant_screener(
            sector=sector,
            quintile=quintile,
            exchange=exchange,
            strategy=strategy,
            min_growth_pct=min_growth,
            max_pe=max_pe,
            min_roe=min_roe,
            min_dy=min_dy,
            max_de=max_de,
            max_peg=max_peg,
            min_mcap=min_mcap,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=5000,
            offset=0,
            survival_filter=survival_filter,
            tsmom_filter=tsmom_filter
        )
        results = data.get("results") or []
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "rank", "symbol", "name", "exchange", "industry", "price", "change_pct",
            "quintile", "composite_score", "pe", "pb", "ps", "peg",
            "roe_pct", "de_ratio", "dividend_yield_pct", "rev_5y_growth_pct"
        ])
        for i, s in enumerate(results, 1):
            p = s.get("percentiles") or {}
            writer.writerow([
                i, s.get("symbol", ""), s.get("name", ""), s.get("exchange", ""), s.get("industry", ""),
                s.get("price", ""), s.get("change_pct", ""),
                p.get("quintile", ""), p.get("composite", ""),
                s.get("pe", ""), s.get("pb", ""), s.get("ps", ""), s.get("peg", ""),
                s.get("roe", ""), s.get("de_ratio", ""), s.get("dividend_yield", ""), s.get("rev_5y_growth", "")
            ])
        csv_text = "\ufeff" + buf.getvalue()
        _cache.set(csv_cache_key, csv_text, ttl_seconds=60)
        return Response(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=quant_screener.csv"}
        )
    except Exception as e:
        return _error_response(e)

# Static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return JSONResponse(content={"message": "Frontend index.html is being built"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
