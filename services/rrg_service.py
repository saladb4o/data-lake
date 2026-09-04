"""
Relative Rotation Graph (RRG) pure-math service for the "Chi so nganh" tab.

Reference formulas: RRG methodology (Julius de Kempenaer); enhanced variant
adapted from github.com/AdroitAnandAI/RRG-Sector-Rotation-India.

No I/O, no network: callers pass in candle dicts.
"""

import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def _ema_alpha(m: int) -> float:
    return 2.0 / (m + 1)


def _zscore_spread(series: pd.Series, window: int) -> pd.Series:
    """Spread a series around 100 using a rolling-window z-score (x10 scale)."""
    roll_mean = series.rolling(window).mean()
    roll_std = series.rolling(window).std(ddof=0)
    z = pd.Series(0.0, index=series.index)
    valid = roll_std > 0
    z[valid] = (series - roll_mean)[valid] / roll_std[valid]
    # Flat window (std == 0): value equals its mean -> z = 0 -> exactly 100.
    return 100.0 + 10.0 * z


def compute_rs_series(sec_closes: List[float], bm_closes: List[float], m: int = 14) -> np.ndarray:
    """Elementwise RS = sec/bm smoothed with JdK EMA (alpha = 2/(m+1)).

    First values use an expanding mean until enough data exists, then a
    standard recursive EMA seeded from that expanding value. Output length
    always equals input length.
    """
    sec = np.asarray(sec_closes, dtype=float)
    bm = np.asarray(bm_closes, dtype=float)
    if sec.shape != bm.shape:
        raise ValueError("sec_closes and bm_closes must have equal length")
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = sec / bm

    n = len(rs)
    alpha = _ema_alpha(m)
    out = np.full(n, np.nan)
    warmup = max(1, min(m, n))
    head = rs[:warmup]
    seed = np.nanmean(head) if np.isfinite(head).any() else np.nan
    prev = seed
    for i in range(n):
        v = rs[i]
        if i < warmup:
            prev = np.nanmean(rs[: i + 1])
        elif np.isfinite(v) and np.isfinite(prev):
            prev = alpha * v + (1.0 - alpha) * prev
        out[i] = prev
    return out


def compute_rrg_series(rs_series, k: int = 10, method: str = "jdk", m: int = 14) -> Dict[str, list]:
    """Compute RS-Ratio / RS-Momentum series from an RS series.

    Leading NaNs are dropped; the caller keeps time alignment via index
    offsets (values are in chronological order, oldest first).
    """
    s = pd.Series(np.asarray(rs_series, dtype=float), dtype=float)
    s = s[s.notna()]
    alpha_m = _ema_alpha(m)
    ema_rs = s.ewm(alpha=alpha_m, adjust=False)

    ema_mean = ema_rs.mean()
    if method == "enhanced":
        ratio = 100.0 * ema_mean / ema_mean.rolling(m).mean()
        roc = ratio.pct_change(k)
        momentum = 100.0 + 100.0 * roc.ewm(alpha=_ema_alpha(k), adjust=False).mean()
    else:  # jdk
        ratio = _zscore_spread(ema_mean, m)
        roc = (ema_mean - ema_mean.shift(k)) / ema_mean.shift(k)
        momentum = _zscore_spread(roc.ewm(alpha=alpha_m, adjust=False).mean(), m)

    total = int(np.asarray(rs_series, dtype=float).size)
    # Join on shared valid positions so x/y stay time-aligned.
    combined = pd.concat(
        [
            ratio.replace([np.inf, -np.inf], np.nan).rename("x"),
            momentum.replace([np.inf, -np.inf], np.nan).rename("y"),
        ],
        axis=1,
    ).dropna()
    return {
        "rs_ratio": [float(v) for v in combined["x"]],
        "rs_momentum": [float(v) for v in combined["y"]],
        "offset": int(total - len(combined)),
    }


def classify_quadrant(rs_ratio: float, rs_momentum: float) -> str:
    if rs_ratio > 100.0 and rs_momentum > 100.0:
        return "Leading"
    if rs_ratio > 100.0:
        return "Weakening"
    if rs_momentum > 100.0:
        return "Improving"
    return "Lagging"


def _candles_to_frame(candles: List[dict]) -> Optional[pd.DataFrame]:
    if not candles:
        return None
    rows = []
    for c in candles:
        try:
            t = str(c.get("time", ""))[:10]
            v = float(c.get("close"))
        except (TypeError, ValueError):
            continue
        if not t or not math.isfinite(v) or v <= 0:
            continue
        rows.append((t, v))
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["time", "close"]).drop_duplicates("time", keep="last")
    df = df.sort_values("time").set_index("time")
    return df


def build_rrg_matrix(
    sectors_hist: Dict[str, List[dict]],
    bench_candles: List[dict],
    tail: int = 8,
    method: str = "jdk",
    m: int = 14,
    k: int = 10,
    sector_names: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build RRG points for all sectors vs a benchmark.

    Each sector's closes are aligned to benchmark closes by date
    intersection. Sectors with too few aligned points get an "error" entry.
    """
    names = sector_names or {}
    bench = _candles_to_frame(bench_candles)
    result: Dict[str, Any] = {"method": method, "points": []}
    if bench is None:
        for code in sectors_hist:
            result["points"].append({
                "sector_code": code,
                "sector_name": names.get(code, code),
                "error": "no benchmark data",
            })
        return result

    min_points = max(m + k + 5, 60)

    for code, candles in sectors_hist.items():
        name = names.get(code, code)
        try:
            sec = _candles_to_frame(candles)
            joined = bench.join(sec, how="inner", lsuffix="_bm", rsuffix="_sec").dropna()
            n = len(joined)
            if n < min_points:
                result["points"].append({
                    "sector_code": code,
                    "sector_name": name,
                    "error": f"insufficient aligned data ({n} < {min_points})",
                })
                continue

            rs = compute_rs_series(joined["close_sec"].tolist(), joined["close_bm"].tolist(), m=m)
            series = compute_rrg_series(rs, k=k, method=method, m=m)
            off = series["offset"]
            ratios = series["rs_ratio"]
            moms = series["rs_momentum"]
            if not ratios or not moms or not math.isfinite(ratios[-1]) or not math.isfinite(moms[-1]):
                result["points"].append({
                    "sector_code": code,
                    "sector_name": name,
                    "error": "not enough valid RS points",
                })
                continue

            x, y = ratios[-1], moms[-1]
            tcount = max(0, int(tail))
            times = joined.index.to_list()[off:]
            start = max(0, len(times) - tcount)
            tail_pts = [
                {"time": str(times[i]), "x": float(ratios[i - off]), "y": float(moms[i - off])}
                for i in range(start, len(times))
            ]
            result["points"].append({
                "sector_code": code,
                "sector_name": name,
                "rs_ratio": float(x),
                "rs_momentum": float(y),
                "quadrant": classify_quadrant(float(x), float(y)),
                "tail": tail_pts,
            })
        except Exception as e:  # never let one bad sector break the matrix
            result["points"].append({
                "sector_code": code,
                "sector_name": name,
                "error": f"{type(e).__name__}: {e}",
            })
    return result
