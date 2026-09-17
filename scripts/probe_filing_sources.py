"""Ask several document sources, not one endpoint, whether they list BCTC.

Runs 34644785546 and 35218315632 established something narrower than it
sounded: CafeF's Events_RelatedNews_New.aspx carries news, and its Type
parameter is decorative - seven ids returned byte-identical answers. That
is one endpoint. It is not CafeF, and it is certainly not "there are no
filings", which would be absurd: every listed company files quarterly and
those documents are public.

So this asks the wider question the narrow result does not answer. Each
candidate URL is fetched once and reported the same way: HTTP status, how
many bytes came back, how many links end in .pdf, and the anchor texts
that look like a financial statement rather than a document about one.
Nothing is parsed and nothing is downloaded - the question here is only
which door has statements behind it.

Every source is reported even when it fails, and a failure is printed as
what it was - a status code, a timeout, a refusal - because the one error
this repo keeps repeating is reading a fact about the fetch as a fact
about the vendor.
"""

from __future__ import annotations

import argparse
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

#: Where a filing might be listed. CafeF first because the app already
#: speaks to it, then the two exchanges, which are the primary publishers
#: and answer to nobody's editorial calendar, then Vietstock.
def candidates(symbol: str) -> List[Dict[str, str]]:
    s = symbol.upper()
    return [
        {"name": "cafef tin-doanh-nghiep",
         "url": f"https://s.cafef.vn/tin-doanh-nghiep/{s}/Event.chn"},
        {"name": "cafef bao-cao-tai-chinh",
         "url": f"https://s.cafef.vn/bao-cao-tai-chinh/{s}/BSheet.chn"},
        {"name": "cafef ajax bctc",
         "url": ("https://cafef.vn/du-lieu/Ajax/CongTy/BaoCaoTaiChinh.aspx"
                 f"?sym={s}&type=BSheet&year=2025&quarter=0")},
        {"name": "cafef ajax disclosures",
         "url": ("https://cafef.vn/du-lieu/Ajax/Events_RelatedNews_New.aspx"
                 f"?symbol={s}&floorID=0&configID=0&PageIndex=1&PageSize=30&Type=2")},
        {"name": "vietstock tai-tai-lieu",
         "url": f"https://finance.vietstock.vn/{s}/tai-tai-lieu.htm"},
        {"name": "vietstock ho-so",
         "url": f"https://finance.vietstock.vn/{s}/ho-so-doanh-nghiep.htm"},
        {"name": "hsx disclosures",
         "url": ("https://www.hsx.vn/Modules/Listed/Web/SymbolNews/"
                 f"?fid=&symbol={s}")},
        {"name": "hnx disclosures",
         "url": f"https://www.hnx.vn/vi-vn/cophieu-etfs/chung-khoan-ny-{s}.html"},
    ]

#: A title that is the statement, not an announcement about one. Kept in
#: step with fetch_one_symbols_filings.py, which learned this list the
#: hard way: "bctc nam" alone matched "ky hop dong kiem toan BCTC nam".
DISQUALIFIERS = ("hop dong", "ky ket", "lua chon", "nghi quyet", "giai trinh",
                 "thong bao ve viec", "quyet dinh", "bo nhiem")
HINTS = ("bao cao tai chinh", "bctc", "bao cao soat xet", "bang can doi ke toan",
         "luu chuyen tien te", "ket qua hoat dong kinh doanh")


def _fold(text: str) -> str:
    from services.bctc_pdf_parser import strip_accents
    return strip_accents(str(text or "")).lower()


def is_statement_title(text: str) -> bool:
    folded = _fold(text)
    if any(_fold(w) in folded for w in DISQUALIFIERS):
        return False
    return any(_fold(h) in folded for h in HINTS)


def probe(url: str, timeout: float = 15.0) -> Dict[str, Any]:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://cafef.vn/",
        "Accept": "text/html,application/xhtml+xml,application/json,*/*",
    })
    out: Dict[str, Any] = {"url": url}
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            out["status"] = resp.status
    except urllib.error.HTTPError as exc:
        out["status"] = exc.code
        out["error"] = f"HTTP {exc.code}"
        return out
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
        return out

    out["bytes"] = len(body)
    out["pdf_links"] = len(re.findall(r'href=["\'][^"\']+\.pdf', body, re.I))
    anchors = re.findall(r"<a[^>]*>(.*?)</a>", body, re.DOTALL | re.I)
    texts = [re.sub(r"<[^>]+>", "", a).strip() for a in anchors]
    texts = [t for t in texts if t]
    out["anchors"] = len(texts)
    out["statement_titles"] = [t for t in texts if is_statement_title(t)][:12]
    # Plain text hits too: some listings render titles outside anchors.
    stripped = re.sub(r"<[^>]+>", " ", body)
    out["bctc_mentions"] = len(re.findall(r"báo cáo tài chính|BCTC",
                                          stripped, re.I))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    args = ap.parse_args(argv)
    symbol = args.symbol.upper().strip()

    print(f"# Where {symbol}'s filings might be listed")
    print()
    print("| source | status | bytes | .pdf links | says BCTC | statement titles |")
    print("|---|---|---:|---:|---:|---:|")

    results = []
    for cand in candidates(symbol):
        res = probe(cand["url"])
        res["name"] = cand["name"]
        results.append(res)
        if "error" in res:
            print(f"| {cand['name']} | {res['error']} | | | | |")
            continue
        print(f"| {cand['name']} | {res['status']} | {res['bytes']:,} | "
              f"{res['pdf_links']} | {res['bctc_mentions']} | "
              f"**{len(res['statement_titles'])}** |")
    print()

    for res in results:
        titles = res.get("statement_titles") or []
        if not titles:
            continue
        print(f"## {res['name']}")
        print()
        for title in titles:
            print(f"  - {title[:100]}")
        print()

    if not any(r.get("statement_titles") for r in results):
        print("- **No source listed a statement.** Read the status column "
              "before the conclusion: a row that errored was never asked.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
