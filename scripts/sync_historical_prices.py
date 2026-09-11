"""Daily prices for the whole universe, quarterised into the price lake.

Sources, in the order they are tried: DNSE's chart endpoint, then SSI's,
then TCBS's, then a yfinance batch download, then vnstock per symbol. Each symbol is counted against the
source that actually answered for it, and the tally is printed - because
this header used to say "TRADINGVIEW & VCI DATA FEEDS" and the saved
payload used to say "TradingView & Yahoo Finance Live Data Feeds" while
the code reached for neither TradingView nor VCI. A label nobody can
check is worse than no label: it was read as evidence that TradingView
was already carrying the lake.

Output: data/historical_prices.json, keyed by symbol then quarter.
"""

import os
import sys
import json
import time
import datetime
import requests
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logger = logging.getLogger(__name__)

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        logger.debug("Could not switch the console to UTF-8", exc_info=True)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# TLS policy: verify by default; opt-out only via VNSTOCK_INSECURE_TLS=1
from services.tls_config import tls_verify, configure_urllib_warnings
configure_urllib_warnings()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "historical_prices.json")

# Master Quarter Milestones (2016 - 2026)
QUARTER_MILESTONES = [
    {"code": "2016-Q1", "start": "2016-01-01", "end": "2016-03-31", "year": 2016, "quarter": 1},
    {"code": "2016-Q2", "start": "2016-04-01", "end": "2016-06-30", "year": 2016, "quarter": 2},
    {"code": "2016-Q3", "start": "2016-07-01", "end": "2016-09-30", "year": 2016, "quarter": 3},
    {"code": "2016-Q4", "start": "2016-10-01", "end": "2016-12-31", "year": 2016, "quarter": 4},

    {"code": "2017-Q1", "start": "2017-01-01", "end": "2017-03-31", "year": 2017, "quarter": 1},
    {"code": "2017-Q2", "start": "2017-04-01", "end": "2017-06-30", "year": 2017, "quarter": 2},
    {"code": "2017-Q3", "start": "2017-07-01", "end": "2017-09-30", "year": 2017, "quarter": 3},
    {"code": "2017-Q4", "start": "2017-10-01", "end": "2017-12-31", "year": 2017, "quarter": 4},

    {"code": "2018-Q1", "start": "2018-01-01", "end": "2018-03-31", "year": 2018, "quarter": 1},
    {"code": "2018-Q2", "start": "2018-04-01", "end": "2018-06-30", "year": 2018, "quarter": 2},
    {"code": "2018-Q3", "start": "2018-07-01", "end": "2018-09-30", "year": 2018, "quarter": 3},
    {"code": "2018-Q4", "start": "2018-10-01", "end": "2018-12-31", "year": 2018, "quarter": 4},

    {"code": "2019-Q1", "start": "2019-01-01", "end": "2019-03-31", "year": 2019, "quarter": 1},
    {"code": "2019-Q2", "start": "2019-04-01", "end": "2019-06-30", "year": 2019, "quarter": 2},
    {"code": "2019-Q3", "start": "2019-07-01", "end": "2019-09-30", "year": 2019, "quarter": 3},
    {"code": "2019-Q4", "start": "2019-10-01", "end": "2019-12-31", "year": 2019, "quarter": 4},

    {"code": "2020-Q1", "start": "2020-01-01", "end": "2020-03-31", "year": 2020, "quarter": 1},
    {"code": "2020-Q2", "start": "2020-04-01", "end": "2020-06-30", "year": 2020, "quarter": 2},
    {"code": "2020-Q3", "start": "2020-07-01", "end": "2020-09-30", "year": 2020, "quarter": 3},
    {"code": "2020-Q4", "start": "2020-10-01", "end": "2020-12-31", "year": 2020, "quarter": 4},

    {"code": "2021-Q1", "start": "2021-01-01", "end": "2021-03-31", "year": 2021, "quarter": 1},
    {"code": "2021-Q2", "start": "2021-04-01", "end": "2021-06-30", "year": 2021, "quarter": 2},
    {"code": "2021-Q3", "start": "2021-07-01", "end": "2021-09-30", "year": 2021, "quarter": 3},
    {"code": "2021-Q4", "start": "2021-10-01", "end": "2021-12-31", "year": 2021, "quarter": 4},

    {"code": "2022-Q1", "start": "2022-01-01", "end": "2022-03-31", "year": 2022, "quarter": 1},
    {"code": "2022-Q2", "start": "2022-04-01", "end": "2022-06-30", "year": 2022, "quarter": 2},
    {"code": "2022-Q3", "start": "2022-07-01", "end": "2022-09-30", "year": 2022, "quarter": 3},
    {"code": "2022-Q4", "start": "2022-10-01", "end": "2022-12-31", "year": 2022, "quarter": 4},

    {"code": "2023-Q1", "start": "2023-01-01", "end": "2023-03-31", "year": 2023, "quarter": 1},
    {"code": "2023-Q2", "start": "2023-04-01", "end": "2023-06-30", "year": 2023, "quarter": 2},
    {"code": "2023-Q3", "start": "2023-07-01", "end": "2023-09-30", "year": 2023, "quarter": 3},
    {"code": "2023-Q4", "start": "2023-10-01", "end": "2023-12-31", "year": 2023, "quarter": 4},

    {"code": "2024-Q1", "start": "2024-01-01", "end": "2024-03-31", "year": 2024, "quarter": 1},
    {"code": "2024-Q2", "start": "2024-04-01", "end": "2024-06-30", "year": 2024, "quarter": 2},
    {"code": "2024-Q3", "start": "2024-07-01", "end": "2024-09-30", "year": 2024, "quarter": 3},
    {"code": "2024-Q4", "start": "2024-10-01", "end": "2024-12-31", "year": 2024, "quarter": 4},

    {"code": "2025-Q1", "start": "2025-01-01", "end": "2025-03-31", "year": 2025, "quarter": 1},
    {"code": "2025-Q2", "start": "2025-04-01", "end": "2025-06-30", "year": 2025, "quarter": 2},
    {"code": "2025-Q3", "start": "2025-07-01", "end": "2025-09-30", "year": 2025, "quarter": 3},
    {"code": "2025-Q4", "start": "2025-10-01", "end": "2025-12-31", "year": 2025, "quarter": 4},

    {"code": "2026-Q1", "start": "2026-01-01", "end": "2026-03-31", "year": 2026, "quarter": 1}
]

def fetch_from_yfinance(symbol: str) -> Optional[pd.DataFrame]:
    """Fallback fetcher using Yahoo Finance (yfinance) for Vietnamese stocks."""
    try:
        import yfinance as yf
        ticker_str = f"{symbol}.VN"
        df = yf.download(ticker_str, start="2016-01-01", end="2026-03-31", progress=False)
        if df is not None and not df.empty and len(df) >= 10:
            df = df.reset_index()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0].lower() if isinstance(c, tuple) else str(c).lower() for c in df.columns]
            else:
                df.columns = [str(c).lower() for c in df.columns]
            
            if 'date' in df.columns:
                df['time'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            elif 'datetime' in df.columns:
                df['time'] = pd.to_datetime(df['datetime']).dt.strftime('%Y-%m-%d')
            
            if 'close' in df.columns and 'time' in df.columns:
                return df[['time', 'open', 'high', 'low', 'close', 'volume']]
    except Exception:
        logger.debug("fetch_from_yfinance: swallowed Exception", exc_info=True)
    return None

def fetch_stock_raw_candles(symbol: str) -> Optional[pd.DataFrame]:
    """
    Multi-source raw candle fetcher with graceful fallbacks:
    Priority 1: Vietcap (VCI) Data Feed
    Priority 2: KBSV / DNSE Data Feed
    Priority 3: Yahoo Finance (yfinance)
    """
    from vnstock import Quote
    
    # 1. Try VCI / KBS / DNSE Data Feeds
    for src in ['vci', 'kbs', 'dnse']:
        try:
            q = Quote(symbol=symbol, source=src)
            df = q.history(start='2016-01-01', end='2026-03-31', interval='1D')
            if df is not None and not df.empty and 'time' in df.columns and 'close' in df.columns:
                return df
        except Exception:
            continue

    # 2. Try yfinance Fallback
    yf_df = fetch_from_yfinance(symbol)
    if yf_df is not None and not yf_df.empty:
        return yf_df

    return None

def compute_stock_quarterly_returns(symbol: str, df: pd.DataFrame) -> Dict[str, Any]:
    """Computes exact quarterly close prices and percentage returns from daily real candles with VND scale normalization."""
    df['time_dt'] = pd.to_datetime(df['time'])
    df = df.sort_values('time_dt').reset_index(drop=True)

    quarters_data = {}
    prev_close = None

    for q in QUARTER_MILESTONES:
        q_code = q["code"]
        start_d = pd.to_datetime(q["start"])
        end_d = pd.to_datetime(q["end"])

        # Filter candles within this quarter
        q_df = df[(df['time_dt'] >= start_d) & (df['time_dt'] <= end_d)]
        if q_df.empty:
            # If no data in this quarter (e.g. stock listed later), continue
            continue

        start_candle = q_df.iloc[0]
        end_candle = q_df.iloc[-1]

        q_open = float(start_candle['open'])
        q_close = float(end_candle['close'])
        q_high = float(q_df['high'].max())
        q_low = float(q_df['low'].min())
        q_vol = int(q_df['volume'].sum())

        # Baseline start price: previous quarter close if available, else quarter open
        base_price = prev_close if prev_close is not None else q_open
        if base_price > 0:
            ret_pct = round(((q_close - base_price) / base_price) * 100.0, 2)
        else:
            ret_pct = 0.0

        quarters_data[q_code] = {
            "quarter": q_code,
            "start_date": str(start_candle['time']),
            "end_date": str(end_candle['time']),
            "start_price": round(base_price, 2),
            "close_price": round(q_close, 2),
            "high": round(q_high, 2),
            "low": round(q_low, 2),
            "volume": q_vol,
            "return_pct": ret_pct
        }
        prev_close = q_close

    return {
        "symbol": symbol,
        "total_quarters": len(quarters_data),
        "earliest_quarter": list(quarters_data.keys())[0] if quarters_data else None,
        "latest_quarter": list(quarters_data.keys())[-1] if quarters_data else None,
        "quarters": quarters_data
    }

#: Broker endpoints, in the order they are asked. DNSE and SSI each answer
#: a decade in one request; TCBS caps a response at 365 points, so ten
#: years costs ten requests per symbol, and it is reported to have closed
#: its unauthenticated endpoints since these URLs were written - so it
#: goes last and only sees what the other two had nothing for.
BROKER_SOURCES = ("dnse", "ssi", "tcbs")

#: How many symbols a broker may fail on before the stage stops asking it.
#: Large enough that a handful of delisted tickers cannot trip it, small
#: enough that a dead endpoint costs a minute rather than half an hour.
PROBE_BEFORE_GIVING_UP = 40


def _fetch_from_broker(source: str, symbol: str) -> Optional[pd.DataFrame]:
    """Daily candles from one broker, shaped like every other fetcher here."""
    from services import broker_prices
    fetch = {"dnse": broker_prices.fetch_dnse,
             "ssi": broker_prices.fetch_ssi,
             "tcbs": broker_prices.fetch_tcbs}[source]
    rows = fetch(symbol)
    if not rows:
        return None
    return pd.DataFrame(rows)


def sync_all_symbols(symbols_list: List[str], max_workers: int = 10,
                     exchanges: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Syncs real prices for all provided symbols concurrently and saves to JSON.

    Three sources, tried in order, and counted. The order changed: this
    used to lead with a yfinance batch download and fall back to vnstock
    per symbol, while the file header and the saved payload both claimed
    "TradingView" - which nothing in here touched. TradingView is now
    actually tried, first, and the tally at the end says which source
    answered for how many symbols so the claim can be checked rather than
    asserted.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    import yfinance as yf

    # exchanges is accepted and unused by the broker sources - both key on
    # the bare ticker - but the master list knows it and a future source
    # that needs a venue would otherwise have to re-derive it.
    exchanges = exchanges or {}
    by_source: Dict[str, int] = {}

    def record(source: str) -> None:
        by_source[source] = by_source.get(source, 0) + 1

    existing_store = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing_store = json.load(f).get("symbols", {})
        except Exception:
            existing_store = {}

    print(f"🚀 Starting Real Price Lake Sync for {len(symbols_list)} stocks...")
    start_time = time.time()
    symbols_to_fetch = [s for s in symbols_list if s not in existing_store or len(existing_store[s].get("quarters", {})) < 8]

    print(f"📦 Cached stocks: {len(existing_store)} | Stocks to fetch: {len(symbols_to_fetch)}")

    # --- sources 1 and 2: the brokers' own chart endpoints ----------------
    # Concurrent because each symbol is an independent HTTPS request. A
    # source that answers for nobody is dropped after PROBE_BEFORE_GIVING_UP
    # symbols rather than being asked 1,500 times: neither endpoint has
    # ever been reached from a machine that could test it, and a dead one
    # would otherwise cost the stage half an hour of timeouts.
    for source in BROKER_SOURCES:
        if not symbols_to_fetch:
            break
        print(f"🌐 {source}: asking for {len(symbols_to_fetch)} symbols...")
        started_source = time.time()
        answered = 0
        attempted = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_fetch_from_broker, source, sym): sym
                       for sym in symbols_to_fetch}
            for future in as_completed(futures):
                sym = futures[future]
                attempted += 1
                if answered == 0 and attempted > PROBE_BEFORE_GIVING_UP:
                    for pending in futures:
                        pending.cancel()
                    print(f"  ⚠️ {source} answered for none of the first "
                          f"{PROBE_BEFORE_GIVING_UP}; not asking it for the "
                          f"rest. Read this as the endpoint being wrong, "
                          f"not as the universe having no prices.")
                    break
                try:
                    df = future.result()
                except Exception:
                    logger.debug("%s fetch failed for %s", source, sym, exc_info=True)
                    continue
                if df is None or len(df) < 10:
                    continue
                res = compute_stock_quarterly_returns(sym, df)
                if res and res.get("total_quarters", 0) >= 4:
                    existing_store[sym] = res
                    record(source)
                    answered += 1
        print(f"🌐 {source} answered for {answered} of {len(symbols_to_fetch)} "
              f"in {round(time.time() - started_source, 1)}s")
        symbols_to_fetch = [s for s in symbols_to_fetch if s not in existing_store]
        print(f"📦 Still to fetch after {source}: {len(symbols_to_fetch)}")

    # Fast batch fetch using yfinance (50 tickers per batch)
    BATCH_SIZE = 50
    success_count = 0

    for i in range(0, len(symbols_to_fetch), BATCH_SIZE):
        chunk = symbols_to_fetch[i:i + BATCH_SIZE]
        tickers_str = " ".join([f"{s}.VN" for s in chunk])
        
        try:
            yf_data = yf.download(tickers_str, start="2016-01-01", end="2026-03-31", group_by="ticker", progress=False, threads=True)
            for sym in chunk:
                ticker_key = f"{sym}.VN"
                try:
                    if len(chunk) == 1:
                        df = yf_data
                    else:
                        if hasattr(yf_data.columns, 'levels') and ticker_key in yf_data.columns.levels[0]:
                            df = yf_data[ticker_key].dropna(how="all")
                        else:
                            df = None
                    if df is not None and not df.empty and len(df) >= 10:
                        df = df.reset_index()
                        df.columns = [c.lower() for c in df.columns]
                        res = compute_stock_quarterly_returns(sym, df)
                        if res and res.get("total_quarters", 0) >= 4:
                            existing_store[sym] = res
                            record("yfinance")
                            success_count += 1
                            if success_count % 15 == 0 or success_count <= 5:
                                print(f"  ✓ [{success_count}] {sym}: {res['total_quarters']} Quarters ({res['earliest_quarter']} -> {res['latest_quarter']})")
                except Exception:
                    logger.debug("sync_all_symbols: swallowed Exception", exc_info=True)
        except Exception as e:
            print(f"  ⚠️ Batch download error: {e}")

        # Fallback individual fetch for remaining missed symbols in chunk
        for sym in chunk:
            if sym not in existing_store:
                try:
                    df = fetch_stock_raw_candles(sym)
                    if df is not None and len(df) >= 10:
                        res = compute_stock_quarterly_returns(sym, df)
                        if res and res.get("total_quarters", 0) >= 4:
                            existing_store[sym] = res
                            record("vnstock")
                            success_count += 1
                except Exception:
                    logger.debug("sync_all_symbols: swallowed Exception", exc_info=True)

        # Save checkpoint
        if (i + BATCH_SIZE) % 100 == 0 or (i + BATCH_SIZE) >= len(symbols_to_fetch):
            payload = {
                "version": "3.5-unified-expanded",
                "last_updated": datetime.datetime.now().isoformat(),
                "total_symbols": len(existing_store),
                "source": ", ".join(f"{k}:{v}" for k, v in sorted(by_source.items())) or "none",
                "symbols": existing_store
            }
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"  💾 [Checkpoint Saved] Database contains {len(existing_store)} stocks")

    payload = {
        "version": "3.5-unified-expanded",
        "last_updated": datetime.datetime.now().isoformat(),
        "total_symbols": len(existing_store),
        "source": ", ".join(f"{k}:{v}" for k, v in sorted(by_source.items())) or "none",
        "symbols": existing_store
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    elapsed = round(time.time() - start_time, 2)
    print(f"✨ Successfully synced {len(existing_store)} stocks in {elapsed}s to {OUTPUT_FILE}")
    # The tally is the point of this pass. Whether vnstock can be dropped
    # is decided by the number next to it, not by preference: a source
    # that answered for nobody costs nothing to remove, and one that
    # answered for hundreds is carrying the backtest.
    print()
    print("| price source | symbols it answered for |")
    print("|---|---:|")
    for source, count in sorted(by_source.items(), key=lambda kv: -kv[1]):
        print(f"| {source} | {count:,} |")
    quiet = [s for s in BROKER_SOURCES if not by_source.get(s)]
    if quiet:
        print()
        print(f"- **{', '.join(quiet)} answered for nobody.** These "
              "endpoints were read out of vietfin's working code but have "
              "never been reached from a machine that could test them, so "
              "this is their first real trial. Read a zero as the endpoint "
              "or the parameters being wrong, not as the universe having "
              "no prices - yfinance and vnstock below say whether the "
              "prices exist.")
    print()
    return payload

if __name__ == "__main__":
    from services.stock_service import ALL_SYMBOLS_MAP, load_master_universe
    load_master_universe()
    
    symbols_file = os.path.join(DATA_DIR, "all_symbols.json")
    valid_stocks = []
    seen = set()
    if os.path.exists(symbols_file):
        with open(symbols_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
            for r in raw:
                sym = r.get("symbol", "").upper().strip()
                ex = r.get("exchange", "").upper().strip()
                stype = (r.get("type") or "STOCK").upper()
                if len(sym) == 3 and sym.isalpha() and ex in ["HOSE", "HNX", "UPCOM"] and stype in ["STOCK", "CP", "CO_PHIEU", ""]:
                    if sym not in seen:
                        seen.add(sym)
                        valid_stocks.append((sym, ex))

    order = {"HOSE": 1, "HNX": 2, "UPCOM": 3}
    valid_stocks.sort(key=lambda x: order.get(x[1], 99))
    syms = [x[0] for x in valid_stocks]
    
    print(f"📋 Loaded {len(syms)} clean 3-letter stock symbols across HOSE, HNX, UPCOM.")
    # The exchange is known here and TradingView needs it. Passing it turns
    # a three-request guess per symbol into one request.
    sync_all_symbols(syms, max_workers=10,
                     exchanges={sym: ex for sym, ex in valid_stocks})
