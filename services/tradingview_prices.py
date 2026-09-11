"""Daily candles from TradingView, fetched once for the whole universe.

Every other source in this path answers an HTTPS request per symbol.
TradingView does not: candles arrive on a WebSocket chart session, and
the library that speaks that protocol is a Node one. So the fetch is a
single subprocess over the whole symbol list, cached in memory, and
`fetch_tradingview` then reads a symbol out of that cache with the same
shape every other fetcher here has.

Two things this deliberately does not do.

It does not disable TLS verification. `scripts/fetch_tradingview.js`
opened with `NODE_TLS_REJECT_UNAUTHORIZED = '0'`, which switches off
certificate checking for the entire Node process, every connection it
makes, for the life of the run. That file has never been reachable -
the repo carried no package.json, so the dependency it imports was
never installed - which is the only reason it did no harm.

It does not claim TradingView carries the lake. This path's own header
used to say "TRADINGVIEW & VCI DATA FEEDS" while the code reached for
neither, and that label was read for months as evidence. Whether
TradingView answers is decided by the tally the sync prints, on the
run, per symbol.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "tradingview_candles.js")

#: Answers from the last batch, by symbol. Cleared at the start of each
#: prefetch so a previous run's results can never be read as this run's -
#: the same carryover shape that let the price lake keep the thousands
#: scale across reruns.
_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_PREFETCHED = False

#: Seconds the batch may run before it is killed. 1,400 symbols at eight
#: at a time and about a second each is a few minutes; the ceiling is for
#: the case where the socket hangs rather than refuses.
TIMEOUT_SECONDS = 1800


def available() -> bool:
    """Whether the batch can run at all.

    Node and the installed dependency, both checked rather than assumed.
    A missing dependency would otherwise surface as every symbol failing,
    which reads as "TradingView has no Vietnamese tickers" - a claim
    about the vendor drawn from a fact about the machine.
    """
    if shutil.which("node") is None:
        return False
    return os.path.isdir(os.path.join(PROJECT_ROOT, "node_modules",
                                      "@mathieuc", "tradingview"))


def prefetch(symbols: List[str],
             exchanges: Optional[Dict[str, str]] = None) -> int:
    """Run the batch once and hold its answers in memory.

    Returns the number of symbols TradingView answered for. Zero is a
    result, not an error: the caller prints it and moves to the next
    source.
    """
    global _PREFETCHED
    _PREFETCHED = True
    _CACHE.clear()

    if not symbols:
        return 0
    if not available():
        print("⚠️  TradingView needs node and @mathieuc/tradingview; one of "
              "them is missing, so it is skipped rather than counted as "
              "answering for nobody.")
        return 0

    exchanges = exchanges or {}
    requests = [{"symbol": sym, "exchange": exchanges.get(sym, "HOSE")}
                for sym in symbols]

    workdir = tempfile.mkdtemp(prefix="tradingview_")
    req_path = os.path.join(workdir, "requests.json")
    out_path = os.path.join(workdir, "candles.jsonl")
    try:
        with open(req_path, "w", encoding="utf-8") as handle:
            json.dump(requests, handle)

        try:
            proc = subprocess.run(
                ["node", NODE_SCRIPT, req_path, out_path],
                cwd=PROJECT_ROOT, timeout=TIMEOUT_SECONDS,
                capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            print(f"⚠️  TradingView batch exceeded {TIMEOUT_SECONDS}s and was "
                  "killed. Whatever it had written is still read below.")
            proc = None

        if proc is not None and proc.stderr.strip():
            # The node side reports its own tally on stderr.
            for line in proc.stderr.strip().splitlines()[-5:]:
                print(f"   {line}")

        if not os.path.exists(out_path):
            return 0

        failures: Dict[str, int] = {}
        with open(out_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("ok") and row.get("candles"):
                    _CACHE[row["symbol"]] = row["candles"]
                else:
                    reason = str(row.get("error", "no candles"))[:60]
                    failures[reason] = failures.get(reason, 0) + 1

        if failures:
            # Why it refused, not just how often. A timeout and an
            # unknown symbol are different faults with different fixes,
            # and collapsing them into one count hides which one this is.
            for reason, count in sorted(failures.items(),
                                        key=lambda kv: -kv[1])[:3]:
                print(f"   ↳ {count:,} symbols: {reason}")

        return len(_CACHE)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def fetch_tradingview(symbol: str) -> Optional[List[Dict[str, Any]]]:
    """Candles for one symbol, from the batch that already ran."""
    if not _PREFETCHED:
        logger.debug("fetch_tradingview called before prefetch; no candles")
        return None
    return _CACHE.get(symbol)
