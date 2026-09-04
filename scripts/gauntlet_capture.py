"""Gauntlet Round 1: capture app screenshots per tab + measure key metrics."""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent.parent / "gauntlet_out" / "app"
OUT.mkdir(parents=True, exist_ok=True)

TABS = ["board", "chart", "quant", "backtest", "sectors", "news", "treemap", "foreign", "alerts"]

results = {}

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(8000)

    for tab in TABS:
        t0 = time.time()
        try:
            page.click(f'.view-tab[data-tab="{tab}"]', timeout=10000)
        except Exception as e:
            results[tab] = {"error": f"click failed: {e}"}
            continue
        page.wait_for_timeout(6000)  # allow async data to load
        shot = OUT / f"{tab}.png"
        page.screenshot(path=str(shot), full_page=False)
        results[tab] = {
            "switch_ms": round((time.time() - t0 - 6) * 1000),
            "screenshot": str(shot),
        }
        if tab == "chart":
            # measure time-to-candles: click another symbol in board? Just record canvas presence
            has_main = page.locator("#mainChartContainer canvas").count()
            has_sub = page.locator("#subChartContainer canvas").count()
            hud = page.locator("#hudClose").inner_text()
            results["chart"]["canvases"] = {"main": has_main, "sub": has_sub}
            results["chart"]["hud_close"] = hud
            # scroll chart panel into view and capture right column too
            page.locator(".chart-view-right").screenshot(path=str(OUT / "chart_right.png"))

    results["_page_errors"] = errors[:10]
    browser.close()

report = OUT / "capture_report.json"
report.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(results, indent=2, ensure_ascii=False))
