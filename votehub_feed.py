"""Turn VoteHub's early-vote posts (data/votehub_latest.csv, read from Bluesky or typed from a screenshot) into model inputs.

Three things come from a post:
  1. total ballots cast so far            -> early.csv is scaled up to it when ours is older (county mix kept, or spread by expected early vote)
  2. share of projected final turnout     -> implied final turnout = total / share -> expected vote still to come
  3. modeled vote (range midpoints)       -> a bounded swing signal ("votehub_swing" in config/switches.json; house bias removed, capped, step-limited)
Their rating (Tilt D...) is shown, never used. Turn it all off with "votehub": false in config/switches.json.
config/votehub_map.csv lists which race the modeled vote belongs to (state_name, race, dem_name); turnout applies to every race in the state.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

LATEST = "data/votehub_latest.csv"
MAP = "config/votehub_map.csv"
SWITCHES = "config/switches.json"
STEP = 1.0   # most a race's VoteHub effect may change between updates (points of median)


def enabled() -> bool:
    try:
        return bool(json.load(open(SWITCHES)).get("votehub", True))
    except Exception:
        return True


def swing_on() -> bool:
    """Their modeled early margin as swing evidence. On by default, bounded: it is the margin of the EARLY electorate, which runs 17-38 points more
    Democratic than the final result, so run_update removes the across-state median gap (their house bias), caps the effect at vh_max_effect
    points per race and lets it change by at most STEP points per update."""
    try:
        return bool(json.load(open(SWITCHES)).get("votehub_swing", True))
    except Exception:
        return False


def load(path: str = LATEST) -> dict:
    """newest row per state name (any vote kind)."""
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return {}
    df = pd.read_csv(path)
    if not len(df):
        return {}
    df = df.sort_values("as_of")
    return {r["state"]: r for r in df.to_dict("records")}


def load_map(path: str = MAP) -> dict:
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return {}
    return {str(r["race"]): r for r in pd.read_csv(path).to_dict("records")}


def _f(x):
    try:
        v = float(x)
        return None if np.isnan(v) else v
    except Exception:
        return None


def adjust_early(early, counties, row, log=print):
    """Scale (or build) the county early table so its total matches VoteHub's statewide count when VoteHub is fresher."""
    total = _f(row.get("total"))
    if not total:
        return early
    if early is not None and len(early) and pd.to_numeric(early["early_returned"], errors="coerce").sum() > 0:
        have = float(pd.to_numeric(early["early_returned"], errors="coerce").sum())
        if total > have * 1.03:
            k = total / have
            e = early.copy()
            for c in ("early_returned", "d_reg", "r_reg", "o_reg"):
                if c in e:
                    e[c] = pd.to_numeric(e[c], errors="coerce") * k
            log(f"  VoteHub: early vote {have:,.0f} -> {total:,.0f} (x{k:.2f}, as of {row.get('as_of')})")
            return e
        return early
    wt = (pd.to_numeric(counties["exp_votes"], errors="coerce").fillna(0)
          * pd.to_numeric(counties.get("exp_early_share", 0.5), errors="coerce").fillna(0.5)).to_numpy(float)
    if wt.sum() <= 0:
        return early
    log(f"  VoteHub: statewide early vote {total:,.0f} spread over {len(counties)} counties (no county table)")
    out = pd.DataFrame({"county": counties["county"].to_numpy(), "early_returned": total * wt / wt.sum()})
    out.attrs["spread"] = True
    return out


def params_for(rid: str, state_name: str, vh: dict, vmap: dict, early=None, log=print) -> tuple[dict, dict]:
    """(Params overrides, display info) for one race. {} when VoteHub has nothing usable."""
    row = vh.get(state_name)
    if row is None:
        return {}, {}
    kw, info = {}, {"as_of": row.get("as_of"), "total": _f(row.get("total")), "pct_of_final": _f(row.get("pct_of_final")),
                    "implied_final": _f(row.get("implied_final")), "rating": row.get("rating")}
    if info["implied_final"]:
        kw["vh_final_turnout"] = info["implied_final"]
    if early is not None and getattr(early, "attrs", {}).get("spread"):
        kw["early_geo_signal"] = False
    m = vmap.get(rid)
    em = _f(row.get("early_margin"))
    if m is not None and em is not None:
        want = str(m.get("dem_name", "")).strip().lower()
        if want and want not in str(row.get("dem_name", "")).lower():
            log(f"  VoteHub: {rid} modeled vote skipped (post is about {row.get('dem_name')}, not {m.get('dem_name')})")
        else:
            info.update(modeled=True, swing_used=swing_on(), early_margin=em, dem=f"{row.get('dem_name')} {row.get('dem_lo')}-{row.get('dem_hi')}",
                        rep=f"{row.get('rep_name')} {row.get('rep_lo')}-{row.get('rep_hi')}")
    return kw, info
