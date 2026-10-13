"""The crawler reads statements from CafeF's document index, not its news feed.

Run 38384954007 crawled every shard in under two minutes and kept nothing:
the news feed get_company_reports scrapes lists announcements *about*
statements, so every company came back with 0 filings. These tests pin what
the index helper keeps and that the processor asks it first.
"""
import io
import json
from unittest.mock import patch

from services import stock_service
from services import bctc_batch_processor


def _row(year, quarter, name, link=None):
    return {"Year": year, "Quarter": quarter, "Time": f"{'CN' if quarter == 5 else 'Q%d' % quarter}/{year}",
            "Name": name, "Link": link or f"https://cdn.example/{year}_{quarter}_{abs(hash(name))}.pdf?v=1"}


INDEX = {"Success": True, "Data": [
    _row(2026, 2, "Báo cáo tài chính công ty mẹ quý 2 năm 2026"),
    _row(2026, 2, "Báo cáo tài chính hợp nhất quý 2 năm 2026"),
    _row(2026, 2, "Báo cáo tài chính hợp nhất quý 2 năm 2026 (đã soát xét)"),
    _row(2025, 5, "Báo cáo tài chính công ty mẹ năm 2025 (đã kiểm toán)"),
    _row(2025, 5, "Báo cáo tài chính hợp nhất năm 2025 (đã kiểm toán)"),
    _row(2025, 4, "Báo cáo tài chính quý 4 năm 2025"),
    _row(2025, 3, "Bản điều lệ", link="https://cdn.example/charter.doc"),
]}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _serve(payload):
    return patch.object(stock_service.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(json.dumps(payload).encode("utf-8")))


def test_one_filing_per_period_consolidated_and_audited_first_newest_first():
    with _serve(INDEX):
        got = stock_service.fetch_cafef_bctc_filings("fpt")
    assert [r["date"] for r in got] == ["Q2/2026", "CN/2025", "Q4/2025"]
    assert got[0]["title"].endswith("(đã soát xét)") and "hợp nhất" in got[0]["title"]
    assert "hợp nhất" in got[1]["title"] and got[1]["quarter"] is None
    assert all(r["pdf_url"] and r["symbol"] == "FPT" and r["type_code"] == "bctc" for r in got)


def test_annual_only_keeps_the_full_year_filings():
    with _serve(INDEX):
        got = stock_service.fetch_cafef_bctc_filings("FPT", annual_only=True)
    assert [r["date"] for r in got] == ["CN/2025"]


def test_an_unreachable_index_is_an_empty_list_not_an_error():
    def boom(*a, **k):
        raise OSError("down")
    with patch.object(stock_service.urllib.request, "urlopen", boom):
        assert stock_service.fetch_cafef_bctc_filings("FPT") == []


def test_listed_symbols_leave_out_otc():
    rows = {"Data": [{"Symbol": "FPT", "TradeCenterId": 1}, {"Symbol": "SHS", "TradeCenterId": 2},
                     {"Symbol": "ABB", "TradeCenterId": 9}, {"Symbol": "24H", "TradeCenterId": 8}]}
    with _serve(rows):
        assert stock_service.fetch_cafef_listed_symbols() == ["ABB", "FPT", "SHS"]


def test_processor_asks_the_index_before_the_news_feed():
    filings = [{"title": "Báo cáo tài chính hợp nhất quý 2 năm 2026", "pdf_url": "https://cdn.example/a.pdf",
                "year": "2026", "fiscal_year": "2026", "quarter": 2, "date": "Q2/2026", "type_code": "bctc"},
               {"title": "Báo cáo tài chính hợp nhất năm 2025", "pdf_url": "https://cdn.example/b.pdf",
                "year": "2025", "fiscal_year": "2025", "quarter": None, "date": "CN/2025", "type_code": "bctc"}]
    asked = []
    proc = bctc_batch_processor.BCTCBatchProcessor()
    with patch.object(bctc_batch_processor, "fetch_cafef_bctc_filings", lambda s: filings), \
         patch.object(bctc_batch_processor, "get_company_reports", side_effect=AssertionError("news feed asked")), \
         patch.object(proc, "discover_10y_annual_reports", side_effect=AssertionError("feed scan asked")), \
         patch.object(bctc_batch_processor, "_get_lake_data", lambda: {}), \
         patch.object(bctc_batch_processor, "_save_lake_data", lambda *a, **k: None), \
         patch.object(proc, "download_report_pdf", lambda sym, url, *a, **k: asked.append(url)):
        proc.process_single_company(symbol="FPT", max_reports=1, fetch_10y_annual=True)
    assert asked == ["https://cdn.example/b.pdf", "https://cdn.example/a.pdf"]
