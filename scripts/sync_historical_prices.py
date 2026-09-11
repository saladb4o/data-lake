"""Daily prices for the whole universe, quarterised into the price lake.

Two sources, in the order they are tried: DNSE's chart endpoint, then
vnstock per symbol. Each symbol is counted against the source that
actually answered for it, and the tally is printed - because
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

def fetch_stock_raw_candles(symbol: str) -> Optional[pd.DataFrame]:
    """
    Multi-source raw candle fetcher with graceful fallbacks:
    Priority 1: Vietcap (VCI) Data Feed
    Priority 2: KBSV / DNSE Data Feed
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

    return None

#: A listed Vietnamese share trades in dong, and the exchanges enforce a
#: floor: nothing stays listed below 1,000 VND. So a daily series whose
#: typical close sits under this is not a penny stock, it is a series
#: quoted in thousands.
DONG_FLOOR = 1000.0

#: What such a series has to be multiplied by to become dong.
THOUSANDS_TO_DONG = 1000.0


def normalise_to_dong(symbol: str, df: pd.DataFrame) -> Optional[str]:
    """Put one symbol's candles into dong, in place. Returns what it did.

    Run 34605559771 compared every symbol in the lake against the
    screener's own price and found the screener higher by a factor of
    ~941 for **all 1,367 of them** - EVS at 4,800 against a lake close
    of 5.10. DNSE quotes in thousands of dong, and so did the yfinance
    and vnstock path before it, which is why switching vendors moved the
    backtest by 0.01 and looked like confirmation that the scale was
    fine. Two sources wrong the same way cannot check each other.

    It is not a cosmetic difference. `fair_value_backtest_service`
    compares this price *absolutely* against a fair value built from
    dong fundamentals, so a close of 5.10 reads as a ~100% discount on
    every symbol, and the eps/bvps floors at the top of that comparison
    (50 and 500) win against every real figure. That is the reason the
    lag sweep has never moved: the filings were never reaching the
    arithmetic.

    Decided per symbol from the data rather than by multiplying every
    source by a constant. A constant is a claim about a vendor that
    nothing re-checks - the exact shape of the "TradingView" label this
    file used to carry - and it would silently double the prices the day
    a source starts sending dong.
    """
    if df is None or df.empty or "close" not in df.columns:
        return None
    closes = pd.to_numeric(df["close"], errors="coerce").dropna()
    closes = closes[closes > 0]
    if closes.empty:
        return None
    # The median, not the mean or the last bar: a decade of history can
    # contain one bad print, and one bad print must not decide the unit
    # for the whole series.
    if float(closes.median()) >= DONG_FLOOR:
        return "dong"
    for column in ("open", "high", "low", "close"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce") \
                * THOUSANDS_TO_DONG
    return "thousands"


def compute_stock_quarterly_returns(symbol: str, df: pd.DataFrame) -> Dict[str, Any]:
    """Quarterly open/high/low/close/volume and returns from daily candles.

    Whatever unit the source sent, in the same unit out. This docstring used to
    promise that the values were rescaled into VND; the function has
    never rescaled anything, and nothing downstream checks. That matters because
    `fair_value_backtest_service` compares the price here *absolutely*
    against a fair value built from VND fundamentals, so a source quoting
    thousands would silently make every stock look 99.9% undervalued. The
    promise is removed rather than kept, because a scale check belongs
    where the sources are compared, not buried per symbol - and a label
    nobody can check is what put yfinance behind a TradingView banner for
    a year.
    """
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

#: Broker endpoints, in the order they are asked. SSI and TCBS were tried
#: here and removed: run 34570149277 measured both at zero symbols out of
#: their first forty while DNSE answered on the same pass and the same
#: universe. See services/broker_prices.py for why they are deleted
#: rather than kept behind a flag.
BROKER_SOURCES = ("dnse",)

#: How many symbols a broker may fail on before the stage stops asking it.
#: Large enough that a handful of delisted tickers cannot trip it, small
#: enough that a dead endpoint costs a minute rather than half an hour.
PROBE_BEFORE_GIVING_UP = 40


def _fetch_from_broker(source: str, symbol: str) -> Optional[pd.DataFrame]:
    """Daily candles from one broker, shaped like every other fetcher here."""
    from services import broker_prices
    fetch = {"dnse": broker_prices.fetch_dnse}[source]
    rows = fetch(symbol)
    if not rows:
        return None
    return pd.DataFrame(rows)


def sync_all_symbols(symbols_list: List[str], max_workers: int = 10,
                     exchanges: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Syncs real prices for all provided symbols concurrently and saves to JSON.

    Two sources, tried in order, and counted. This used to lead with a
    yfinance batch download and fall back to vnstock per symbol, while
    the file header and the saved payload both claimed "TradingView" -
    which nothing in here touched. The tally at the end says which
    source answered for how many symbols, so the claim can be checked
    rather than asserted; it is what retired SSI, TCBS and yfinance.
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    # vnstock's transitive dependencies log per-request noise of their
    # own. Kept from when yfinance was in this path and buried the one
    # table the stage exists to produce.
    for noisy in ("peewee", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.CRITICAL)

    # exchanges is accepted and unused by the broker sources - both key on
    # the bare ticker - but the master list knows it and a future source
    # that needs a venue would otherwise have to re-derive it.
    exchanges = exchanges or {}
    by_source: Dict[str, int] = {}
    # Which scale each symbol's candles arrived on, counted the same way
    # the sources are. A source that changes units is then a number that
    # moves rather than a backtest that quietly stops using its filings.
    by_unit: Dict[str, int] = {}

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
                unit = normalise_to_dong(sym, df)
                if unit:
                    by_unit[unit] = by_unit.get(unit, 0) + 1
                res = compute_stock_quarterly_returns(sym, df)
                if res and res.get("total_quarters", 0) >= 4:
                    existing_store[sym] = res
                    record(source)
                    answered += 1
        print(f"🌐 {source} answered for {answered} of {len(symbols_to_fetch)} "
              f"in {round(time.time() - started_source, 1)}s")
        symbols_to_fetch = [s for s in symbols_to_fetch if s not in existing_store]
        print(f"📦 Still to fetch after {source}: {len(symbols_to_fetch)}")

    # DNSE answered for 1,364 of the 1,400 symbols on run 34586582908.
    # yfinance was asked for the 36 it missed and answered for none of
    # them, while printing one "possibly delisted" block per ticker; it
    # has never been measured carrying a single symbol of this lake. A
    # source that costs noise and returns nothing is removed, not
    # silenced. vnstock stays as the last resort: it answered for 3.
    BATCH_SIZE = 50
    success_count = 0

    for i in range(0, len(symbols_to_fetch), BATCH_SIZE):
        chunk = symbols_to_fetch[i:i + BATCH_SIZE]

        # Fallback individual fetch for remaining missed symbols in chunk
        for sym in chunk:
            if sym not in existing_store:
                try:
                    df = fetch_stock_raw_candles(sym)
                    if df is not None and len(df) >= 10:
                        unit = normalise_to_dong(sym, df)
                        if unit:
                            by_unit[unit] = by_unit.get(unit, 0) + 1
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
    # Written to a file as well as printed. The job log is not readable
    # from where these results get read - the artifact host is refused and
    # the log API only serves the tail - so a table buried thirty minutes
    # deep in a stage is a table nobody sees. The pass appends this file
    # to the step summary, which is the one channel that always arrives.
    tally: List[str] = []
    tally.append("### Where the prices came from")
    tally.append("")
    tally.append("| price source | symbols it answered for |")
    tally.append("|---|---:|")
    for source, count in sorted(by_source.items(), key=lambda kv: -kv[1]):
        tally.append(f"| {source} | {count:,} |")
    tally.append("")
    tally.append("| scale the candles arrived on | symbols |")
    tally.append("|---|---:|")
    for unit, count in sorted(by_unit.items(), key=lambda kv: -kv[1]):
        tally.append(f"| {unit} | {count:,} |")
    if by_unit.get("thousands"):
        tally.append("")
        tally.append(f"**{by_unit['thousands']:,}** symbols were quoted in "
                     "thousands of dong and multiplied by 1,000 on the way "
                     "in. The backtest compares this price absolutely "
                     "against a fair value built from dong fundamentals, "
                     "so a series left in thousands reads as a ~100% "
                     "discount on every symbol.")
    print()
    for line in tally:
        print(line)
    quiet = [s for s in BROKER_SOURCES if not by_source.get(s)]
    if quiet:
        print()
        print(f"- **{', '.join(quiet)} answered for nobody.** Read a zero "
              "as the endpoint or its parameters being wrong, not as the "
              "universe having no prices: the other rows say whether the "
              "prices exist. A source that stays at zero for a whole pass "
              "should be deleted, not left to spend its forty probe "
              "requests again next time.")
    print()

    summary_path = os.path.join(DATA_DIR, "price_sources.md")
    try:
        with open(summary_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(tally) + "\n")
    except OSError:
        logger.warning("could not write %s", summary_path, exc_info=True)
    return payload

if __name__ == "__main__":
    from services.stock_service import ALL_SYMBOLS_MAP, load_master_universe
    load_master_universe()
    
    symbols_file = os.path.join(DATA_DIR, "all_symbols.json")
    valid_stocks = []
    seen = set()
    # Why each symbol the master list carries was not asked for a price.
    # The universe the valuation engine scores is 1,524 symbols; this
    # filter has been handing the price sync 1,400 of them, and the 124
    # that never get asked have been reported as "no price" ever since -
    # indistinguishable, from every table downstream, from a symbol the
    # sources refused. A rejection nobody can see is a rejection nobody
    # can argue with, so each one is counted under the rule that made it.
    rejected: Dict[str, List[str]] = {}

    def reject(reason: str, sym: str) -> None:
        rejected.setdefault(reason, []).append(sym)

    if os.path.exists(symbols_file):
        with open(symbols_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
            for r in raw:
                sym = r.get("symbol", "").upper().strip()
                ex = r.get("exchange", "").upper().strip()
                stype = (r.get("type") or "STOCK").upper()
                if sym in seen:
                    continue
                if not (len(sym) == 3 and sym.isalpha()):
                    reject("not a 3-letter alphabetic ticker", sym or "(blank)")
                    continue
                if ex not in ("HOSE", "HNX", "UPCOM"):
                    reject(f"exchange {ex or '(blank)'}", sym)
                    continue
                if stype not in ("STOCK", "CP", "CO_PHIEU", ""):
                    reject(f"type {stype}", sym)
                    continue
                seen.add(sym)
                valid_stocks.append((sym, ex))

    order = {"HOSE": 1, "HNX": 2, "UPCOM": 3}
    valid_stocks.sort(key=lambda x: order.get(x[1], 99))
    syms = [x[0] for x in valid_stocks]

    total = len(syms) + sum(len(v) for v in rejected.values())
    lines = ["## Which symbols the price sync is allowed to ask for", "",
             f"- master list: **{total}**",
             f"- asked for a price: **{len(syms)}**",
             f"- filtered out before any fetch: **{total - len(syms)}**", ""]
    if rejected:
        lines += ["| filtered out by | symbols | which |", "|---|---:|---|"]
        for reason, syms_out in sorted(rejected.items(),
                                       key=lambda kv: -len(kv[1])):
            shown = ", ".join(sorted(syms_out)[:40])
            if len(syms_out) > 40:
                shown += f", ... (+{len(syms_out) - 40})"
            lines.append(f"| {reason} | {len(syms_out)} | {shown} |")
        lines.append("")
    print("\n".join(lines))
    try:
        with open(os.path.join(DATA_DIR, "price_universe.md"), "w",
                  encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        logger.warning("could not write price_universe.md", exc_info=True)

    # The exchange is known here and TradingView needs it. Passing it turns
    # a three-request guess per symbol into one request.
    sync_all_symbols(syms, max_workers=10,
                     exchanges={sym: ex for sym, ex in valid_stocks})
