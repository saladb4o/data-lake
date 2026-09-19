#!/usr/bin/env python3
"""Fill the WACC comparables table for one symbol, from measured data.

    scripts/xlsxvas/fill_peers.py SYMBOL TEMPLATE.xlsx OUT.xlsx [--top 10]

Three things go into the table and each comes from somewhere different:

  * who the peers are - the repository's own peer engine, which ranks the
    universe by ICB sector, scale, returns and multiples. Not a list typed
    here, because the right peers depend on the company being valued.
  * the levered beta - ordinary least squares on daily log returns against
    VN-INDEX over a stated window, from the price history the repository
    already fetches. The window, the number of observations and the fit
    are written next to each row, so a beta from forty trading days can be
    told from a beta from a thousand.
  * debt, equity and the tax rate - the fundamentals for each peer.

Anything that cannot be measured is left empty. A blank beta column makes
the model fall back to the beta typed on the Control Panel, which is a
number the user chose; a fabricated beta would be a number nobody chose.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from xlsx_patch import WorkbookPatch            # noqa: E402
import vas_layout as V                          # noqa: E402

WC = "WACC"
CM = V.SHEET_NAMES["Comps"]
SP = V.SHEET_NAMES["Share Price"]
PRICE_FIRST_ROW = 11
PRICE_LAST_ROW = 1374
FIRST_ROW = 10
LAST_ROW = 27
INDEX_SYMBOL = "VNINDEX"
MIN_OBSERVATIONS = 120          # roughly six months of trading days

# The rows the Comps sheet keeps for peers, in five groups.
COMPS_ROWS = (list(range(13, 17)) + list(range(23, 26))
              + list(range(32, 35)) + list(range(41, 45))
              + list(range(51, 55)))

# Units, in one place, because this is where they go wrong. The screener
# quotes a market capitalisation in ty dong and a reference price the way
# a board does, in thousands of dong. The workbook wants dong per share
# and millions of shares.
#
#   shares (million) = cap (ty dong) * 1e9 / (price_thousands * 1e3) / 1e6
#                    = cap / price_thousands
#
# ACB is the check: 115,000 ty dong at 25.6 gives 4,492 million shares,
# against the 4.47 billion it has in issue.
PRICE_THOUSANDS_TO_DONG = 1000.0


def price_in_dong(reference: float) -> float:
    return reference * PRICE_THOUSANDS_TO_DONG


def shares_in_millions(market_cap_ty: float, reference: float):
    """None rather than a number when either side is missing or zero."""
    if not market_cap_ty or not reference:
        return None
    return market_cap_ty / reference


def log_returns(closes: Sequence[float]) -> List[float]:
    out = []
    for prev, now in zip(closes, closes[1:]):
        if prev and now and prev > 0 and now > 0:
            out.append(math.log(now / prev))
        else:
            out.append(float("nan"))
    return out


def ols_beta(stock: Sequence[float],
             index: Sequence[float]) -> Optional[Tuple[float, int, float]]:
    """Slope of stock returns on index returns, with n and R-squared.

    Pairs where either side is missing are dropped rather than zero-filled:
    a zero return on a day the stock did not trade is not an observation,
    it is an assumption that the price did not move.
    """
    pairs = [(x, y) for x, y in zip(index, stock)
             if not (math.isnan(x) or math.isnan(y))]
    n = len(pairs)
    if n < MIN_OBSERVATIONS:
        return None
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    if sxx <= 0:
        return None
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    beta = sxy / sxx
    syy = sum((p[1] - my) ** 2 for p in pairs)
    r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else 0.0
    return beta, n, r2


def closes_by_date(history: Dict) -> Dict[str, float]:
    """Pull {date: close} out of whatever shape the history call returns."""
    candles = history.get("candles") or history.get("data") or []
    out: Dict[str, float] = {}
    for c in candles:
        if isinstance(c, dict):
            day = c.get("time") or c.get("date") or c.get("t")
            close = c.get("close") or c.get("c")
        elif isinstance(c, (list, tuple)) and len(c) >= 5:
            day, close = c[0], c[4]
        else:
            continue
        if day is None or close is None:
            continue
        try:
            out[str(day)[:10]] = float(close)
        except (TypeError, ValueError):
            continue
    return out


def aligned(stock: Dict[str, float],
            index: Dict[str, float]) -> Tuple[List[float], List[float]]:
    """Line the two series up on the days both actually traded."""
    days = sorted(set(stock) & set(index))
    return [stock[d] for d in days], [index[d] for d in days]


def beta_for(symbol: str, index_closes: Dict[str, float],
             fetch) -> Optional[Tuple[float, int, float]]:
    closes = closes_by_date(fetch(symbol) or {})
    if not closes:
        return None
    s, i = aligned(closes, index_closes)
    if len(s) < MIN_OBSERVATIONS + 1:
        return None
    return ols_beta(log_returns(s), log_returns(i))


def price_history(symbol: str, fetch) -> List[Tuple[str, float]]:
    """The subject company's own daily closes, oldest first.

    The Share Price sheet takes its 52-week high, low and average off
    this column, and Implied Value Summary takes a valuation band off
    those three. With the column empty they were MAX and MIN of nothing,
    which answer zero, and the summary reported an implied enterprise
    value of minus the net debt.
    """
    closes = closes_by_date(fetch(symbol) or {})
    return sorted(closes.items())


def collect(symbol: str, top_k: int) -> Tuple[List[Dict], List[str]]:
    """Gather the peer set and everything measurable about it."""
    from services.stock_service import get_company_peers, get_stock_history

    def fetch(sym: str):
        return get_stock_history(sym, interval="1D", timeframe="ALL")

    notes: List[str] = []
    index_closes = closes_by_date(fetch(INDEX_SYMBOL) or {})
    if not index_closes:
        notes.append(f"không lấy được lịch sử giá {INDEX_SYMBOL}")

    own = price_history(symbol, fetch)
    if not own:
        notes.append(f"không lấy được lịch sử giá {symbol}")

    found = get_company_peers(symbol, top_k=top_k)
    rows = []
    for p in found.get("peers", []):
        sym = p.get("symbol")
        if not sym:
            continue
        measured = beta_for(sym, index_closes, fetch) if index_closes else None
        cap = p.get("market_cap")
        ref = p.get("price")
        rows.append({
            "symbol": sym,
            "name": p.get("name") or "",
            "exchange": p.get("exchange") or "",
            "price": price_in_dong(ref) if ref else None,
            "shares": shares_in_millions(cap, ref),
            "beta": measured[0] if measured else None,
            "n": measured[1] if measured else 0,
            "r2": measured[2] if measured else None,
        })
    if not rows:
        notes.append(f"bộ máy so sánh không trả về mã nào cho {symbol}")
    without = [r["symbol"] for r in rows if r["beta"] is None]
    if without:
        notes.append("chưa đo được beta: " + ", ".join(without))
    return rows, notes, own


def write(src: str, dest: str, symbol: str, rows: List[Dict],
          notes: List[str], own: List[Tuple[str, float]]) -> None:
    w = WorkbookPatch(src)
    # the last 1,364 trading days the sheet has room for, oldest first, so
    # the 52-week window at the bottom of the column is the recent one
    room = PRICE_LAST_ROW - PRICE_FIRST_ROW + 1
    tail = own[-room:]
    for offset in range(room):
        row = PRICE_FIRST_ROW + offset
        if offset < len(tail):
            day, close = tail[offset]
            w.set_value(SP, f"B{row}", day)
            w.set_value(SP, f"C{row}", close)
        else:
            w.set_value(SP, f"B{row}", None)
            w.set_value(SP, f"C{row}", None)
    for offset in range(LAST_ROW - FIRST_ROW + 1):
        row = FIRST_ROW + offset
        if offset >= len(rows):
            for col in "BCDEFIJ":
                w.set_value(WC, f"{col}{row}", None)
            continue
        r = rows[offset]
        w.set_value(WC, f"B{row}", r["symbol"])
        w.set_value(WC, f"C{row}", r["name"])
        w.set_value(WC, f"D{row}", r["exchange"])
        w.set_value(WC, f"J{row}", round(r["beta"], 4)
                    if r["beta"] is not None else None)
    # the same peer set, on the sheet that takes multiples off it
    priced = [r for r in rows if r.get("price") and r.get("shares")]
    for slot, row in enumerate(COMPS_ROWS):
        if slot >= len(rows):
            for col in ("B", "D", "E"):
                w.set_value(CM, f"{col}{row}", None)
            continue
        r = rows[slot]
        w.set_value(CM, f"B{row}", f"{r['symbol']} - {r['name']}"[:60])
        w.set_value(CM, f"D{row}", round(r["price"], 0)
                    if r.get("price") else None)
        w.set_value(CM, f"E{row}", round(r["shares"], 2)
                    if r.get("shares") else None)
    w.set_value(CM, "B62",
                f"Nguồn: bộ máy so sánh của kho, {len(priced)}/{len(rows)} "
                f"mã có giá và số cổ phiếu. Nợ vay, tiền và số liệu dự "
                f"phóng của từng mã vẫn phải nhập tay.")

    measured = [r for r in rows if r["beta"] is not None]
    stamp = (f"Nguồn: bộ máy so sánh + lịch sử giá của kho, hồi quy lợi suất "
             f"log ngày trên {INDEX_SYMBOL}. "
             f"Đo được {len(measured)}/{len(rows)} mã.")
    w.set_value(WC, "C32", stamp)
    if notes:
        w.set_value(WC, "C33", " | ".join(notes)[:250])
    w.set_value(WC, "C31", f"Ghi chú ({symbol}):")
    w.save(dest)
    print(f"{symbol}: {len(rows)} mã so sánh, {len(measured)} có beta, "
          f"{len(tail)} phiên giá -> {dest}")
    for note in notes:
        print(f"  ! {note}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("symbol")
    ap.add_argument("src")
    ap.add_argument("dest")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args(argv)
    rows, notes, own = collect(args.symbol.upper(), args.top)
    write(args.src, args.dest, args.symbol.upper(), rows, notes, own)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
