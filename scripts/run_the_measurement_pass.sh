#!/usr/bin/env bash
# One pass that answers every open question about the data at once.
#
# Written as a script rather than as workflow steps because two workflows
# need it: the real one (fundamentals_lake.yml) and the bootstrap that
# borrows the screener's dispatch registration until that one reaches the
# default branch. A 150-line job copied into both is the same defect this
# codebase spent a day removing.
#
# The order is forced by dependencies, not by preference:
#
#   listing + screener snapshot   everything downstream needs the universe
#   historical prices             the backtest cannot run without them
#   fundamentals lake + probe     one fetch, two outputs
#   candidate scoring             reads the probe, fetches nothing
#   backtest sweep                reads all three lakes
#   coverage audit                reads the snapshot
#
# Stages that only measure are allowed to fail without taking the pass
# down: losing the backtest to a missing price lake must not also lose the
# lake that was already built. Stages that produce inputs are not.
#
# Every piped stage sets pipefail inside its own shell. Without it the
# exit status is tee's, which is always zero - the measurement dies, the
# summary reports that every stage completed, and the run is green.
set -uo pipefail

DATA="${DATA_LOCAL_DIR:?DATA_LOCAL_DIR must be set}"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
LIMIT="${LAKE_LIMIT:-0}"
LAGS="${BACKTEST_LAGS:-20 30 45 60 90}"
mkdir -p "$DATA"

FAILED=()

stage() {
  local name="$1"; shift
  echo "::group::$name"
  local started=$SECONDS
  if "$@"; then
    echo "  ✅ $name ($((SECONDS - started))s)"
  else
    local code=$?
    echo "  ❌ $name failed with $code after $((SECONDS - started))s"
    FAILED+=("$name")
  fi
  echo "::endgroup::"
}

# --- inputs ---------------------------------------------------------------
# The universe. Refuses rather than publishing a thin snapshot, so a
# failure here is fatal to everything after it and the pass says so.
stage "screener universe" \
  python scripts/sync_unified_market_data.py

# Never run on a runner before, and it takes no limit, so its cost is the
# one unknown in this pass. It is measured, not trusted.
stage "historical prices" \
  python scripts/sync_historical_prices.py

# --- the lake, and the probe that judges two of its fields ----------------
LAKE_ARGS=(--universe --out "$DATA/historical_fundamentals.json"
           --diagnostics-out "$DATA/code_candidates_probe.json")
if [ "$LIMIT" != "0" ]; then LAKE_ARGS+=(--limit "$LIMIT"); fi
stage "fundamentals lake" \
  python scripts/build_historical_fundamentals.py "${LAKE_ARGS[@]}"

# --- measurements ---------------------------------------------------------
# Everything below only reads. Each appends to the step summary, which is
# the one channel that does not depend on reading a job log from its tail.

if [ -f "$DATA/code_candidates_probe.json" ]; then
  stage "score capex and depreciation codes" \
    bash -c "set -o pipefail; python scripts/score_code_candidates.py \
      '$DATA/code_candidates_probe.json' \
      --json '$DATA/code_candidates.json' | tee -a '$SUMMARY'"
fi

# Off by default. FiinGroup, the one route here that this codebase does
# not already have, is behind a paid plan - so the probe cannot answer
# the question it was written for, and spending requests on it every pass
# would be spending them on a vendor we cannot use. The script is kept
# rather than deleted: if a plan is ever bought, the comparison it makes
# (which of the vendor's named rows carries each of our numbers) is the
# check on the code map that VNDIRECT cannot provide.
#
#   PROBE_SOURCES=1  to run it.
if [ "${PROBE_SOURCES:-0}" = "1" ]; then
stage "probe sources we do not use" \
  bash -c "set -o pipefail; python scripts/probe_new_sources.py \
    --lake '$DATA/historical_fundamentals.json' \
    --json '$DATA/new_sources.json' | tee -a '$SUMMARY'"
fi

stage "backtest sweep" \
  bash -c "set -o pipefail; python scripts/measure_the_backtest.py \
    --lags $LAGS --json '$DATA/backtest_sweep.json' | tee -a '$SUMMARY'"

# Last, deliberately. Whatever is printed last is the only thing
# guaranteed to be readable from a log tail, and the coverage headline is
# the number the exercise is measured by.
stage "coverage audit" \
  bash -c "set -o pipefail; python scripts/audit_valuation_coverage.py \
    --show-blocked 60 --json '$DATA/coverage.json' | tee -a '$SUMMARY'"

# --- what happened --------------------------------------------------------
{
  echo
  echo "## Measurement pass"
  echo
  for f in "${FAILED[@]:-}"; do
    [ -n "$f" ] && echo "- ❌ **$f** did not complete"
  done
  if [ ${#FAILED[@]} -eq 0 ]; then echo "- every stage completed"; fi
  echo
  echo "| file | bytes |"
  echo "|---|---:|"
  for f in historical_fundamentals screener_snapshot historical_prices \
           coverage backtest_sweep code_candidates code_candidates_probe \
           new_sources; do
    if [ -f "$DATA/$f.json" ]; then
      echo "| $f.json | $(wc -c < "$DATA/$f.json") |"
    else
      echo "| $f.json | **missing** |"
    fi
  done
} | tee -a "$SUMMARY"

# A pass whose inputs failed produced no measurement, and should not
# report success. A pass that only lost a measurement still delivered the
# lakes, and should.
for f in "${FAILED[@]:-}"; do
  case "$f" in
    "screener universe"|"historical prices"|"fundamentals lake") exit 1 ;;
  esac
done
exit 0
