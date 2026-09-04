# Research: Real Historical Data for Vietnam Benchmarks & ICB Sector Indices

> Research-only deliverable. All code snippets below were **actually executed and verified** on
> 2026-08-22 against the installed environment (`vnstock 3.5.1`, Python 3.13, Windows/PowerShell).
> Goal: replace synthetic data in the "Chỉ số ngành" tab with real index history.

---

## 1. Environment

| Item | Value |
|---|---|
| `vnstock` version | **3.5.1** (4.0.7 available; not tested here) |
| Import style (matches `services/stock_service.py:44-49`) | `from vnstock import Quote, Company, Listing` + `from vnstock.core import setup_api_key` |
| API key | `.env` → `VNSTOCK_API_KEY=vnstock_23c9...` — same key already hardcoded as fallback in stock_service.py:49 |
| Community rate limit | **60 requests/phút** announced at setup; measured real throughput ≈ **13–20 req/min sequential** (network latency dominated; occasional 30 s read-timeout + tenacity retry on `trading.vietcap.com.vn`) |
| Node | v22.17.0, `@mathieuc/tradingview` installed in project `node_modules` |

---

## 2. Verified working code

### 2a. Benchmark history (VNINDEX, VN30, HNXINDEX, UPCOMINDEX)

```python
import os
from vnstock import Quote
from vnstock.core import setup_api_key

setup_api_key(os.environ["VNSTOCK_API_KEY"])

df = Quote(symbol="VNINDEX", source="VCI").history(
    start="2000-01-01", end="2026-08-22", interval="1D")
# columns: ['time', 'open', 'high', 'low', 'close', 'volume']  (time = pandas Timestamp)
```

Measured results (daily):

| Symbol | Rows | First date | Last date | Notes |
|---|---|---|---|---|
| VNINDEX | 5633 | **2004-01-05** | 2026-08-21 | deepest benchmark history |
| VN30 | 3630 | 2012-02-06 | 2026-08-21 | |
| HNXINDEX | 5178 | 2005-07-14 | 2026-08-21 | |
| UPCOMINDEX | 4199 | 2009-06-25 | 2026-08-21 | ⚠️ symbol is `UPCOMINDEX`, NOT `UPCOM` (the latter raises `ValueError: Invalid symbol`) |

- `interval="1W"` works too (145 rows for 2024→now; weekly bar timestamped at period end).
- `interval="1m"` also works — returns intraday minute bars for a session (256 bars for 2026-08-21), useful for live snapshots.
- Invalid symbols raise `ValueError` immediately (no silent empty frame) — safe to probe.

### 2b. HOSE ICB sector indices via VCI ✅ REAL DATA EXISTS

HOSE publishes official ICB industry-group indices and **vnstock/VCI serves their full daily OHLCV**:

```python
for s in ["VNFIN","VNFINLEAD","VNDIAMOND","VNSI","VN100",
          "VNIT","VNREAL","VNUTI","VNMAT","VNHEAL","VNIND","VNCONS"]:
    df = Quote(symbol=s, source="VCI").history(start="2000-01-01", end="2026-08-22", interval="1D")
```

Verified depth:

| Index | ICB meaning | First date | Last date |
|---|---|---|---|
| VNFIN | Financials (sector) | 2017-05-31 | 2026-08-21 |
| VNREAL | Real Estate | 2017-05-31 | 2026-08-21 |
| VNUTI | Utilities | 2017-05-31 | 2026-08-21 |
| VNMAT | Materials | 2017-05-31 | 2026-08-21 |
| VNHEAL | Health Care | 2017-05-31 | 2026-08-21 |
| VNIND | Industrials | 2017-05-31 | 2026-08-21 |
| VNCONS | Consumer | 2017-05-31 | 2026-08-21 |
| VNIT | Information Technology | 2020-01-02 | 2026-08-21 |
| VNFINLEAD | Large-cap financials | 2019-11-18 | 2026-08-21 |
| VNDIAMOND | Quality/growth selection | 2019-11-18 | 2026-08-21 |
| VNSI | Sustainability | 2021-09-06 | 2026-08-21 |
| VN100 | Mid+large beyond VN30 | 2022-06-20 | 2026-08-21 |

Symbols that do **NOT** exist on VCI (all raise `ValueError`): `UPCOM`, `HNX30INDEX`, `VNALLSHARE`,
`VNBANK`, `VNEN`, `VNTEL`, `VNCYC`, `VNDEF`, `VNUTIL`, `VNFOOD`, `VNPET`, `VNCHEM`, `VNSTEEL`,
`VNCOM`, `VNMEDIA`, `VNTIC`, `VNCODI`, `VNCOST`, `VNCOME`.
⚠️ `VNMIDCAP` resolves but returned nonsense values (close=1.96) — avoid.

### 2c. Listing class — mostly broken in 3.5.1 (do not rely on it)

Verified failures:
- `Listing(source="VCI").all_symbols()` → `RetryError(ConnectionError)` (upstream JSON/API failure)
- `Listing(source="VCI").industries_icb()` → `RetryError(ValueError)`
- `Listing(source="VCI").symbols_by_exchange()` → `RetryError(ConnectionError)`
- `Listing.industries` / `symbols_by_industry` attributes don't exist (correct names are `industries_icb` / `symbols_by_industries`)
- Valid `Listing` sources: only `'KBS'`, `'VCI'`, `'MSN'`; valid `Quote` sources: `'kbs','vci','msn','dnse','binance','fmp','fmarket'` (**not** `"TCBS"`)
- MSN listing → `NotImplementedError`

The project already bypasses this correctly: `sync_universe_from_vnstock()` (services/stock_service.py:274)
fetches the universe + ICB codes straight from `https://trading.vietcap.com.vn/api/price/symbols/getAll`
and KBS — keep that approach for sector membership.

---

## 3. Local Node TradingView fetchers

All three scripts disable TLS verification (`NODE_TLS_REJECT_UNAUTHORIZED='0'`) — acceptable here but noted.

### `scripts/fetch_tradingview.js` — single-symbol daily candles
```powershell
node scripts\fetch_tradingview.js "HOSE:VNINDEX"   # arg2 = range is ignored on CLI path (hardcoded 1200)
```
Or programmatically: `getTradingViewCandles("HOSE:FPT", 1500)` → array of
`{ time, timestamp, open, high, low, close, volume }` (volume is `NaN` for indices).
- Verified: `HOSE:VNINDEX` and `HOSE:VNFIN` both return **1200 daily candles (~5 years, back to 2021-10)**.
- Works for any TradingView Vietnam symbol including indices and custom lists (e.g., all constituents of a sector).

### `scripts/sync_tradingview_prices.js` — bulk quarterly aggregation
- No CLI args. Reads `data/screener_snapshot.json` / `data/all_symbols.json` (only 3-letter A-Z stock symbols from HOSE/HNX/UPCOM), spawns **3 workers**, fetches `timeframe:'D', range:2600` per symbol with 3.5 s timeout + exchange fallback, aggregates to quarters, checkpoints every 30 symbols into `data/historical_prices.json`. 30 ms pause between requests.

### `scripts/scan_tv_node.js` — live snapshot of whole market
- No CLI args. One POST to `https://scanner.tradingview.com/vietnam/scan` → **1291 rows** of
  price/change/volume/mcap/P-E/P-B/ROE/margins etc. in a single request. Ideal for live tab data;
  filterable by ICB-like fields if extended.

---

## 4. Source comparison

| Criterion | vnstock `Quote` (VCI) | TradingView node (`@mathieuc`) | TV scanner endpoint |
|---|---|---|---|
| Benchmark indices (VNINDEX…) | ✅ daily back to **2004** | ✅ ~1200 days (2021→) | snapshot only |
| HOSE ICB sector indices (VNFIN, VNIT…) | ✅ verified 12 symbols | ✅ (e.g. HOSE:VNFIN) | n/a |
| Daily OHLCV quality | OHLCV, clean pandas DF | OHLCV, index volume=NaN | close/change only |
| Max practical scale | ~60 req/min cap (measured ~13–20/min incl. latency & retries); ~1300 symbols ≈ **1–2 h** one-off sync | WebSocket, 3 workers ≈ 1300 symbols in ~15–30 min, unofficial API (risk of block) | **entire market in 1 request** |
| Auth/rate limits | community key required (already in .env), 60 req/min | none (unofficial, no key) | none (unofficial) |
| Reliability for long DAILY history | **best** (deepest archive, official provider) | medium (unofficial WS, timeouts observed) | n/a |
| Live snapshot | `interval="1m"` works but 1 req/symbol | per-symbol session | best (bulk) |

---

## 5. Recommendation

**(a) Benchmark history** → `Quote(symbol="VNINDEX"|"VN30"|"HNXINDEX"|"UPCOMINDEX", source="VCI").history(...)`.
Deepest reliable daily history (VNINDEX → 2004). Cache daily; refresh once after market close. Note `UPCOM` is invalid — use `UPCOMINDEX`.

**(b) Per-symbol daily candles at ~1300-symbol scale** → keep the existing Node pipeline
(`scripts/sync_tradingview_prices.js` pattern, 3 workers + exchange fallback) for bulk syncs since vnstock's
community quota (60 req/min nominal, ~13–20/min real) makes a full VCI sweep take 1–2 h and risks throttling.
Use vnstock/VCI as the authoritative backfill/correction pass for indices and high-value symbols where you need
pre-2021 depth (TV caps around 1200 candles via these scripts). For the "Chỉ số ngành" tab specifically,
the 12 sector/benchmark index series are cheap to pull directly from vnstock (12 requests total).

**(c) Live snapshot values** → `scripts/scan_tv_node.js` scanner endpoint: all ~1291 symbols with
price/change/fundamentals in one request (fastest, no key). Fallback: vnstock `Quote(...).history(interval="1m")`
per symbol when a single symbol's live intraday detail is needed.

Sector membership mapping stays as-is (VCI getAll endpoint provides `icbCode2`; see SECTOR_MAP_ICB in stock_service.py:286).
