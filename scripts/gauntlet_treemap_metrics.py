"""Treemap gauntlet metrics harness.

Captures the live treemap tab and measures objective quality metrics so
gauntlet rounds can be compared numerically instead of by vibes.

Usage: python scripts/gauntlet_treemap_metrics.py <round_id>
Writes: gauntlet_out/rounds/<round_id>.json and <round_id>.png
"""
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "gauntlet_out" / "rounds"
OUT.mkdir(parents=True, exist_ok=True)


def rank(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(xs, ys):
    if len(xs) < 3:
        return 0.0
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def parse_cap(title):
    # "FPT - FPT Corp\nGiá: ... \nVốn hóa: 146,320 tỷ\nSàn: HOSE"
    for part in title.split("\n"):
        if "Vốn hóa" in part:
            digits = "".join(ch for ch in part if ch.isdigit())
            if digits:
                return float(digits)
    return None


def main(round_id):
    api = json.loads(urllib.request.urlopen(BASE + "/api/market-treemap").read())
    data = api.get("data", api)
    sectors = data.get("sectors", [])
    expected = {c["symbol"]: float(c.get("market_cap") or 0) for s in sectors for c in s.get("children", [])}

    res = {"round": round_id, "ts": time.time()}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)

        t_click = time.time()
        page.click('.view-tab[data-tab="treemap"]', timeout=10000)

        # render-complete: tile count stable for ~600ms or 15s deadline
        prev, stable_since, tiles_n, t_done = -1, None, 0, None
        deadline = time.time() + 15
        while time.time() < deadline:
            tiles_n = page.locator(".treemap-tile").count()
            now = time.time()
            if tiles_n == prev and tiles_n > 0:
                if stable_since is None:
                    stable_since = now
                elif now - stable_since > 0.6:
                    t_done = now
                    break
            else:
                stable_since = None
            prev = tiles_n
            page.wait_for_timeout(120)
        if t_done is None:
            t_done = time.time()

        res["switch_ms"] = round((t_done - t_click) * 1000)
        res["tile_count"] = tiles_n
        res["expected_count"] = len(expected)

        # coverage: which expected symbols rendered as tiles (data-symbol attr,
        # robust to adaptive labels hiding the symbol span on tiny tiles)
        syms = set(page.eval_on_selector_all(".treemap-tile", "els => els.map(e => e.getAttribute('data-symbol').trim())"))
        missing = sorted(set(expected) - syms)
        res["coverage_pct"] = round(100 * (len(expected) - len(missing)) / max(1, len(expected)), 1)
        res["missing_sample"] = missing[:10]

        # size fidelity: bounding-box area vs market_cap (spearman)
        boxes = page.evaluate(
            """() => [...document.querySelectorAll('.treemap-tile')].map(t => {
                const r = t.getBoundingClientRect();
                const s = t.querySelector('.tile-symbol');
                return {sym: s ? s.textContent.trim() : '', w: r.width, h: r.height};
            })"""
        )
        pairs = [(b["w"] * b["h"], parse_cap(b["title"]) if False else expected.get(b["sym"])) for b in boxes]
        pairs = [(a, c) for a, c in pairs if c and c > 0 and a > 1]
        areas = [p[0] for p in pairs]
        caps = [p[1] for p in pairs]
        res["area_vs_cap_spearman"] = round(spearman(areas, caps), 3)
        res["size_fidelity_pairs"] = len(pairs)

        # custom tooltip check: hover first tile, look for tooltip element beyond native title
        try:
            page.hover(".treemap-tile >> nth=0", timeout=3000)
            page.wait_for_timeout(400)
            res["custom_tooltip_present"] = page.evaluate(
                "() => !!document.querySelector('.treemap-tooltip, .tm-tooltip, #treemapTooltip')"
            )
        except Exception:
            res["custom_tooltip_present"] = False

        # legend presence & richness
        res["legend_items"] = page.locator(".legend-item").count()

        # screenshot BEFORE interaction tests (tile click navigates away)
        shot = OUT / f"{round_id}.png"
        page.screenshot(path=str(shot), full_page=False)

        # interactions still work: click a tile should not throw
        try:
            page.click(".treemap-tile >> nth=0", timeout=3000)
            page.wait_for_timeout(500)
        except Exception as e:
            errors.append(f"tile click failed: {e}")

        res["js_errors"] = errors[:10]
        res["screenshot"] = str(shot)
        browser.close()

    out = OUT / f"{round_id}.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "round_0")
