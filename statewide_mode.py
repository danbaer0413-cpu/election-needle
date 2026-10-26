"""
Statewide-totals mode: the needle can run from a state's TOTAL vote, and screenshots refine WHERE the vote is.

Two small files per race (in the race's data folder, e.g. data/MI/u-s-senate/):

  statewide.csv   one row, the latest statewide count (typed, pasted, or from a feed):
                    dem,rep[,pct_in][,as_of]
                  dem/rep = votes counted so far statewide. pct_in (optional) = the state's "% reporting";
                  only used as a check.
  reporting.csv   from screenshots, any counties you can read (the rest are filled in):
                    county,pct_in[,dem,rep]
                  pct_in = that county's % of expected vote counted (100 = final). If dem and rep are given
                  they are used as the county's real counts and removed from the allocation.

How the county table is built (so the model sees ordinary county results):
  1. Counties with real dem/rep (reporting.csv, or the race's results.csv from a feed/paste) are kept as is.
  2. What is left of the statewide totals is spread over the other counties in proportion to
     pct_in x expected votes (counties with no pct_in share the leftover evenly by expected votes).
  3. Each county's margin = its baseline margin + one common shift, chosen so the allocated Dem votes add up
     exactly to the statewide Dem total. Votes you have not located are therefore placed where the
     screenshots say they are, and the baseline map decides the rest.
If the county-level results already add up to at least the statewide total, they are used unchanged.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from model import norm_name

K_BASE = 1.0      # a statewide total with no county location is worth about ONE county's evidence in total
K_LOC = 3.0       # extra evidence when screenshots tell us where the counted vote is (scaled by the share of the state they cover)


def _read(path):
    try:
        return pd.read_csv(path) if os.path.exists(path) else None
    except Exception:
        return None


def _force_minutes(sw):
    try:
        return float(sw.get("force_minutes")) if sw is not None and pd.notna(sw.get("force_minutes")) else 60.0
    except Exception:
        return 30.0


def _forced(sw) -> bool:
    """statewide.csv row with force=yes and as_of_utc within force_minutes (default 60) of now: the typed/screenshot numbers beat scraped ones."""
    if sw is None or str(sw.get("force", "")).strip().lower() not in ("yes", "y", "true", "1"):
        return False
    try:
        t = pd.Timestamp(sw.get("as_of_utc"))
        t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
        return (pd.Timestamp.now(tz="UTC") - t) <= pd.Timedelta(minutes=_force_minutes(sw))
    except Exception:
        return False


def build(counties: pd.DataFrame, results: pd.DataFrame | None, folder: str, rid: str = "", log=print, statewide=None):
    sw = _read(os.path.join(folder, "statewide.csv"))
    sw = sw.iloc[-1] if sw is not None and len(sw) else None
    forced = _forced(sw)
    if statewide is not None and not forced and (sw is None or statewide["dem"] + statewide["rep"] > float(sw["dem"]) + float(sw["rep"])):
        sw = pd.Series(statewide)                          # a larger scraped total beats an older typed one (counts only go up)
    elif forced:
        log(f"  {rid}: screenshot numbers FORCED for {_force_minutes(sw):.0f} minutes from {sw.get('as_of_utc')}: they override scraped totals and counties until then")
    if sw is None:
        return results
    try:
        D, R = float(sw["dem"]), float(sw["rep"])
    except Exception:
        log(f"  {rid}: statewide.csv needs numeric dem and rep columns; ignored")
        return results
    c = counties.copy()
    c["_k"] = c["county"].astype(str).map(norm_name)
    c["exp"] = pd.to_numeric(c["exp_votes"], errors="coerce").fillna(0.0)
    base = pd.to_numeric(c["base_margin"], errors="coerce").fillna(0.0).to_numpy(float)

    known = {}          # key -> (dem, rep, final)
    pct = {}            # key -> pct_in for counties without counts
    for df in (results, _read(os.path.join(folder, "reporting.csv"))):
        if df is None or not len(df):
            continue
        for r in df.to_dict("records"):
            k = norm_name(str(r.get("county", "")))
            if not k or k not in set(c["_k"]):
                continue
            d, rp = r.get("dem"), r.get("rep")
            has = d is not None and rp is not None and not pd.isna(d) and not pd.isna(rp) and (float(d) + float(rp)) > 0
            p = r.get("pct_in", r.get("pct"))
            p = None if p is None or pd.isna(p) else float(p)
            if has:
                new_ = (float(d), float(rp), bool(r.get("final", False)) or (p is not None and p >= 100))
                old_ = known.get(k)
                from_report = df is not results
                if old_ is None or not from_report or forced or new_[0] + new_[1] >= old_[0] + old_[1]:
                    known[k] = new_
            elif p is not None:
                pct[k] = p

    kd = sum(v[0] for v in known.values()); kr = sum(v[1] for v in known.values())
    if kd + kr >= D + R - 1:
        return results                                   # county detail already covers the statewide count
    Drem, Rrem = max(D - kd, 0.0), max(R - kr, 0.0)
    Trem = Drem + Rrem

    un = c[~c["_k"].isin(known)].copy()
    ex = un["exp"].to_numpy(float)
    p = np.array([pct.get(k, np.nan) for k in un["_k"]], dtype=float)
    unknown_p = np.isnan(p)
    w = np.where(unknown_p, 0.0, np.clip(p, 0, 100) / 100.0 * ex)
    listed = float(w.sum())
    # counties without a screenshot share whatever the listed counties do not account for, by expected votes
    if listed > Trem and unknown_p.any():
        log(f"  {rid}: CHECK the % reporting you gave adds up to more votes than the statewide total; scaled down")
        w = w * Trem / listed
        w = np.where(unknown_p, 0.0, w)
    elif unknown_p.any():
        # target: listed counties hold their pct share of expected votes; the rest of Trem goes to the others
        leftover = max(Trem - listed, 0.0)
        w_un = ex * unknown_p
        w = np.where(unknown_p, leftover * w_un / max(w_un.sum(), 1.0), w)
    elif listed > 0:
        w = w * Trem / listed
    counted = w
    bm = np.array([base[c.index.get_loc(i)] for i in un.index])

    def dem_total(shift):
        m = np.clip(bm + shift, -100, 100)
        return float((counted * (1 + m / 100) / 2).sum())
    lo, hi = -100.0, 100.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if dem_total(mid) < Drem:
            lo = mid
        else:
            hi = mid
    shift = (lo + hi) / 2
    m = np.clip(bm + shift, -100, 100)
    dem = counted * (1 + m / 100) / 2
    rep = counted - dem

    cover = float(un.loc[[k in pct for k in un["_k"]], "exp"].sum() / max(un["exp"].sum(), 1.0))
    K = K_BASE + K_LOC * cover
    share = counted / max(counted.sum(), 1.0)
    rows = []
    for k, (d, rp, fin) in known.items():
        rows.append(dict(county=c.loc[c["_k"] == k, "county"].iloc[0], dem=d, rep=rp, final=fin, weight=1.0))
    for (i, row), d_, r_, sh_ in zip(un.iterrows(), dem, rep, share):
        if d_ + r_ <= 0:
            continue
        p_ = pct.get(row["_k"])
        rows.append(dict(county=row["county"], dem=round(float(d_)), rep=round(float(r_)),
                         final=bool(p_ is not None and p_ >= 100), weight=float(min(1.0, K * sh_))))
    out = pd.DataFrame(rows)
    exp_tot = float(c["exp"].sum())
    implied = (D + R) / exp_tot * 100 if exp_tot else float("nan")
    msg = (f"  {rid}: statewide mode, D {D:,.0f} R {R:,.0f} ({(D-R)/(D+R)*100:+.1f}); {len(known)} counties with counts, "
           f"{int(len(pct))} with % only, common shift vs baseline {shift:+.1f}; estimated rows carry about {K:.1f} counties' worth of evidence; implied {implied:.0f}% of expected vote")
    if "pct_in" in sw.index and not pd.isna(sw["pct_in"]) and abs(float(sw["pct_in"]) - implied) > 8:
        msg += f"  CHECK: state says {float(sw['pct_in']):.0f}% in but totals imply {implied:.0f}%"
    log(msg)
    return out
