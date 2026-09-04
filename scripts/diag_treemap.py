"""Diagnostic: why is the treemap grid empty?"""
import json
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1600, "height": 900})
    console = []
    netfail = []
    page.on("console", lambda m: console.append(f"{m.type}: {m.text[:300]}"))
    page.on("requestfailed", lambda r: netfail.append(f"{r.url} {r.failure}"))
    page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(7000)
    page.click('.view-tab[data-tab="treemap"]', timeout=10000)
    page.wait_for_timeout(6000)
    state = page.evaluate(
        """() => ({
            hasApp: !!window.app,
            hasMarketTreemap: typeof window.MarketTreemap,
            tmManagerNull: !!(window.app && !window.app.treemapManager),
            currentTab: window.app ? window.app.currentTab : null,
            containerExists: !!document.getElementById('treemapContainer'),
            containerHTMLlen: document.getElementById('treemapContainer') ? document.getElementById('treemapContainer').innerHTML.length : -1,
            panelVisible: (() => { const el = document.getElementById('tab_treemap'); return el ? getComputedStyle(el).display : 'missing'; })(),
            gridExists: !!document.getElementById('treemapGrid'),
        })"""
    )
    print(json.dumps(state, indent=2))
    # try manual fetch + render
    manual = page.evaluate(
        """async () => {
            try {
                const res = await fetch('/api/market-treemap');
                const json = await res.json();
                const d = json.data;
                const sectors = Array.isArray(d) ? d : (d.sectors || d.children || []);
                return {status: res.status, sectorsLen: sectors.length, firstKeys: sectors[0] ? Object.keys(sectors[0]) : null};
            } catch (e) { return {error: String(e)}; }
        }"""
    )
    print(json.dumps(manual, indent=2))
    print("--- console (last 30) ---")
    for c in console[-30:]:
        print(c)
    print("--- netfail (last 10) ---")
    for f in netfail[-10:]:
        print(f)
    b.close()
