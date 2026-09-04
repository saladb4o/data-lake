"""
=============================================================================
BCTC BATCH PROCESSOR & DATA LAKE PIPELINE
=============================================================================
Orchestrates large-scale asynchronous downloading and parsing of corporate
financial reports (BCTC) across HOSE, HNX, and UPCOM.

Persists extracted artifacts to:
  - `data/pdf_lake/{symbol}/` (Raw PDF archive)
  - `data/pdf_lake/extracted_bctc_lake.json` (Structured JSON L2 Cache)
"""

import os
import re
import json
import time
import logging
import urllib.request
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.stock_service import get_company_reports, resolve_data_file
from services.bctc_pdf_parser import BCTCPdfParser

logger = logging.getLogger(__name__)

PDF_LAKE_DIR = os.path.join(os.path.dirname(resolve_data_file("screener_snapshot.json")), "pdf_lake")
os.makedirs(PDF_LAKE_DIR, exist_ok=True)
EXTRACTED_LAKE_FILE = os.path.join(PDF_LAKE_DIR, "extracted_bctc_lake.json")
CORPORATE_ACTIONS_LAKE_FILE = os.path.join(PDF_LAKE_DIR, "extracted_corporate_actions.json")


_lake_cache_mem: Dict[str, Any] = {}
_lake_cache_mtime: float = 0.0
_corp_cache_mem: Dict[str, Any] = {}
_corp_cache_mtime: float = 0.0


def _resolve_lake_file(filename: str) -> str:
    """Resolves lake files across Google Drive (synced from Colab) and local data/ directory."""
    candidate = resolve_data_file(os.path.join("pdf_lake", filename))
    if os.path.exists(candidate):
        return candidate
    return os.path.join(PDF_LAKE_DIR, filename)


def _merge_shards_if_present(data: Dict[str, Any]) -> Dict[str, Any]:
    """Scans for bctc_shard_*.json produced by distributed Colab workers and merges them into lake data."""
    search_dirs = []
    gdrive_dir = os.getenv("GOOGLE_DRIVE_DATA_DIR", "G:/My Drive/vnstock_data")
    if gdrive_dir and os.path.isdir(os.path.join(gdrive_dir, "pdf_lake")):
        search_dirs.append(os.path.join(gdrive_dir, "pdf_lake"))
    if os.path.isdir(PDF_LAKE_DIR) and PDF_LAKE_DIR not in search_dirs:
        search_dirs.append(PDF_LAKE_DIR)
        
    merged_count = 0
    for sdir in search_dirs:
        try:
            for fname in os.listdir(sdir):
                if re.match(r"^bctc_shard_\d+\.json$", fname):
                    fpath = os.path.join(sdir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            shard_data = json.load(f)
                        if isinstance(shard_data, dict):
                            for sym, sym_info in shard_data.items():
                                existing_sym = data.get(sym, {})
                                existing_periods = len(existing_sym.get("periods", [])) if isinstance(existing_sym, dict) else 0
                                new_periods = len(sym_info.get("periods", [])) if isinstance(sym_info, dict) else 0
                                if sym not in data or new_periods >= existing_periods:
                                    data[sym] = sym_info
                                    merged_count += 1
                    except Exception as err:
                        logger.warning(f"Failed to read shard {fpath}: {err}")
        except Exception:
            pass
            
    if merged_count > 0:
        logger.info(f"Auto-merged {merged_count} symbols from Colab shards into BCTC lake")
        _save_lake_data(data)
    return data


def _get_lake_data() -> Dict[str, Any]:
    """Reads L2 persistent extracted lake cache with in-memory mtime caching, Google Colab Drive sync, and shard auto-merging."""
    global _lake_cache_mem, _lake_cache_mtime
    file_path = _resolve_lake_file("extracted_bctc_lake.json")
    data = {}
    if os.path.exists(file_path):
        try:
            mtime = os.path.getmtime(file_path)
            if _lake_cache_mem and _lake_cache_mtime == mtime:
                return _lake_cache_mem
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _lake_cache_mem = data
            _lake_cache_mtime = mtime
        except Exception:
            data = _lake_cache_mem or {}
    
    # Check if any new shards from Colab workers arrived
    data = _merge_shards_if_present(data)
    _lake_cache_mem = data
    return data


def _save_lake_data(data: Dict[str, Any]) -> None:
    """Saves to L2 persistent extracted lake cache atomically."""
    global _lake_cache_mem, _lake_cache_mtime
    try:
        tmp_file = EXTRACTED_LAKE_FILE + f".tmp_{os.getpid()}_{int(time.time()*1000)}"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, EXTRACTED_LAKE_FILE)
        _lake_cache_mem = data
        _lake_cache_mtime = os.path.getmtime(EXTRACTED_LAKE_FILE)
    except Exception as e:
        logger.error(f"Error saving BCTC lake data: {e}")


def _get_corporate_actions_lake() -> Dict[str, Any]:
    """Reads L2 persistent corporate actions lake cache with in-memory mtime caching and Google Colab Drive sync."""
    global _corp_cache_mem, _corp_cache_mtime
    file_path = _resolve_lake_file("extracted_corporate_actions.json")
    if os.path.exists(file_path):
        try:
            mtime = os.path.getmtime(file_path)
            if _corp_cache_mem and _corp_cache_mtime == mtime:
                return _corp_cache_mem
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _corp_cache_mem = data
            _corp_cache_mtime = mtime
            return data
        except Exception:
            return _corp_cache_mem or {}
    return {}


def _save_corporate_actions_lake(data: Dict[str, Any]) -> None:
    """Saves to L2 persistent corporate actions lake cache atomically."""
    global _corp_cache_mem, _corp_cache_mtime
    try:
        tmp_file = CORPORATE_ACTIONS_LAKE_FILE + f".tmp_{os.getpid()}_{int(time.time()*1000)}"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, CORPORATE_ACTIONS_LAKE_FILE)
        _corp_cache_mem = data
        _corp_cache_mtime = os.path.getmtime(CORPORATE_ACTIONS_LAKE_FILE)
    except Exception as e:
        logger.error(f"Error saving corporate actions lake data: {e}")


class BCTCBatchProcessor:
    """
    High-volume multi-threaded pipeline for downloading, caching, and parsing
    BCTC filings without external LLM dependencies.
    """

    def __init__(self, lake_dir: str = PDF_LAKE_DIR):
        self.lake_dir = os.path.abspath(lake_dir)
        os.makedirs(self.lake_dir, exist_ok=True)

    def download_report_pdf(self, symbol: str, pdf_url: str, filename_prefix: str) -> Optional[str]:
        """
        Downloads a single PDF filing safely to local disk lake if not already present.
        """
        symbol = symbol.upper().strip()
        sym_dir = os.path.join(self.lake_dir, symbol)
        os.makedirs(sym_dir, exist_ok=True)

        clean_prefix = re.sub(r"[^\w\-_]", "_", filename_prefix)
        local_path = os.path.join(sym_dir, f"{clean_prefix}.pdf")

        if os.path.exists(local_path) and os.path.getsize(local_path) > 1024:
            return local_path

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://cafef.vn/"
        }
        try:
            req = urllib.request.Request(pdf_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                data = resp.read()
                if len(data) > 1024:
                    with open(local_path, "wb") as f:
                        f.write(data)
                    return local_path
        except Exception as e:
            logger.warning(f"Failed to download PDF for {symbol} from {pdf_url}: {e}")

        return None

    def process_single_company(
        self,
        symbol: str,
        year: str = "all",
        max_reports: int = 5
    ) -> Dict[str, Any]:
        """
        Retrieves company disclosures, downloads available BCTC PDFs, and parses them.
        """
        symbol = symbol.upper().strip()
        reports_meta = get_company_reports(symbol=symbol, report_type="bctc", fetch_pdf=True, page=1, page_size=max_reports, year=year)
        reports = reports_meta.get("reports", []) or reports_meta.get("data", {}).get("reports", [])
        if not reports and "reports_all" in reports_meta:
            reports = reports_meta["reports_all"][:max_reports]

        lake = _get_lake_data()
        results = []

        for rep in reports:
            pdf_url = rep.get("pdf_url")
            if not pdf_url:
                continue

            doc_id = f"{symbol}_{rep.get('year', '2024')}_{abs(hash(rep.get('title', '')))}"
            # Check if already processed in lake
            if doc_id in lake:
                results.append(lake[doc_id])
                continue

            prefix = f"{rep.get('year', '2024')}_{doc_id[:16]}"
            local_pdf = self.download_report_pdf(symbol, pdf_url, prefix)
            if not local_pdf:
                continue

            try:
                parser = BCTCPdfParser(local_pdf)
                extracted = parser.extract_full_report()
                p_info = extracted.get("period_info", {})
                record = {
                    "doc_id": doc_id,
                    "symbol": symbol,
                    "title": rep.get("title", ""),
                    "year": p_info.get("year") or rep.get("year", ""),
                    "quarter": p_info.get("quarter"),
                    "period_type": p_info.get("period_type", "unknown"),
                    "period_label": p_info.get("period_label", ""),
                    "filing_date": rep.get("date", ""),
                    "filing_timestamp": rep.get("timestamp", 0),
                    "is_audited": p_info.get("is_audited", False) or (rep.get("audit_badge") is not None),
                    "pdf_url": pdf_url,
                    "local_path": local_pdf,
                    "extracted_data": extracted,
                    "processed_at": time.time()
                }
                lake[doc_id] = record
                results.append(record)
            except Exception as e:
                logger.error(f"Error parsing PDF {local_pdf}: {e}")

        _save_lake_data(lake)
        return {
            "symbol": symbol,
            "reports_processed": len(results),
            "results": results
        }

    def batch_process_universe(
        self,
        symbols: List[str],
        year: str = "all",
        max_workers: int = 5
    ) -> Dict[str, Any]:
        """
        Batch processes an entire universe of tickers concurrently.
        """
        summary = {"total_symbols": len(symbols), "success_count": 0, "processed_reports": 0}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.process_single_company, s, year, 3): s for s in symbols}
            for fut in as_completed(futures):
                s = futures[fut]
                try:
                    res = fut.result()
                    summary["success_count"] += 1
                    summary["processed_reports"] += res.get("reports_processed", 0)
                except Exception as e:
                    logger.error(f"Failed processing symbol {s}: {e}")

        return summary

    def process_corporate_disclosures(
        self,
        symbol: str,
        report_types: List[str] = ["resolution", "governance", "dividend"],
        limit_per_type: int = 2
    ) -> Dict[str, Any]:
        """
        Downloads and parses non-BCTC filings (Resolutions, Governance, Dividend notices).
        Persists results to data/pdf_lake/extracted_corporate_actions.json.
        """
        from services.corporate_disclosures_parser import CorporateDisclosuresParser
        lake = _get_corporate_actions_lake()
        results = []

        for r_type in report_types:
            try:
                rep_data = get_company_reports(symbol, report_type=r_type, fetch_pdf=True, page_size=limit_per_type)
                reports = rep_data.get("reports", [])
            except Exception as e:
                logger.warning(f"Failed fetching {r_type} reports for {symbol}: {e}")
                continue

            for rep in reports:
                pdf_url = rep.get("pdf_url")
                if not pdf_url:
                    continue

                safe_title = re.sub(r"[^\w\-_]", "_", rep.get("title", "doc"))[:30]
                filename = f"{symbol}_{r_type.upper()}_{rep.get('year', '2026')}_{safe_title}"
                local_pdf = self.download_report_pdf(symbol, pdf_url, filename)
                if not local_pdf or not os.path.exists(local_pdf):
                    continue

                doc_id = f"{symbol}_{r_type}_{abs(hash(local_pdf)) % 100000}"
                try:
                    parser = CorporateDisclosuresParser(local_pdf)
                    extracted = parser.extract_full_report(category_hint=r_type)

                    record = {
                        "doc_id": doc_id,
                        "symbol": symbol.upper(),
                        "category": r_type,
                        "title": rep.get("title", ""),
                        "date": rep.get("date", ""),
                        "timestamp": rep.get("timestamp", 0),
                        "pdf_url": pdf_url,
                        "local_path": local_pdf,
                        "extracted_data": extracted,
                        "processed_at": time.time()
                    }
                    lake[doc_id] = record
                    results.append(record)
                except Exception as e:
                    logger.error(f"Error parsing disclosure PDF {local_pdf}: {e}")

        _save_corporate_actions_lake(lake)
        return {
            "symbol": symbol,
            "disclosures_processed": len(results),
            "results": results
        }

    def parse_existing_local_lake(self) -> Dict[str, Any]:
        """
        Iterates over all existing local PDF files in `data/pdf_lake/{symbol}/`,
        identifies BCTC filings, parses them, extracts periods & TT200 statements,
        and saves into `data/pdf_lake/extracted_bctc_lake.json`.
        """
        lake = _get_lake_data()
        stats = {"symbols_scanned": 0, "files_parsed": 0, "errors": 0}

        if not os.path.exists(self.lake_dir):
            return stats

        symbol_dirs = [d for d in os.listdir(self.lake_dir) if os.path.isdir(os.path.join(self.lake_dir, d))]
        stats["symbols_scanned"] = len(symbol_dirs)

        for sym in sorted(symbol_dirs):
            sym_clean = sym.upper().strip()
            sym_path = os.path.join(self.lake_dir, sym)
            pdf_files = [f for f in os.listdir(sym_path) if f.lower().endswith(".pdf")]

            for fn in pdf_files:
                fn_upper = fn.upper()
                if any(k in fn_upper for k in ["_DIVIDEND_", "_RESOLUTION_", "_GOVERNANCE_", "_INSIDER_"]):
                    continue

                full_path = os.path.join(sym_path, fn)
                doc_id = f"{sym_clean}_{fn[:-4]}"
                if doc_id in lake:
                    continue

                try:
                    parser = BCTCPdfParser(full_path)
                    extracted = parser.extract_full_report()
                    p_info = extracted.get("period_info", {})
                    record = {
                        "doc_id": doc_id,
                        "symbol": sym_clean,
                        "title": fn,
                        "year": p_info.get("year", "2024"),
                        "quarter": p_info.get("quarter"),
                        "period_type": p_info.get("period_type", "unknown"),
                        "period_label": p_info.get("period_label", ""),
                        "filing_date": "",
                        "filing_timestamp": int(os.path.getmtime(full_path)),
                        "is_audited": p_info.get("is_audited", False),
                        "pdf_url": "",
                        "local_path": full_path,
                        "extracted_data": extracted,
                        "processed_at": time.time()
                    }
                    lake[doc_id] = record
                    stats["files_parsed"] += 1
                except Exception as e:
                    logger.error(f"Error parsing existing PDF {full_path}: {e}")
                    stats["errors"] += 1

        _save_lake_data(lake)
        return stats


def calculate_source0_ttm(symbol: str, lake_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Computes rolling 4-quarter TTM financial metrics and point-in-time Balance Sheet
    from Source 0 ground truth reports.
    """
    symbol_clean = symbol.upper().strip()
    lake = lake_data if lake_data is not None else _get_lake_data()

    matching = [r for r in lake.values() if r.get("symbol") == symbol_clean]
    if not matching:
        return None

    def _sort_key(r):
        y = int(r.get("year") or 0) if str(r.get("year", "")).isdigit() else 0
        q = r.get("quarter") or 0
        ts = r.get("filing_timestamp") or 0
        return (y, q, ts)

    matching.sort(key=_sort_key, reverse=True)

    latest_rec = matching[0]
    latest_ext = latest_rec.get("extracted_data", {})
    latest_bs = latest_ext.get("balance_sheet", {}).get("items", {})

    tot_assets = latest_bs.get(270, {}).get("current_val")
    equity = latest_bs.get(400, {}).get("current_val")
    tot_liab = latest_bs.get(300, {}).get("current_val")
    cash = latest_bs.get(110, {}).get("current_val")
    st_debt = latest_bs.get(320, {}).get("current_val") or 0.0
    lt_debt = latest_bs.get(338, {}).get("current_val") or 0.0
    tot_debt = st_debt + lt_debt
    net_debt = tot_debt - (cash or 0.0)

    # Strategy 1: Check for 4 distinct rolling quarters
    quarters_seen = []
    seen_periods = set()
    for r in matching:
        q = r.get("quarter")
        y = r.get("year")
        if q and y:
            period_id = f"{y}_Q{q}"
            if period_id not in seen_periods:
                seen_periods.add(period_id)
                quarters_seen.append(r)
                if len(quarters_seen) == 4:
                    break

    if len(quarters_seen) == 4:
        rev_ttm = sum(r.get("extracted_data", {}).get("income_statement", {}).get("revenue_vnd", 0.0) or 0.0 for r in quarters_seen)
        npat_ttm = sum(r.get("extracted_data", {}).get("income_statement", {}).get("npat_vnd", 0.0) or 0.0 for r in quarters_seen)
        cfo_ttm = sum(r.get("extracted_data", {}).get("cash_flow", {}).get("cfo_vnd", 0.0) or 0.0 for r in quarters_seen)
        capex_ttm = sum(r.get("extracted_data", {}).get("cash_flow", {}).get("capex_vnd", 0.0) or 0.0 for r in quarters_seen)
        fcf_ttm = cfo_ttm - capex_ttm
        ttm_method = "ROLLING_4_QUARTERS"
        quarters_used = [f"Q{r.get('quarter')}/{r.get('year')}" for r in quarters_seen]
    else:
        # Strategy 2: Use latest Annual Audited FY report if available
        annual_recs = [r for r in matching if r.get("period_type") == "annual" or r.get("is_audited")]
        target_rec = annual_recs[0] if annual_recs else latest_rec
        target_ext = target_rec.get("extracted_data", {})
        is_stmt = target_ext.get("income_statement", {})
        cf_stmt = target_ext.get("cash_flow", {})

        rev_ttm = is_stmt.get("revenue_vnd")
        npat_ttm = is_stmt.get("npat_vnd")
        cfo_ttm = cf_stmt.get("cfo_vnd")
        capex_ttm = cf_stmt.get("capex_vnd")
        fcf_ttm = cf_stmt.get("fcf_vnd") or ((cfo_ttm - capex_ttm) if cfo_ttm is not None and capex_ttm is not None else None)
        ttm_method = "LATEST_ANNUAL_BASELINE"
        quarters_used = [target_rec.get("period_label") or str(target_rec.get("year", "FY"))]

    return {
        "symbol": symbol_clean,
        "as_of_period": latest_rec.get("period_label") or str(latest_rec.get("year", "")),
        "ttm_method": ttm_method,
        "quarters_used": quarters_used,
        "revenue_ttm": rev_ttm,
        "net_profit_ttm": npat_ttm,
        "cfo_ttm": cfo_ttm,
        "capex_ttm": capex_ttm,
        "fcf_ttm": fcf_ttm,
        "total_assets": tot_assets,
        "equity": equity,
        "total_liabilities": tot_liab,
        "cash_and_equivalents": cash,
        "total_debt": tot_debt,
        "net_debt": net_debt,
        "provenance_tier": 4
    }


