#!/usr/bin/env python3
"""Which of the candidate item codes is really capex, judged by a vendor
that names its lines.

The problem this closes
-----------------------
VNDIRECT's quarterly statement endpoint sends eight keys per row and not
one of them is a label: a full key census across 1,380 symbols found
code, itemCode, reportType, modelType, numericValue, fiscalDate,
createdDate and modifiedDate, and nothing else. So the extractor reads
capex from item code 32100 on the strength of the VAS numbering
convention alone, and the capex score against its anchor has been 0.3%
for three runs running - arithmetic with nothing to check it against.

capex is not a small gap. `fcf` resolves as cfo - |capex| and otherwise
imputes as cfo * 0.7, and an impute sits below the provenance gate, so
capex below the gate blocks fcf outright. Run 34616175758 measured cfo
present at tier 3 for 1,514 of 1,524 symbols while capex sits below the
gate for 193 - and fcf is the third most common blocking driver in the
universe at 141 symbols. Nothing else in the refusal table is one
correctly-identified item code away from being fixed.

What this does
--------------
Vietcap's financial-statement endpoint returns the cash flow statement
with each line under a named field, and its metrics endpoint supplies
the Vietnamese and English titles for those names. That is the witness
VNDIRECT will not provide. For each symbol this takes Vietcap's own
capital-expenditure line and asks which of the candidate VNDIRECT codes
already recorded in the diagnostics probe reproduces it.

It is a match count, not a proof: two vendors can copy the same mistake,
and a company whose capex is genuinely zero matches every code that is
also zero. So zero-on-both quarters are counted separately and never
credited, and the result is reported as a rate over symbols that had a
non-zero figure on both sides.

Reads the probe file and the network. Writes no valuation input.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: How close two vendors' figures have to be to count as the same line.
#: Wide enough for a rounding or unit-of-thousands difference at the
#: last digit, narrow enough that two different lines of a cash flow
#: statement do not land on each other by accident.
AGREE_WITHIN = 0.01

#: Words a capital-expenditure line carries in Vietcap's own titles.
#: Matched against the Vietnamese and English titles rather than against
#: the field name, because the field names are camel-cased vendor
#: shorthand and the titles are what a person can check.
CAPEX_TITLE_HINTS = (
    "mua sam", "mua sắm", "tai san co dinh", "tài sản cố định",
    "xay dung co ban", "xây dựng cơ bản",
    "purchase of fixed", "capital expenditure", "acquisition of fixed",
)


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def _f(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def _agree(left: float, right: float) -> bool:
    """Same magnitude, either sign.

    Sign is deliberately ignored. A cash flow statement may carry a
    purchase of fixed assets as a negative outflow or as a positive
    amount in an outflow section, and the two vendors need not have
    chosen the same convention - which is a presentation difference,
    not a different number.
    """
    scale = max(abs(left), abs(right), 1.0)
    return abs(abs(left) - abs(right)) / scale <= AGREE_WITHIN


def candidate_codes(probe: Dict[str, Any]) -> List[str]:
    """The capex candidates the diagnostics probe already recorded."""
    seen = set()
    for quarters in probe.values():
        if not isinstance(quarters, dict):
            continue
        for row in quarters.values():
            if isinstance(row, dict):
                seen.update(k for k in row if k.startswith("capex_"))
    return sorted(seen)


def vietcap_capex_by_quarter(symbol: str, cookies: Dict[str, str],
                             field: Optional[str] = None
                             ) -> Tuple[Dict[str, float], Optional[str]]:
    """Vietcap's capital-expenditure line, keyed the way the probe is.

    Returns ({quarter_code: value}, the field name it used). The field is
    returned so the caller can report which line it actually compared
    against - a match rate against an unnamed line would be the same
    unlabelled number this script exists to replace.
    """
    from scripts.vendor_census import _get_json, VIETCAP_BASE

    status, body = _get_json(f"{VIETCAP_BASE}/{symbol}/financial-statement",
                             params={"section": "CASH_FLOW"}, cookies=cookies)
    if status != 200 or not isinstance(body, dict):
        return {}, None
    data = body.get("data")
    if not isinstance(data, dict):
        return {}, None
    rows = data.get("quarters")
    if not isinstance(rows, list) or not rows:
        return {}, None

    out: Dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        year, quarter = _f(row.get("year")), _f(row.get("quarter"))
        if year is None or quarter is None:
            continue
        value = _f(row.get(field)) if field else None
        if value is None:
            continue
        out[f"{int(year)}-Q{int(quarter)}"] = value
    return out, field


def name_the_capex_field(cookies: Dict[str, str]) -> Optional[str]:
    """The field Vietcap files capital expenditure under, from its own titles.

    Asked once and reused: the chart of accounts differs between a bank
    and a manufacturer, but the cash-flow line for buying fixed assets
    does not, and asking per symbol would be 1,500 requests to learn one
    string.
    """
    from scripts.vendor_census import _get_json, VIETCAP_BASE

    for reference in ("FPT", "HPG", "VNM"):
        status, body = _get_json(
            f"{VIETCAP_BASE}/{reference}/financial-statement/metrics",
            cookies=cookies)
        if status != 200 or not isinstance(body, dict):
            continue
        data = body.get("data")
        if not isinstance(data, dict):
            continue
        for fields in data.values():
            if not isinstance(fields, list):
                continue
            for entry in fields:
                if not isinstance(entry, dict):
                    continue
                titles = " ".join(_norm(entry.get(k)) for k in
                                  ("titleVi", "fullTitleVi",
                                   "titleEn", "fullTitleEn"))
                if any(hint in titles for hint in CAPEX_TITLE_HINTS):
                    name = str(entry.get("field") or "").strip()
                    if name:
                        print(f"- Vietcap files it under `{name}` "
                              f"(\"{_norm(entry.get('titleVi')) or _norm(entry.get('titleEn'))}\"), "
                              f"found on {reference}")
                        return name
    return None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", default="data/code_candidates_probe.json",
                        help="The diagnostics probe a lake build wrote.")
    parser.add_argument("--limit", type=int, default=200,
                        help="How many symbols to ask Vietcap about.")
    parser.add_argument("--json", default="", help="Where to write the result.")
    args = parser.parse_args(argv)

    print("# Which item code is capex, according to a vendor that names it")
    print()

    if not os.path.exists(args.probe):
        print(f"- no probe at `{args.probe}`: a lake build writes it. "
              "Nothing to match against.")
        return 1
    with open(args.probe, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    probe = payload.get("symbols", payload)
    if not isinstance(probe, dict) or not probe:
        print(f"- `{args.probe}` carries no per-symbol rows.")
        return 1

    codes = candidate_codes(probe)
    if not codes:
        print("- the probe recorded no `capex_*` candidates, so there is "
              "nothing to choose between. The probe's columns come from "
              "VNDIRECT_ITEM_CODES['capex']; if that list is empty the "
              "extractor is not reading capex from anywhere.")
        return 1
    print(f"- candidate codes in the probe: {', '.join(codes)}")

    from scripts.vendor_census import _handshake_cookies
    cookies = _handshake_cookies()
    print(f"- handshake returned {len(cookies)} cookies")

    field = name_the_capex_field(cookies)
    if not field:
        print("- **Vietcap named no capital-expenditure line.** Every title "
              "on its metrics endpoint was searched for the words a capex "
              "line carries and none matched, so there is no witness here "
              "and the code stays unconfirmed. That is a fact about the "
              "endpoint, not a failure to find one - the next place to "
              "look is a vendor that publishes a chart of accounts.")
        return 1

    symbols = sorted(probe)[:max(1, args.limit)]
    print(f"- asking Vietcap for {len(symbols):,} symbols")
    print()

    hits: Dict[str, int] = {code: 0 for code in codes}
    compared: Dict[str, int] = {code: 0 for code in codes}
    both_zero = 0
    answered = 0

    for symbol in symbols:
        vietcap, _ = vietcap_capex_by_quarter(symbol, cookies, field)
        if not vietcap:
            continue
        answered += 1
        quarters = probe.get(symbol) or {}
        for quarter, row in quarters.items():
            if not isinstance(row, dict):
                continue
            theirs = vietcap.get(quarter)
            if theirs is None:
                continue
            for code in codes:
                ours = _f(row.get(code))
                if ours is None:
                    continue
                if abs(ours) < 1.0 and abs(theirs) < 1.0:
                    both_zero += 1
                    continue
                compared[code] += 1
                if _agree(ours, theirs):
                    hits[code] += 1

    print(f"- Vietcap answered for **{answered:,}** of {len(symbols):,}")
    print(f"- quarters where both sides were zero, and so prove nothing: "
          f"**{both_zero:,}**")
    print()
    print("| candidate code | quarters compared | matched | rate |")
    print("|---|---:|---:|---:|")
    ranked = sorted(codes, key=lambda c: -(hits[c] / max(compared[c], 1)))
    for code in ranked:
        n = compared[code]
        rate = f"{hits[code] / n:.1%}" if n else "-"
        print(f"| `{code}` | {n:,} | {hits[code]:,} | {rate} |")
    print()

    best = ranked[0] if ranked else None
    if best and compared[best] >= 50 and hits[best] / compared[best] >= 0.80:
        print(f"- **`{best}` is capex.** It reproduces Vietcap's "
              f"`{field}` on {hits[best]:,} of {compared[best]:,} quarters. "
              "That is a second vendor agreeing on a figure it names, "
              "which is what the extractor has never had.")
    elif best and compared[best]:
        print(f"- **No candidate is confirmed.** The best, `{best}`, "
              f"matches {hits[best] / compared[best]:.1%} of "
              f"{compared[best]:,} quarters. Below agreement this weak the "
              "two vendors are not reading the same line, and which of "
              "them is right is a further question - do not promote a "
              "code on this.")
    else:
        print("- **Nothing was compared.** Vietcap answered but no quarter "
              "lined up with the probe's, so the two are keyed differently "
              "and the comparison has not happened.")

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({"vietcap_field": field, "symbols_answered": answered,
                       "both_zero": both_zero, "hits": hits,
                       "compared": compared}, handle, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
