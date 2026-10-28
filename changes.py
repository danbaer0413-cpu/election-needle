"""What moved since an earlier update, from data/needle_log.csv and the latest projections. No Streamlit here, so it can be tested alone."""
from __future__ import annotations

import os

import pandas as pd

WINDOWS = {"Last update": None, "24 hours": 24, "7 days": 24 * 7}


def read(path: str = "data/needle_log.csv") -> pd.DataFrame:
    if not path.startswith("http") and not os.path.exists(path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        df["ts"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        return df.dropna(subset=["ts", "median"])
    except Exception:
        return pd.DataFrame()


def reference_time(log: pd.DataFrame, now_ts, hours):
    """The earlier update to compare against: the previous run, or the last one at least `hours` before the newest."""
    times = sorted(log["ts"].unique())
    times = [pd.Timestamp(t) for t in times if pd.Timestamp(t) < now_ts]
    if not times:
        return None
    if hours is None:
        return times[-1]
    target = now_ts - pd.Timedelta(hours=hours)
    older = [t for t in times if t <= target]
    return older[-1] if older else times[0]          # not that much history yet: use the oldest we have


def compute(log: pd.DataFrame, races: dict, hours=None):
    """(DataFrame of changes, reference timestamp). races = latest.json['races'] (only those with a summary).
    Columns: id, prev_median, median, d_median, prev_win, win, d_win. Sorted by size of the median move."""
    if log is None or not len(log):
        return pd.DataFrame(), None
    now_ts = log["ts"].max()
    ref = reference_time(log, now_ts, hours)
    if ref is None:
        return pd.DataFrame(), None
    prev = log[log["ts"] == ref].drop_duplicates("id", keep="last").set_index("id")
    rows = []
    for rid, r in races.items():
        s = r.get("summary")
        if not s or rid not in prev.index:
            continue
        p = prev.loc[rid]
        rows.append(dict(id=rid, prev_median=float(p["median"]), median=float(s["median"]),
                         d_median=float(s["median"]) - float(p["median"]),
                         prev_win=float(p["win_prob"]) * 100, win=float(s["win_prob"]) * 100,
                         d_win=float(s["win_prob"]) * 100 - float(p["win_prob"]) * 100))
    df = pd.DataFrame(rows)
    if len(df):
        df = df.reindex(df["d_median"].abs().sort_values(ascending=False).index).reset_index(drop=True)
    return df, ref


def arrow(d: float, tol: float = 0.05) -> str:
    return "▲ toward Dem" if d > tol else "▼ toward GOP" if d < -tol else "– no change"


def margin_text(m: float) -> str:
    return f"{'D' if m > 0 else 'R'}+{abs(m):.1f}"


def sweep(start: float, end: float, steps: int = 14) -> list[float]:
    """Eased path from start to end (fast, then settling), ending exactly on end."""
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        e = 1 - (1 - t) ** 3
        out.append(start + (end - start) * e)
    out[-1] = end
    return out


def pct_text(p: float) -> str:
    """Win chance for display: never a flat 100% or 0% (the model is never that sure)."""
    return ">99%" if p > 99.0 else "<1%" if p < 1.0 else f"{p:.0f}%"


def rating_text(dem_pct: float) -> str:
    """Words instead of a win percentage: Toss-up / Tilt / Lean / Likely / Solid (by Dem win chance)."""
    side = "Dem" if dem_pct >= 50 else "GOP"
    p = max(dem_pct, 100 - dem_pct)
    if p < 55:
        return "Toss-up"
    return f"{'Tilt' if p < 65 else 'Lean' if p < 80 else 'Likely' if p < 95 else 'Solid'} {side}"
