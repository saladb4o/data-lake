# Valuation & Backtest Audit Note

> **Status of the previous version of this file.** It certified the system
> COMPLIANT on "Zero Fake Data", "No Cheap Tricks" and a "Price-Tautology
> Firebreak", and reported 41,872 verified quarterly valuations. Those claims
> did not hold against the code they described. The document is rewritten here
> to record what was actually found and what changed, because a green audit
> that is wrong is worse than no audit: it stops anyone looking.

## 1. What was wrong

### 1.1 Fair value was a fixed multiple of the price being judged

Two mechanisms, both live at the same time.

**Input layer.** Every absent model input was replaced with a fraction of
market cap - debt 40%, revenue 80%, equity 60%, cash 15%, RWA 120%, land bank
20%. Market cap is price x shares, so a payload with no financial statements
produced a complete set of "fundamentals" that were all linear in price.

**Model layer.** Each of the 22 models floored its own drivers and its final
equity value at further fractions of market cap - `equity_val = max(x, 0.10 *
market_cap)` appeared in eleven models, alongside driver floors such as
`clean_ebitda = max(ebitda, 0.05 * market_cap)` and `bv_0 = max(book_equity,
0.20 * market_cap)`. 29 such floors in total.

Measured: the same company valued at 10,000, 20,000, 40,000 and 80,000 VND
returned a composite fair value of exactly **0.7619 x price** at every level.
An eight-fold change in price, no change in the ratio.

### 1.2 The backtest reconstructed history from price

`fair_value_backtest_service.py` had no historical statements, so it computed
`eps = historical_price / current_pe` and `bvps = historical_price /
current_pb`, then derived net income, revenue, EBIT, EBITDA, cash, CFO, FCF and
debt from those two. The comment on that block read *"This is unbiased"*. It
assumes the company's P/E was constant from 2021 to today, which is the thing
under measurement.

The universe was the **current** screener applied to every historical quarter:
today's ROE deciding a 2021 purchase (lookahead), and delisted companies simply
absent (survivorship).

### 1.3 Model weighting rewarded agreeing with the market

Rolling error paired each fair value with the price of the **same** quarter, so
a model that correctly identified a 40% mispricing was scored as 40% wrong.
Separately, `historical_errors` was never supplied by any production caller, so
every "Omnibus - SMAPE" request took a fallback branch that weighted each model
by its closeness to the mean of the others - herding, not error weighting -
while the UI told the user it was error-calibrated.

### 1.4 Smaller defects

- Nearest-rank quartiles inflated the IQR until the outlier fence stopped
  rejecting anything at small n.
- Sector priors were diluted by every model the priors table did not name:
  VNBNK's stated 35% was 29% in practice, and moved with unrelated models.
- `composite_fair_value` fell back to a literal 10,000 VND; all 22 model
  signatures defaulted `current_price` to 10,000.
- Altman Z'' inputs fell back to fractions of market cap, making the bankruptcy
  verdict a function of the share price.
- Custom symbols absent from the screener were replaced with an invented
  company (price 30,000, market cap 15,000bn, ROE 18%, ROIC 15%).
- Sharpe, Sortino and Calmar divided by `max(denominator, 1.0)` on percentage
  denominators, unbounded-inflating the ratios for low-volatility runs.
- Missing screener factors were ranked at the 50th percentile, so
  non-disclosure was free.

## 2. What changed

| Area | Change |
| --- | --- |
| Input provenance | `InputResolver` marks every input REAL, DERIVED or IMPUTED, and provenance propagates through derivations. |
| Model gating | A model whose declared drivers were imputed publishes `INSUFFICIENT_DATA` and leaves the composite. A price-only payload yields 22 x INSUFFICIENT_DATA and a composite of 0. |
| Price floors | All 29 removed. A loss-maker gets no P/E, a non-payer no DDM, negative book equity no P/B; equity wiped out by debt reports zero. |
| Backtest inputs | `fundamentals_mode=point_in_time` (default) values only symbol-quarters with a filing published by the rebalance date. `snapshot_projected` reproduces the old arithmetic and stamps every payload with a warning that it is not evidence of skill. |
| Error scoring | Fair values are scored against the price **four quarters later**, and only where that horizon has already been observed. |
| Weighting | Linear-interpolation quartiles; sector priors renormalised only among the models they name, with the table's gaps reported; the herding fallback replaced by the sector prior plus an explicit "metric not applied" flag. |
| Risk firewall | Altman Z'' is labelled unreliable when its inputs were imputed, and will not disqualify a company on an invented score. |
| Metrics | Risk-adjusted ratios are withheld (`None`) rather than inflated when the denominator is below a basis point. |
| Screener | Pillar weights renormalise over reported factors; the composite is shrunk toward the midpoint in proportion to missing data; `factor_coverage_pct` is published. |

## 3. Second pass: the rest of services/

An audit of the remaining twenty-odd service modules found the same disease in
four more places, plus three unrelated defects.

### 3.1 Market data invented from the ticker's spelling

`ALL_SYMBOLS_MAP` filled a missing reference price with
`15.0 + crc32(symbol) % 85` and a missing market cap with
`1500 + crc32(symbol) % 145000`. Both are stable across runs, so they read as
observations rather than as a function of how a ticker is spelled - and this
map feeds the screener, the peer engine and the backtest universe fallback.
Fourteen downstream read sites then re-invented the same values
(`.get("ref", 50.0)`, `.get("market_cap", 25000)`, `.get("eps", 3500.0)`).

`compute_algorithmic_peers` invented every candidate's market cap, ROE, ROA,
P/E and P/B from the same hash and ranked "similarity" over them, so for a
thinly covered ticker the peer list was a ranking over the letters of the
tickers. Its `change_pct` default used `abs(hash(sym))`, which is seeded per
process, so the same peer showed a different daily move after every restart.

### 3.2 A second valuation engine with the same circularity

`get_company_earnings_engine` - the single-stock deep dive - computed
`bvps = price / P/B` and `eps = price / P/E`, so its "Justified P/B" and
"Forward P/E" scenarios reduced to the entry price times a ratio. Its fallback
built a whole synthetic company (20% gross margin, 10% operating margin, D/E
0.5, all four pillars at exactly 50) for any uncovered symbol and ran the full
6-model x 3-scenario matrix on it.

### 3.3 A fabricated institutional cost basis

`smart_money_flow_engine` reported `foreign_vwap_30d = current_price * 0.97`
and `foreign_vwap_90d = current_price * 0.94`, so "distance to foreign cost
basis" was always exactly -3.09% (or +2.91% on the other branch) whatever
foreign investors actually paid, and the support/resistance verdict derived
from it never varied. Proprietary desk flow was likewise derived from turnover
with fixed 3-7% coefficients.

### 3.4 Three-statement forecasts from market cap

`three_statement_engine` defaulted a missing market cap to 10,000, floored it
at 100bn, and backed revenue out of it via a P/S multiple - and COGS, SG&A and
EBIT are all fractions of revenue, so the whole projected income statement
moved with the share price. It also read `data/screener_snapshot.json`
directly, bypassing the shared resolver, so it could forecast from a different
snapshot than the app was serving.

### 3.5 Unrelated defects

- The Sharpe/Calmar denominator clamp fixed in `fair_value_backtest_service`
  was present in both sibling backtest services and had been missed.
- The current year was written in as the literal `2026` at eighteen call
  sites. Correct during 2026, silently wrong from 1 January 2027.
- The `network` test marker was applied to whole modules: 283 of the 317 tests
  it excluded run fine offline and had never run in CI. That hid a broken
  `test_orchestrator_scoring` (its own docstring says it makes no network
  calls) and five stale expectations in `test_adversarial_stress`. Tiering is
  now per test; CI collection went from 735 to 1,009.

### 3.6 What the export and forecast suites were actually testing

`build_forecast_from_screener` reads a local snapshot file. Under test
isolation that file is absent, so the export and forecast suites - 51 tests
across `test_financial_model_exporter`, `test_adversarial_excel_universe_
verification` and the VN30 balance checks - were building models for invented
companies while appearing to test HPG, FPT and VCB. The VN30 test asserted the
accounting identity balances, which invented figures always do. They now run
against a `screener_snapshot` fixture with stated inputs.

---

## 4. Open items

1. **The fundamentals lake is empty.** `point_in_time` is the default and has
   nothing to read until `data/historical_fundamentals.json` is built.
   `scripts/build_historical_fundamentals.py` fetches it from VNDIRECT Finfo;
   its transformation logic is unit-tested but it has **not** been run end to
   end against the live API (this sandbox's proxy refuses that host).

2. **Filing dates are estimated.** The VNDIRECT endpoint does not expose them,
   so the builder writes quarter end + 45 days and marks
   `filing_date_is_estimated`. Real filing dates would tighten the
   point-in-time boundary.

3. **`data/pdf_lake/extracted_bctc_lake.json` is 99.7 MB and 0.4% usable.**
   Measured by `scripts/audit_bctc_lake.py`: 1,769 records, 22 with any
   extracted data, **7 with actual statement items, covering 4 symbols**.
   1,748 have `year: None`; 13 of the 22 parsed documents are
   `SCANNED_IMAGE`, which needs OCR. It is not a fundamentals source.

4. ~~**The fair-value backtest result panel has no markup.**~~ *Fixed.* The
   panel now exists as a third sub-tab of the backtest tab
   (`btFairValueSection`), defining every id `app.js` writes to, plus a
   `fundamentals_mode` selector wired through to the API parameter.
   `tests/test_frontend_element_contract.py` fails the build if app.js ever
   reads an element id the page does not define. That sweep also found five
   other reads with no markup: four are harmless fallback alternates in
   `a || b` lookup chains, but `healthOverviewContainer` is a genuinely dead
   path - `fetchCompanyHealth` and `renderCompanyHealth` have no caller and no
   container. It is recorded in the test's `KNOWN_ABSENT` map with that reason
   rather than left invisible; it should be wired to the stock-detail panel or
   deleted.

5. **Sector weight priors are still opinions.** `SECTOR_WEIGHT_PRIORS` is now
   labelled honestly rather than as "pre-calibrated IVW", and
   `scripts/calibrate_sector_weight_priors.py` will derive real ones from
   measured forward errors - but it needs the fundamentals lake from item 1.

6. **Proprietary desk flow and foreign VWAP need a real feed.** Both are now
   reported as estimated or unavailable rather than fabricated, which is
   correct but leaves the feature empty until per-session foreign volume is
   available.


## 5. Third pass: silent failures and unstable identity

### 5.1 89 exception handlers that logged nothing

`except Exception: pass` appeared 91 times across `services/`, 57 of them in
`stock_service.py`. Every one made a broken parser, a dead endpoint or a
swallowed `TypeError` indistinguishable from a symbol that legitimately has no
data. All are now `logger.debug(..., exc_info=True)`: the control flow is
unchanged - the handler still swallows - but the failure is recoverable from a
log instead of being gone. Two remain deliberately silent, marked `silent-ok:`
with a reason, because they run before the module's logger exists.

De-silencing them immediately surfaced a real defect. `stock_service` re-asserted
TLS verification by reaching into `services.unified_data_service` inside such a
handler; that import is circular from there, so the assignment never ran. It was
harmless - `tls_config` already derives `TLS_VERIFY` from the same environment
variable and defaults to verifying, and `unified_data_service` imports that value
directly - so the block was redundant as well as dead, and has been removed with
tls_config left as the single source of truth. But it had been invisible for as
long as it existed.

### 5.2 Record ids that changed on every restart

17 record identifiers were built from `abs(hash(text))` - article links,
press-release urls, disclosure titles, BCTC document keys, subsidiary and family
cluster ids. CPython salts str hashing per process, so the same article got a new
id every time the server came up and every store keyed on those ids stopped
deduplicating, accumulating the same record repeatedly.

All now use `services/stable_identity.stable_hash` (crc32: not cryptographic, and
not meant to be - it just has to be identical in every process). The old
`stock_service.deterministic_hash` is kept as a delegating alias.
`tests/test_no_silent_failures_or_unstable_ids.py` bans the builtin `hash()`
across `services/`, and verifies the property directly by running `stable_hash`
under three different `PYTHONHASHSEED` values in subprocesses - and, so the rule
does not quietly become moot, checks that builtin `hash()` really does still vary.


## 6. Fourth pass: what the third pass missed

Asked whether everything was fixed, I checked instead of answering from memory,
and the check found four things.

### 6.1 The price tautology came back through the payload

Sections 1.1 and 3.2 removed the circularity from `valuation_engine` and from
the single-symbol engine. They did not look at
`services/unified_data_service.py`, which back-solves a missing EPS, revenue,
net income or equity from market capitalisation and a sector multiple:

```python
net_income = (mcap * 1_000_000_000.0) / max(1.0, sec_med["pe"])
revenue    = (mcap * 1_000_000_000.0) / max(0.1, sec_med["ps"])
tot_eq     =  mcap * 1_000_000_000.0  / max(0.5, sec_med["pb"])
eps        = round(price / max(1.0, pe), 0)
```

That module is honest about it - it ships an `is_imputed` map and per-field
`field_provenance` tiers next to the values. `InputResolver` was not reading
them, so a tier-1 EPS arrived as a plain float and was recorded REAL. Measured
on a payload whose statements were all back-solved from market cap:

| entry price | composite FV | FV / price |
|---|---|---|
| 10,000 | 8,850 | 0.8850 |
| 20,000 | 17,701 | 0.8851 |
| 40,000 | 35,401 | 0.8850 |
| 80,000 | 70,802 | 0.8850 |

`InputResolver` now honours the payload's own verdict: a field the upstream
layer flags as imputed, or ranks below tier 2, is IMPUTED here however concrete
it looks. The same payload now produces no valuation at all, at every price,
which is the right answer for accounts derived from the price. A payload with
no provenance metadata still resolves as REAL, so nothing else changed.

### 6.2 A fabricated 15% volatility, directly under the fix for it

`fair_value_backtest_service` guarded the Sharpe denominator against being
clamped - and then handed it `ann_std = ... if len(rets) > 1 else 15.0`, with
`ann_downside_std = ann_std * 0.65`. Guarding the ratio is pointless when the
denominator itself was invented. Both are withheld now, and period returns are
computed by `_period_returns`, which skips a step with no positive base instead
of dividing by `max(prev, 1.0)`.

### 6.3 More clamped denominators, and a test that was too narrow to see them

The section-5 sweep matched only denominators *named* vol/std/dd/drawdown, so
it walked past `cagr / max(1.0, abs(max_dd))` (Calmar, in two more code paths),
`avg_win / max(1.0, avg_loss)`, `gross_gains / max(1.0, gross_losses)` with a
`99.0` sentinel for "no losses", `avg_oos_sharpe / max(0.1, avg_is_sharpe)`,
and `allocated_capital / max(1.0, entry_p)`. All now route through one
module-level `safe_ratio`, which returns None rather than a floor.

One of them was not a clamp but a tautology: the Monte Carlo Sharpe annualised
by `sqrt(n_trades / max(1, n_trades / 12.0))`, which is exactly `sqrt(12)` for
any n >= 12 - a hardcoded monthly cadence in the shape of a calculation. It now
measures trades per year from the span the trades actually cover, and declines
to annualise when the dates cannot support it.

The test now matches the *shape* (any division by `max()` with a literal),
exempting count guards like `x / max(1, len(trades))` - where the numerator is
zero whenever the denominator would be - and listing the two ranking sort keys
that legitimately floor a P/E, so a new one has to be justified in the file.

### 6.4 The section-5 scope stopped at services/

23 silent handlers remained in `server.py`, `run_app.py` and `scripts/`,
including one that dropped `factor_weights` from a screener response with no
trace, and one that lost the RRG disk cache silently. All de-silenced; the
tests now sweep every production file in the repository rather than
`services/` alone, and the element-contract test sweeps every bundled script
rather than `app.js` alone.

One consequence worth stating: `win_rate_pct` no longer reports 50.0 for a run
with no trades, but it does still report 0.0 rather than None - read together
with `total_trades`, which sits beside it. `profit_factor`, Calmar, Sharpe,
Sortino, the payoff ratio and walk-forward efficiency are all withheld (None)
when undefined, and `static/js/app.js` renders that as "n/a" rather than the
string "null".
