"""
Quant Scoring Engine: percentile-quintile scorer with corrected tie semantics.

Fixes a verified production defect: 721 of 1526 stocks (47.2%) shared ONE
identical composite score (76.6). Root cause: the inline scorer inside
``sync_unified_screener_universe`` used ``count(x <= val)/n`` percentiles,
so mass-imputed (tied) factor values all collapsed to identical pillar
percentiles and identical composites.

Design decisions
----------------
1. MID-RANK percentiles: ``(strictly_less + 0.5 * equal) / n * 100`` for
   higher-is-better factors, mirrored for lower-is-better ones. Tied values
   share the midpoint of their rank block instead of all receiving the
   maximum rank (which the old ``count(x <= val)`` gave them). A single
   stock scores 50.0; the maximum value scores ``(n-0.5)/n*100``.

2. ANTI-TIE COMPOSITE: computed at FULL precision from the four pillar
   percentiles (weights unchanged: .35/.25/.20/.20), then a small,
   CENTERED tie-break component is folded in::

        composite_raw = clamp(0.35g + 0.25q + 0.20h + 0.20v
                              + (tiebreak_pct - 50.0) * 0.02, 0, 100)
        composite     = round(composite_raw, 4)

    ``tiebreak_pct`` is an equally-weighted AVERAGE of the mid-rank
    percentiles of every secondary REAL component available on the record
    (see TIEBREAK_FIELDS). Because it is a single averaged percentile with
    ONE coefficient, the adjustment is capped at exactly +/-1 point
    regardless of how many components resolve (7 today).

    HONEST DISPERSION SEMANTICS (NO GUARANTEE): besides the four
    fundamental secondaries, the average includes log10(market_cap),
    change_pct momentum, and log10(price) to disperse
    INFORMATIONALLY-DEGENERATE records -- sector-imputed stocks whose
    primary factors AND fundamental secondaries collapse to identical
    constants -- using REAL reported TradingView values that still vary
    across them. They are ORDERING AIDS, not alpha factors: their combined
    weight (<= +/-1 composite point via the shared 0.02 coefficient) is
    tiny versus the pillar weights (each pillar moves the composite by up
    to 20-35 points).

    Dispersion holds UNLESS one of two documented conditions occurs:

    (a) FULLY INFORMATIONALLY IDENTICAL RECORDS: records whose resolved
        raw component tuples are identical everywhere may legitimately
        still tie; that residual is documented and tolerated.

    (b) COUPLED-COMPONENT CANCELLATION: two components can be
        deterministic inverses/proxies of each other (e.g. fcf_ttm imputed
        proportional to market_cap makes __fcf_yield__ track or exactly
        mirror __log10_mcap__), so their percentile contributions cancel
        in the unweighted average. Both mechanisms below mitigate this:

        * MIRROR / DUPLICATE / DEGENERATE DEDUP (before averaging): each
          secondary's full percentile column is checked against every
          already-kept component; a column that equals a kept column
          elementwise within MIRROR_EPSILON (1e-9), or satisfies
          p_i == 100 - p_j elementwise (exact mirror), is dropped -- as is
          any constant (zero-variance) column. At least the first
          informative component survives. Every drop is recorded in
          ``LAST_SCORING_DIAGNOSTICS["dropped_components"]`` with its
          reason and emitted via module debug logging.

        * LEXICOGRAPHIC DISPERSION FLOOR (belt-and-braces): after the
          fold, any residual tie-group on the published 4-decimal grid
          whose members carry DIFFERING resolved raw component tuples is
          dispersed deterministically: members are ordered lexicographically
          by their unique raw tuple (None sorts lowest) and shifted by
          ``1e-4 * (2*lex_rank - (n_unique-1))`` -- i.e. integer multiples
          of one published grid step, centered on the group (twice the
          half-centered 1e-4*(lex_rank-(g-1)/2) spacing so steps survive
          the 4-decimal rounding grid). Total displacement stays below
          0.01 composite points even for ~100-member groups; it injects no
          randomness and uses only real resolved values. Members sharing
          an identical raw tuple receive the same shift and remain tied.

    The centered fold preserves primary-factor ordering almost everywhere
    while separating stocks whose primary factors are identical (mass
    imputation); a median secondary shifts nothing. Ordering is fully
    deterministic: every input is a pure function of the universe
    snapshot. Published composite stays in [0, 100].

3. QUANTILE ASSIGNMENT BY RANK (not fixed score thresholds): stocks are
   sorted by composite descending (ties broken by symbol for total
   determinism) and cut into five bands using sequential index math::

       size_band_k = ceil(remaining / remaining_bands), starting from Q1.

   HONEST BEHAVIOR NOTE: because each band takes the CEILING of what is
   left, any indivisible remainder lands in the TOP bands — e.g. n=7 cuts
   as 2/2/1/1/1 and n=6 as 2/1/1/1/1, so Q1 can be several members larger
   than Q5 at small n. Band sizes stay non-increasing from Q1 to Q5 and
   every band IS populated whenever n >= 5. Fixed thresholds (>=80 => Q1)
   are gone: they were meaningless when hundreds of stocks shared one score.

4. EDGE CASES: empty universe is a silent no-op; missing / None / NaN /
   inf / bool fields contribute a neutral 50.0 percentile; a corrupt
   (non-dict) ``_metadata`` is treated as absent; a tie-break field that
   is unavailable universe-wide or on a given record is excluded from that
   record's tie-break average (if none are available the tie-break term is
   exactly 0.0 via the centering); non-dict records are rejected with a
   ValueError naming the symbol; n < 5 assigns bands only while stocks
   remain.

Consumers continue to read ``stock["percentiles"]`` with the exact shape
published today: growth, quality, health, valuation, composite, quintile,
quintile_label, quintile_color, quintile_badge (Vietnamese labels preserved).

Performance: percentiles are evaluated against per-factor PRE-SORTED arrays
via ``bisect`` (O(log n) per lookup, O(n log n + k*n log n) overall for k
factors), replacing the previous O(k * n^2) pairwise scans. A 1526-record
universe scores in well under a second.
"""

import logging
import math
from bisect import bisect_left, bisect_right
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

_logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Constants (must match the labels/colors/badges already shipped to the UI)
# --------------------------------------------------------------------------

QUINTILE_META: Dict[str, Tuple[str, str, str]] = {
    "Q1": ("Tinh Hoa (Top 20%)", "#10b981", "badge-q1"),
    "Q2": ("Tốt (Khá)", "#3b82f6", "badge-q2"),
    "Q3": ("Trung Bình", "#eab308", "badge-q3"),
    "Q4": ("Yếu", "#f97316", "badge-q4"),
    "Q5": ("Rủi Ro Cao", "#ef4444", "badge-q5"),
}

NEUTRAL_PERCENTILE: float = 50.0

# Number of decimals on the PUBLISHED composite grid. Must stay coarse
# enough to hide float noise but fine enough that the anti-tie separation
# (~0.02 * 100/n per rank position) survives rounding.
COMPOSITE_DECIMALS: int = 4

# Coefficient on the CENTERED tie-break percentile: max shift = 50 * 0.02 = 1.
TIEBREAK_COEFFICIENT: float = 0.02

# Elementwise tolerance for exact-mirror / exact-duplicate column detection:
# p_i == 100 - p_j (mirror) or p_i == p_j (duplicate) within this epsilon.
MIRROR_EPSILON: float = 1e-9

# Grid step used by the lexicographic dispersion floor; equal to one
# published-composite grid step, so shifts survive COMPOSITE_DECIMALS.
FLOOR_STEP: float = 1e-4

# Cross-sectional winsorization of PRIMARY factor inputs before percentile
# ranking: each column's resolved values are clipped to its own empirical
# [1st, 99th] percentile band, intersected with hard domain caps below.
# Ranking input only -- raw record fields are never mutated, so display
# keeps the reported values. Small universes (< WINSOR_MIN_N) skip the
# percentile clip and fall back to domain caps alone.
WINSOR_QUANTILE: float = 0.01

WINSOR_MIN_N: int = 100

DOMAIN_CAPS: Dict[str, Tuple[float, float]] = {
    "rev_5y_growth": (-99.0, 500.0),
    "rev_3y_cagr": (-99.0, 500.0),
    "pat_3y_cagr": (-99.0, 500.0),
    "roe": (-100.0, 200.0),
    "op_margin": (-100.0, 200.0),
    "roa": (-100.0, 200.0),
    "current_ratio": (0.0, 50.0),
    "de_ratio": (-10.0, 100.0),
    "peg": (-100.0, 100.0),
    "pe": (-100.0, 300.0),
}

# Diagnostics from the most recent score_universe run: which tie-break
# components were kept / dropped (with reasons) and how many residual
# tie-groups needed the lexicographic dispersion floor.
LAST_SCORING_DIAGNOSTICS: Dict[str, Any] = {}

# Primary scoring factors: (field_name, higher_is_better)
PRIMARY_FACTORS: List[Tuple[str, bool]] = [
    ("rev_5y_growth", True),
    ("rev_3y_cagr", True),
    ("pat_3y_cagr", True),
    ("roe", True),
    ("op_margin", True),
    ("roa", True),
    ("de_ratio", False),
    ("current_ratio", True),
    ("peg", False),
    ("pe", False),
]

# Secondary REAL fields used ONLY for the anti-tie component. This constant
# is authoritative: the scoring loop iterates over it (no hardcoding).
# Synthetic keys prefixed "__" have dedicated resolvers below;
# plain keys resolve straight off the record.
#
# The three trailing size/momentum components are ORDERING AIDS, not alpha
# factors: they resolve REAL reported values (log10 market cap, change
# momentum, log10 price) that vary even across sector-imputed stocks whose
# fundamental profile is otherwise identical, dispersing them
# deterministically. Their combined influence is capped at +/-1 composite
# point. Coupled components (exact mirrors / duplicates / constants) are
# removed before averaging -- see _select_tiebreak_components.
TIEBREAK_FIELDS: List[Tuple[str, bool]] = [
    ("dividend_yield", True),
    ("roic", True),
    ("__fcf_yield__", True),
    ("__dq_score__", True),
    ("__log10_mcap__", True),
    ("__change_pct__", True),
    ("__log10_price__", True),
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _finite(value: Any) -> Optional[float]:
    """Return value as finite float, else None (covers None / NaN / inf / junk)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    f = float(value)
    return f if math.isfinite(f) else None


def _midrank_percentile(sorted_values: List[float], target: float,
                        higher_is_better: bool) -> float:
    """
    Mid-rank empirical percentile of ``target`` within a PRE-SORTED array,
    in [0, 100]. O(log n) via bisect: strictly_less / equal counts come
    from the insertion brackets instead of full scans.
    """
    lo = bisect_left(sorted_values, target)
    hi = bisect_right(sorted_values, target)
    equal = hi - lo
    n = len(sorted_values)
    if higher_is_better:
        strictly_less = lo
    else:
        strictly_less = n - hi
    pct = ((strictly_less + 0.5 * equal) / n) * 100.0
    return min(100.0, max(0.0, pct))


def empirical_percentile(
    values: List[float],
    target: float,
    higher_is_better: bool = True,
) -> float:
    """
    Mid-rank empirical percentile of ``target`` within ``values``, in [0, 100].

    rank = (strictly_less + 0.5 * equal) for higher_is_better, mirrored
    (strictly_greater + 0.5 * equal) otherwise; percentile = rank / n * 100,
    clamped to [0, 100]. Non-finite entries (None, NaN, inf) are filtered
    from ``values``; an unusable target or empty/unusable population returns
    the neutral 50.0.

    This is the CORRECTED tie semantics: tied observations sit at the middle
    of their rank block rather than all claiming the top rank as the old
    ``count(x <= val)/n`` formula did.
    """
    t = _finite(target)
    if t is None:
        return NEUTRAL_PERCENTILE
    valid = sorted(v for v in (_finite(x) for x in values) if v is not None)
    if not valid:
        return NEUTRAL_PERCENTILE
    return _midrank_percentile(valid, t, higher_is_better)


def _resolve_factor(stock: Dict, field: str) -> Optional[float]:
    return _finite(stock.get(field))


def _resolve_fcf_yield(stock: Dict) -> Optional[float]:
    """fcf_ttm normalized by market_cap (higher is better)."""
    fcf = _finite(stock.get("fcf_ttm"))
    mcap = _finite(stock.get("market_cap"))
    if fcf is None or mcap is None or mcap <= 0:
        return None
    return fcf / mcap


def _resolve_dq_score(stock: Dict) -> Optional[float]:
    """data_quality_score from _metadata; corrupt/non-dict metadata => None."""
    meta = stock.get("_metadata")
    if not isinstance(meta, dict):
        return None
    return _finite(meta.get("data_quality_score"))


def _resolve_log10_mcap(stock: Dict) -> Optional[float]:
    """log10 market_cap (higher is better); non-positive/missing skipped."""
    mcap = _finite(stock.get("market_cap"))
    if mcap is None or mcap <= 0:
        return None
    return math.log10(mcap)


def _resolve_change_pct_momentum(stock: Dict) -> Optional[float]:
    """change_pct used directly (higher is better); missing/corrupt skipped."""
    return _finite(stock.get("change_pct"))


def _resolve_log10_price(stock: Dict) -> Optional[float]:
    """log10 price (higher is better); non-positive/missing skipped."""
    price = _finite(stock.get("price"))
    if price is None or price <= 0:
        return None
    return math.log10(price)


_TIEBREAK_RESOLVERS: Dict[str, Callable[[Dict], Optional[float]]] = {
    "dividend_yield": lambda s: _resolve_factor(s, "dividend_yield"),
    "roic": lambda s: _resolve_factor(s, "roic"),
    "__fcf_yield__": _resolve_fcf_yield,
    "__dq_score__": _resolve_dq_score,
    "__log10_mcap__": _resolve_log10_mcap,
    "__change_pct__": _resolve_change_pct_momentum,
    "__log10_price__": _resolve_log10_price,
}


def _pillar_weights() -> List[Tuple[List[str], List[float]]]:
    """
    Factor composition of each pillar, weights summing to 1.0:
      growth    = .40*rev_5y + .30*rev_3y_cagr + .30*pat_3y_cagr
      quality   = .40*roe + .35*op_margin + .25*roa
      health    = .60*de(lower better) + .40*current_ratio
      valuation = .60*peg(lower better) + .40*pe(lower better)
    """
    return [
        (["rev_5y_growth", "rev_3y_cagr", "pat_3y_cagr"], [0.40, 0.30, 0.30]),
        (["roe", "op_margin", "roa"], [0.40, 0.35, 0.25]),
        (["de_ratio", "current_ratio"], [0.60, 0.40]),
        (["peg", "pe"], [0.60, 0.40]),
    ]


def _validate_records(stocks: Dict[str, Dict]) -> None:
    """Reject non-dict records up front, naming the offending symbol."""
    for sym, s in stocks.items():
        if not isinstance(s, dict):
            raise ValueError(
                f"score_universe: record for symbol {sym!r} is "
                f"{type(s).__name__}, expected dict"
            )


def _select_tiebreak_components(
    names: List[str],
    pct_columns: Dict[str, List[float]],
    raw_columns: Dict[str, List[Optional[float]]],
) -> Tuple[List[str], Dict[str, str]]:
    """
    Greedy anti-cancellation pass over the tie-break components (declared
    order). Returns (kept_names, dropped{name: reason}).

    Dropped categories:
      * degenerate   -- zero-variance percentile column among resolved
                        records (constant field or unavailable
                        universe-wide): carries no ordering info.
      * exact mirror -- p_i == 100 - p_j elementwise (within MIRROR_EPSILON)
                        versus an already-kept component, compared on every
                        record where BOTH resolve. This is what happens when
                        two fields are deterministic inverses, e.g. fcf_ttm
                        imputed proportional to market_cap makes __fcf_yield__
                        the mirror of __log10_mcap__; left in, the pair
                        cancels exactly in the unweighted average.
      * duplicate    -- p_i == p_j elementwise versus a kept component.

    At least the first non-degenerate component is always kept.
    """
    kept: List[str] = []
    dropped: Dict[str, str] = {}
    eps = MIRROR_EPSILON
    n_rec = len(next(iter(raw_columns.values()))) if raw_columns else 0

    for name in names:
        col = pct_columns[name]
        avail = [v is not None for v in raw_columns[name]]
        resolved_vals = [v for v, a in zip(col, avail) if a]
        if not resolved_vals or all(
            abs(v - resolved_vals[0]) <= eps for v in resolved_vals
        ):
            dropped[name] = "degenerate (constant/unavailable column)"
            continue

        reason: Optional[str] = None
        for k in kept:
            kcol = pct_columns[k]
            pairs = [
                (col[i], kcol[i])
                for i in range(n_rec)
                if avail[i] and raw_columns[k][i] is not None
            ]
            if not pairs:
                continue  # no co-resolved records: cannot establish coupling
            if all(abs(p + q - 100.0) <= eps for p, q in pairs):
                reason = f"exact mirror of kept component '{k}'"
                break
            if all(abs(p - q) <= eps for p, q in pairs):
                reason = f"exact duplicate of kept component '{k}'"
                break
        if reason:
            dropped[name] = reason
            _logger.debug("tie-break component %r dropped: %s", name, reason)
        else:
            kept.append(name)
    return kept, dropped


def _raw_component_tuple(
    vals: Dict[str, Optional[float]], names: List[str]
) -> Tuple[float, ...]:
    """Resolved RAW component values as a sortable tuple; None sorts lowest."""
    return tuple(
        vals[name] if vals[name] is not None else float("-inf")
        for name in names
    )


def _apply_dispersion_floor(
    composites: Dict[str, float],
    raw_tuples: Dict[str, Tuple[float, ...]],
) -> int:
    """
    Belt-and-braces lexicographic dispersion floor. Mutates ``composites``
    in place. Any tie-group (equal published composite) whose members carry
    DIFFERING raw tuples is ordered by unique tuple (lexicographic; None
    already mapped to -inf) and shifted by::

        FLOOR_STEP * (2*lex_rank - (n_unique - 1))

    i.e. integer multiples of one 4-decimal grid step, centered on the
    group (twice the half-centered 1e-4*(rank-(g-1)/2) spacing so adjacent
    members stay >= one grid step apart AFTER rounding to 4 decimals).
    Near the [0, 100] bounds the WHOLE group is translated inward by the
    minimum amount that restores headroom, preserving exact inter-member
    spacing instead of clamping outward shifts (clamping would fuse
    members with differing raw tuples back into ties). Span grows as
    2*FLOOR_STEP*(u-1); members with IDENTICAL raw tuples get the same
    shift and remain tied: fully-informationally-identical records
    legitimately tie.
    Returns the number of groups that were dispersed.
    """
    groups: Dict[float, List[str]] = {}
    for sym, comp in composites.items():
        groups.setdefault(comp, []).append(sym)

    dispersed = 0
    for base, members in groups.items():
        if len(members) < 2:
            continue
        unique_tuples = sorted({raw_tuples[sym] for sym in members})
        if len(unique_tuples) < 2:
            continue  # informationally identical: legitimate tie
        dispersed += 1
        rank_of = {t: r for r, t in enumerate(unique_tuples)}
        u = len(unique_tuples)
        half_span = FLOOR_STEP * (u - 1)
        offset = 0.0
        if base + half_span > 100.0:
            offset = 100.0 - (base + half_span)
        elif base - half_span < 0.0:
            offset = -(base - half_span)
        for sym in members:
            shift = FLOOR_STEP * (2 * rank_of[raw_tuples[sym]] - (u - 1)) + offset
            composites[sym] = round(base + shift, COMPOSITE_DECIMALS)
    return dispersed


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def score_universe(stocks: Dict[str, Dict]) -> None:
    """
    Score every stock in place, adding ``stock["percentiles"]``.

    Keys added (same shape consumers already read): growth, quality, health,
    valuation, composite, quintile, quintile_label, quintile_color,
    quintile_badge. Composite is published rounded to COMPOSITE_DECIMALS
    (4); pillar percentiles to 1 decimal for display. See module docstring
    for the anti-tie composite and rank-based quintile mathematics.
    Raises ValueError if any record is not a dict.
    """
    if not stocks:
        return

    _validate_records(stocks)

    # --- Resolve every factor once per record ---------------------------
    primary_names = [name for name, _ in PRIMARY_FACTORS]
    tb_names = [name for name, _ in TIEBREAK_FIELDS]
    hib_map: Dict[str, bool] = dict(PRIMARY_FACTORS)
    hib_map.update(TIEBREAK_FIELDS)

    factor_names = primary_names + tb_names
    columns_raw: Dict[str, List[float]] = {name: [] for name in factor_names}
    resolved: Dict[str, Dict[str, Optional[float]]] = {}

    for sym, s in stocks.items():
        vals: Dict[str, Optional[float]] = {}
        for name in factor_names:
            if name in primary_names:
                v = _resolve_factor(s, name)
            else:
                v = _TIEBREAK_RESOLVERS[name](s)
            vals[name] = v
            if v is not None:
                columns_raw[name].append(v)
        resolved[sym] = vals

    # --- Winsorize PRIMARY ranking inputs (display keeps raw values) -----
    # Clip each primary factor's resolved values to the cross-sectional
    # [1st, 99th] percentile band intersected with DOMAIN_CAPS, so a single
    # implausible filing cannot dominate the percentile tails. Only the
    # in-memory ranking copy is mutated; tie-break components and the raw
    # record fields are left untouched.
    winsor_bounds: Dict[str, Tuple[float, float]] = {}
    for name in primary_names:
        col = columns_raw[name]
        dlo, dhi = DOMAIN_CAPS.get(name, (-math.inf, math.inf))
        if len(col) >= WINSOR_MIN_N:
            srt = sorted(col)
            k = max(1, int(round(WINSOR_QUANTILE * len(srt))))
            lo = max(srt[k - 1], dlo)
            hi = min(srt[len(srt) - k], dhi)
        else:
            lo, hi = dlo, dhi
        winsor_bounds[name] = (lo, hi) if lo <= hi else (dlo, dhi)
    winsorized_symbols: Dict[str, bool] = {}
    for sym, vals in resolved.items():
        clipped = False
        for name in primary_names:
            v = vals[name]
            if v is not None:
                lo, hi = winsor_bounds[name]
                vals[name] = min(max(v, lo), hi)
                if vals[name] != v:
                    clipped = True
        winsorized_symbols[sym] = clipped

    # --- Pre-sort each column once (O(n log n)); lookups are O(log n) ---
    sorted_columns: Dict[str, List[float]] = {
        name: sorted(col) for name, col in columns_raw.items()
    }

    def _pct(name: str, value: Optional[float]) -> float:
        col = sorted_columns[name]
        if value is None or not col:
            return NEUTRAL_PERCENTILE
        return _midrank_percentile(col, value, hib_map[name])

    # --- Anti-cancellation pass over tie-break components ----------------
    # Build each component's FULL percentile column once, then drop any
    # column that is constant (degenerate), an exact mirror of a kept one,
    # or an exact duplicate of a kept one -- see module docstring (b).
    tb_pct_columns: Dict[str, List[float]] = {}
    tb_raw_columns: Dict[str, List[Optional[float]]] = {}
    for name in tb_names:
        tb_pct_columns[name] = [_pct(name, resolved[sym][name])
                                for sym in stocks.keys()]
        tb_raw_columns[name] = [resolved[sym][name] for sym in stocks.keys()]

    kept_tb, dropped_tb = _select_tiebreak_components(
        tb_names, tb_pct_columns, tb_raw_columns
    )

    pillar_specs = _pillar_weights()
    composites: Dict[str, float] = {}
    pillar_display: Dict[str, Dict[str, float]] = {}

    for sym, s in stocks.items():
        vals = resolved[sym]

        # --- Pillar percentiles at FULL precision -----------------------
        pillar_values: List[float] = []
        for fields, weights in pillar_specs:
            pv = 0.0
            for field, w in zip(fields, weights):
                pv += w * _pct(field, vals[field])
            pillar_values.append(pv)

        g, q, h, v = pillar_values
        composite_primary = 0.35 * g + 0.25 * q + 0.20 * h + 0.20 * v

        # --- Centered anti-tie component (secondary REAL fields) --------
        # Only anti-cancellation-SURVIVING components enter the average;
        # unavailable-on-this-record kept components are still excluded.
        tb_parts: List[float] = []
        for name in kept_tb:
            raw = vals[name]
            if raw is None:
                continue  # unavailable on this record: exclude from average
            if not columns_raw[name]:
                continue  # unavailable universe-wide
            tb_parts.append(_pct(name, raw))
        tiebreak_pct = sum(tb_parts) / len(tb_parts) if tb_parts else 50.0

        # --- Fold, clamp, publish on the 4-decimal grid -----------------
        composite_raw = min(100.0, max(0.0, composite_primary +
                                       TIEBREAK_COEFFICIENT * (tiebreak_pct - 50.0)))
        composites[sym] = round(composite_raw, COMPOSITE_DECIMALS)
        pillar_display[sym] = {
            "growth": round(g, 1),
            "quality": round(q, 1),
            "health": round(h, 1),
            "valuation": round(v, 1),
        }

    # --- Lexicographic dispersion floor (belt-and-braces) ----------------
    # Any residual tie-group with DIFFERING raw component tuples is
    # dispersed deterministically (< 0.01 point shift); identical-tuple
    # groups legitimately stay tied. See module docstring.
    raw_tuples: Dict[str, Tuple[float, ...]] = {
        sym: _raw_component_tuple(resolved[sym], tb_names)
        for sym in stocks.keys()
    }
    floor_groups = _apply_dispersion_floor(composites, raw_tuples)

    LAST_SCORING_DIAGNOSTICS.clear()
    LAST_SCORING_DIAGNOSTICS.update({
        "records": len(stocks),
        "kept_components": list(kept_tb),
        "dropped_components": dict(dropped_tb),
        "dispersion_floor_groups": floor_groups,
    })

    # --- Rank-based quintile assignment ----------------------------------
    # Sort by composite desc, symbol asc: fully deterministic ordering even
    # under residual ties (residual ties are rare thanks to the tie-break).
    order = sorted(stocks.keys(), key=lambda sym: (-composites[sym], sym))

    assignments: Dict[str, str] = {}
    start = 0
    remaining = len(order)
    for band in range(5):
        if remaining <= 0:
            break
        # Each band takes the ceiling of what is left; any indivisible
        # remainder therefore lands in the TOP bands (Q1 first). Guarantees
        # all 5 bands are populated whenever n >= 5.
        size = min(remaining, math.ceil(remaining / (5 - band)))
        quintile = f"Q{band + 1}"
        for sym in order[start:start + size]:
            assignments[sym] = quintile
        start += size
        remaining -= size

    # --- Publish ----------------------------------------------------------
    for sym, s in stocks.items():
        quintile = assignments.get(sym, "Q5")
        label, color, badge = QUINTILE_META[quintile]
        p = dict(pillar_display[sym])
        p["composite"] = composites[sym]
        p["quintile"] = quintile
        p["quintile_label"] = label
        p["quintile_color"] = color
        p["quintile_badge"] = badge
        if winsorized_symbols.get(sym):
            p["winsorized"] = True
        s["percentiles"] = p


def largest_tie_cluster(stocks: Dict[str, Dict]) -> int:
    """
    Size of the biggest group of stocks sharing an identical PUBLISHED
    composite score (the 4-decimal grid). 0 for an empty universe.
    Diagnostic for the mass-tie defect this module fixes (was 721 in
    production).
    """
    counts: Counter = Counter()
    for s in stocks.values():
        comp = _finite((s.get("percentiles") or {}).get("composite"))
        if comp is not None:
            counts[round(comp, COMPOSITE_DECIMALS)] += 1
    return max(counts.values(), default=0)


# --------------------------------------------------------------------------
# Guru strategy matchers (mirror services/backtest_service.evaluate_guru_model)
# --------------------------------------------------------------------------

GURU_EXCLUDED_SECTORS_GREENBLATT: set = {"VNFIN", "VNUTI"}

GURU_CONSENSUS_MIN_APPROVALS: int = 2

GURU_STRATEGY_KEYS: List[str] = [
    "guru_magic_formula_greenblatt",
    "guru_piotroski_fscore",
    "guru_zweig_conservative_growth",
    "guru_cornerstone_growth_oshaughnessy",
    "guru_cornerstone_value_oshaughnessy",
    "guru_neff_total_return",
    "novy_marx_quality_value",
    "gray_quantitative_value_qval",
]


def _guru_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def build_guru_context(stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    recs = [s for s in stocks if isinstance(s, dict)]

    def _num(v: Any) -> bool:
        return _guru_num(v)

    caps = sorted([float(c["market_cap"]) for c in recs if _num(c.get("market_cap"))])
    cap_median = caps[len(caps) // 2] if caps else 0.0
    cap_mean = round(sum(caps) / len(caps), 2) if caps else 0.0

    pes = sorted([float(c["pe"]) for c in recs if _num(c.get("pe")) and c.get("pe", 0) > 0])
    pe_median = pes[len(pes) // 2] if pes else 15.0

    elig_roic = []
    elig_ey = []
    for c in recs:
        if c.get("sector_code") in GURU_EXCLUDED_SECTORS_GREENBLATT:
            continue
        if not (_num(c.get("market_cap")) and c.get("market_cap", 0) >= cap_median):
            continue
        if _num(c.get("roic")) and c.get("roic", 0) > 0 and _num(c.get("pe")) and c.get("pe", 0) > 0:
            elig_roic.append(float(c["roic"]))
            elig_ey.append(100.0 / float(c["pe"]))
    elig_roic.sort()
    elig_ey.sort()
    roic_median = elig_roic[len(elig_roic) // 2] if elig_roic else 7.0
    ey_median = elig_ey[len(elig_ey) // 2] if elig_ey else 7.0

    pbs = sorted([float(c["pb"]) for c in recs if _num(c.get("pb")) and c.get("pb", 0) > 0])
    pb_q20 = pbs[min(len(pbs) - 1, int(len(pbs) * 0.2))] if pbs else 1.0

    divs = sorted([float(c["dividend_yield"]) for c in recs if _num(c.get("dividend_yield")) and c.get("dividend_yield", 0) > 0])
    div_median = divs[len(divs) // 2] if divs else 2.0

    by_sector: Dict[str, List[float]] = {}
    for c in recs:
        sec = c.get("sector_code")
        if sec and _num(c.get("de_ratio")):
            by_sector.setdefault(sec, []).append(float(c["de_ratio"]))
    sector_de_median = {}
    for sec, vals in by_sector.items():
        vals.sort()
        sector_de_median[sec] = vals[len(vals) // 2]

    return {
        "cap_median": cap_median,
        "cap_mean": cap_mean,
        "pe_median": pe_median,
        "roic_median_eligible": roic_median,
        "ey_median_eligible": ey_median,
        "pb_q20": pb_q20,
        "dividend_median_positive": div_median,
        "sector_de_median": sector_de_median,
    }


def _guru_piotroski_score(s: Dict[str, Any]) -> int:
    score = 0
    if (s.get("roa", 0.0) or 0.0) > 0:
        score += 1
    if (s.get("cfo_to_pat", 1.0) or 1.0) >= 0.6:
        score += 1
    if (s.get("pat_1y_growth", 0) or 0) > 0:
        score += 1
    if (s.get("cfo_to_pat", 1.0) or 1.0) >= 1.0:
        score += 1
    if (s.get("de_ratio", 99) or 99) < 1.0:
        score += 1
    if (s.get("current_ratio", 1.5) or 1.5) >= 1.5:
        score += 1
    if (s.get("share_dilution_3y", 2.0) or 2.0) <= 2.0:
        score += 1
    if (s.get("gross_margin", 20.0) or 20.0) >= 20.0:
        score += 1
    if (s.get("rev_1y_growth", 0) or 0) > 0:
        score += 1
    return score


def _guru_greenblatt_matches(s: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    if s.get("sector_code") in GURU_EXCLUDED_SECTORS_GREENBLATT:
        return False
    if not (_guru_num(s.get("market_cap")) and s.get("market_cap", 0) >= ctx["cap_median"]):
        return False
    if not (_guru_num(s.get("roic")) and s.get("roic", 0) > 0):
        return False
    if not (_guru_num(s.get("pe")) and s.get("pe", 0) > 0):
        return False
    return s.get("roic") >= ctx["roic_median_eligible"] and (100.0 / s.get("pe")) >= ctx["ey_median_eligible"]


def _guru_piotroski_matches(s: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    if not (_guru_num(s.get("pb")) and 0 < s.get("pb", 0) <= ctx["pb_q20"]):
        return False
    return _guru_piotroski_score(s) >= 7


def _guru_zweig_matches(s: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    pat1 = s.get("pat_1y_growth", 0) or 0
    eps3 = s.get("eps_3y_cagr", 0) or 0
    pe_v = s.get("pe")
    de_v = s.get("de_ratio")
    if pat1 <= 0 or pat1 <= eps3 or eps3 < 15.0:
        return False
    if (s.get("pat_5y_growth", 0) or 0) <= 0 or (s.get("rev_5y_growth", 0) or 0) <= 0:
        return False
    if (s.get("rev_1y_growth", 0) or 0) <= 0:
        return False
    if not (_guru_num(pe_v) and 5.0 < pe_v <= 40.0):
        return False
    if not (_guru_num(de_v) and de_v < ctx["sector_de_median"].get(s.get("sector_code", ""), 1.0)):
        return False
    return True


def _guru_osh_growth_matches(s: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    ps_v = s.get("ps")
    if not (_guru_num(s.get("market_cap")) and s.get("market_cap", 0) > ctx["cap_median"]):
        return False
    if not (_guru_num(ps_v) and 0 < ps_v < 1.5):
        return False
    if (s.get("pat_1y_growth", 0) or 0) <= 0 or (s.get("pat_3y_cagr", 0) or 0) <= 0 or (s.get("pat_5y_growth", 0) or 0) <= 0:
        return False
    return True


def _guru_osh_value_matches(s: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    div_v = s.get("dividend_yield")
    if not (_guru_num(s.get("market_cap")) and s.get("market_cap", 0) > ctx["cap_mean"]):
        return False
    if not (_guru_num(s.get("cfo_to_pat")) and s.get("cfo_to_pat", 0) > 1.0):
        return False
    return bool(_guru_num(div_v) and div_v >= ctx["dividend_median_positive"])


def _guru_neff_matches(s: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    eps3 = s.get("eps_3y_cagr", 0) or 0
    div_v = s.get("dividend_yield", 0) or 0
    pe_v = s.get("pe")
    if not (_guru_num(pe_v) and pe_v > 0):
        return False
    neff_ratio = (eps3 + div_v) / pe_v
    if neff_ratio < 1.0:
        return False
    if not (0.4 * ctx["pe_median"] <= pe_v <= 0.7 * ctx["pe_median"]):
        return False
    if not (7.0 <= eps3 <= 20.0):
        return False
    if (s.get("rev_3y_cagr", 0) or 0) < 7.0:
        return False
    if not (_guru_num(s.get("cfo_to_pat")) and s.get("cfo_to_pat", 0) > 1.0):
        return False
    return True


def _guru_novy_marx_matches(s: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    price = s.get("price", 0.0) or 0.0
    mcap = s.get("market_cap", 0.0) or 0.0
    if price < 4.0 or mcap < 200.0:
        return False
    gross_m = s.get("gross_margin", 0.0) or 0.0
    roe = s.get("roe", 0.0) or 0.0
    roic = s.get("roic", 0.0) or 0.0
    if not (gross_m >= 22.0 and (roic >= 13.0 or roe >= 15.0)):
        return False
    pe = s.get("pe")
    pb = s.get("pb")
    if not ((_guru_num(pe) and 0 < pe <= 13.5) or (_guru_num(pb) and 0 < pb <= 1.8)):
        return False
    cfo_pat = s.get("cfo_to_pat", 1.0) or 1.0
    if cfo_pat < 0.8:
        return False
    net_de = s.get("net_de_ratio", s.get("de_ratio", 0.5)) or 0.5
    if net_de > 0.60:
        return False
    return (s.get("fcf_ttm", 0.0) or 0.0) > 0


def _guru_qval_matches(s: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    if s.get("sector_code") == "VNFIN":
        return False
    price = s.get("price", 0.0) or 0.0
    mcap = s.get("market_cap", 0.0) or 0.0
    if price < 4.0 or mcap < 250.0:
        return False
    cfo_pat = s.get("cfo_to_pat", 1.0) or 1.0
    if cfo_pat < 0.90:
        return False
    dilution = s.get("share_dilution_3y", 2.0) or 2.0
    if dilution > 3.5:
        return False
    cur_r = s.get("current_ratio", 1.5) or 1.5
    if cur_r < 1.30:
        return False
    de = s.get("de_ratio", 99.0) or 99.0
    if de > 0.75:
        return False
    pe = s.get("pe")
    pb = s.get("pb")
    if not ((_guru_num(pe) and 0 < pe <= 13.0) or (_guru_num(pb) and 0 < pb <= 1.6)):
        return False
    roe = s.get("roe", 0.0) or 0.0
    roic = s.get("roic", 0.0) or 0.0
    if not (roe >= 15.0 or roic >= 12.0):
        return False
    if (s.get("fcf_ttm", 0.0) or 0.0) <= 0:
        return False
    div_y = s.get("dividend_yield", 0.0) or 0.0
    return div_y >= 1.5


def evaluate_guru_matches(s: Dict[str, Any], ctx: Dict[str, Any]) -> List[str]:
    matched: List[str] = []
    try:
        if _guru_greenblatt_matches(s, ctx):
            matched.append("guru_magic_formula_greenblatt")
        if _guru_piotroski_matches(s, ctx):
            matched.append("guru_piotroski_fscore")
        if _guru_zweig_matches(s, ctx):
            matched.append("guru_zweig_conservative_growth")
        if _guru_osh_growth_matches(s, ctx):
            matched.append("guru_cornerstone_growth_oshaughnessy")
        if _guru_osh_value_matches(s, ctx):
            matched.append("guru_cornerstone_value_oshaughnessy")
        if _guru_neff_matches(s, ctx):
            matched.append("guru_neff_total_return")
        if _guru_novy_marx_matches(s, ctx):
            matched.append("novy_marx_quality_value")
        if _guru_qval_matches(s, ctx):
            matched.append("gray_quantitative_value_qval")
        if len(matched) >= GURU_CONSENSUS_MIN_APPROVALS:
            matched.append("guru_consensus_multi_model")
    except Exception as exc:
        _logger.debug("guru matcher failed for %r: %s", s.get("symbol"), exc)
    return matched
