"""Gauntlet Round 1b: capture reference-bar screenshots (best effort)."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "gauntlet_out" / "bars"
OUT.mkdir(parents=True, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36")

BARS = [
    # Bar cho tab Chart: TradingView chart HOSE:FPT
    ("tradingview_fpt", "https://www.tradingview.com/chart/?symbol=HOSE%3AFPT"),
    # Bar cho tab Board: SSI iBoard
    ("iboard_ssi", "https://iboard.ssi.com.vn/"),
    # Bar cho tab Quant Screener: TradingView Stock Screener (Overview)
    # Verified: 200, render 100+ rows factor table (P/E, EPS growth, ROE, PEG...)
    ("tv_screener", "https://www.tradingview.com/screener/"),
]

results = {}
with sync_playwright() as p:
    browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(user_agent=UA, viewport={"width": 1600, "height": 900},
                              locale="vi-VN")
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    for name, url in BARS:
        url = url.replace(" ", "")
        page = ctx.new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(12000)
            shot = OUT / f"{name}.png"
            page.screenshot(path=str(shot))
            results[name] = {
                "url": url,
                "status": resp.status if resp else None,
                "screenshot": str(shot),
                "title": page.title()[:100],
            }
        except Exception as e:
            results[name] = {"url": url, "error": str(e)[:200]}
        finally:
            page.close()
    browser.close()

(OUT / "bars_report.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(results, indent=2, ensure_ascii=False))
