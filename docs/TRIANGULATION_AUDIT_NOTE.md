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

## 3. Open items

1. **The fundamentals lake is empty.** `point_in_time` is the default and has
   nothing to read until `data/historical_fundamentals.json` is built.
   `scripts/build_historical_fundamentals.py` fetches it from VNDIRECT Finfo;
   it has unit-tested transformation logic but has **not** been run end to end
   against the live API.

2. **Filing dates are estimated.** The VNDIRECT endpoint does not expose them,
   so the builder writes quarter end + 45 days and marks
   `filing_date_is_estimated`. Real filing dates would tighten the
   point-in-time boundary and should replace the estimate when available.

3. **`data/pdf_lake/extracted_bctc_lake.json` is 104 MB and 98.7% empty** -
   1,769 records, 22 with non-empty `extracted_data`, 1,748 with `year: None`.
   It is not a usable fundamentals source in its current state.

4. **The fair-value backtest result panel has no markup.** `fvBtWinnerTitle`,
   `fvBtYearlyTableBody` and the rest are read by `static/js/app.js` but exist
   nowhere in `static/index.html`, so that render path writes into nothing.

5. **Sector weight priors are undocumented opinions.** `SECTOR_WEIGHT_PRIORS`
   is labelled "Pre-calibrated" with no derivation anywhere in the repository.
   The dilution bug is fixed, but the numbers themselves still need a stated
   basis or an honest relabelling.

6. **Seven tests pass only in full-suite order.** Two in
   `test_orchestrator_scoring.py` and five in `test_adversarial_stress.py` fail
   when run in isolation, on unmodified code. Pre-existing; not investigated.
