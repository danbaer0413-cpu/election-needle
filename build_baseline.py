"""
Turn ten years of county results (history_results.csv) into a race's counties.csv.

    python build_baseline.py history_results.csv --state GA --race "Governor" [options]

history_results.csv columns: state,county,year,race,dem_votes,rep_votes,other_votes,early_votes
Writes data/<ST>/<race>/counties.csv (county,region,base_margin,exp_votes,exp_early_share)
and prints sanity checks. Compare the printed statewide margins to the certified results.

Method
  base_margin     weighted mean of each county's two-party margin (D-R, pts) over past statewide
                  contests; recent years and the target office weigh more. The model's statewide
                  swing then moves every county to match the polls, so the baseline only needs the
                  right county-to-county pattern.
  exp_votes       weighted two-party votes in past midterm-type years (default 2022 and 2018),
                  times --growth.
  exp_early_share early + mail votes / total votes, weighted over years that report it
                  (--early-default if none do).
  region          from --regions regions.csv (county,region), otherwise auto-grouped by size and lean.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

from model import norm_name
from states import race_dir

REQUIRED = ["state", "county", "year", "race", "dem_votes", "rep_votes", "other_votes", "early_votes"]


def parse_weights(s: str) -> dict:
    return {int(k): float(v) for k, v in (kv.split(":") for kv in s.split(","))}


def build(hist: pd.DataFrame, state: str, race: str, margin_w: dict, turnout_w: dict,
          growth: float = 1.0, office_bonus: float = 1.5, early_default: float = 0.4,
          regions: pd.DataFrame | None = None,
          early_pattern: pd.DataFrame | None = None, midterm_scale: float = 0.80) -> tuple[pd.DataFrame, dict]:
    miss = [c for c in REQUIRED if c not in hist]
    if miss:
        raise ValueError(f"history is missing columns: {miss}")
    h = hist[hist["state"].astype(str).str.upper() == state.upper()].copy()
    if h.empty:
        raise ValueError(f"no rows for state {state}")
    for c in ("dem_votes", "rep_votes", "other_votes", "early_votes"):
        h[c] = pd.to_numeric(h[c], errors="coerce")
    # one spelling per county: different source files spell some names differently (St. Clair / St Clair)
    h["_k"] = h["county"].map(norm_name)
    h["county"] = h.groupby("_k")["county"].transform(lambda s: s.value_counts().index[0])
    h["two"] = h["dem_votes"] + h["rep_votes"]
    h = h[h["two"] > 0].copy()
    h["margin"] = (h["dem_votes"] - h["rep_votes"]) / h["two"] * 100
    h["total"] = h["two"] + h["other_votes"].fillna(0)
    target = race.replace(" (special)", "")
    h["is_target"] = h["race"].astype(str).str.replace(" (special)", "", regex=False) == target

    notes: dict = {"counties": int(h["county"].nunique()), "contests": []}
    # statewide margins per contest, for the sanity check
    g = h.groupby(["year", "race"]).agg(d=("dem_votes", "sum"), r=("rep_votes", "sum"), n=("county", "nunique"))
    for (y, rc), row in g.iterrows():
        notes["contests"].append((int(y), rc, int(row["n"]), round((row["d"] - row["r"]) / (row["d"] + row["r"]) * 100, 2)))

    # ---- base margin -------------------------------------------------------------
    m = h[h["year"].isin(margin_w)].copy()
    if m.empty:
        raise ValueError(f"none of the years {sorted(margin_w)} are in the history for {state}")
    m["w"] = m["year"].map(margin_w) * np.where(m["is_target"], office_bonus, 1.0)
    # weight by county size within contest too, so tiny counties don't swing the average of noise
    base = m.groupby("county").apply(lambda d: np.average(d["margin"], weights=d["w"]), include_groups=False)

    # ---- expected votes ------------------------------------------------------------
    t = h[h["year"].isin(turnout_w)].copy()
    notes["turnout_fallback"] = None
    if t.empty:
        # no midterm county results yet: use presidential-year turnout scaled down to a midterm level
        pres = {y: w for y, w in margin_w.items() if y in set(h["year"]) and y % 4 == 0}
        if not pres:
            raise ValueError(f"no turnout years found in the history for {state}")
        t = h[h["year"].isin(pres)].copy()
        turnout_w = pres
        notes["turnout_fallback"] = f"presidential years {sorted(pres)} x {midterm_scale}"
    else:
        midterm_scale = 1.0
    # per county-year: the target office if present, else the top of the ticket that year
    def pick(d):
        d = d[d["is_target"]] if d["is_target"].any() else d
        return d["two"].max()
    ty = t.groupby(["county", "year"]).apply(pick, include_groups=False).reset_index(name="two")
    ty["w"] = ty["year"].map(turnout_w)
    exp_votes = ty.groupby("county").apply(lambda d: np.average(d["two"], weights=d["w"]) * growth * midterm_scale,
                                           include_groups=False)

    # ---- early share ---------------------------------------------------------------
    e = h[h["early_votes"].notna() & (h["total"] > 0)].copy()
    e = e[e["year"].isin(list(turnout_w) + list(margin_w))]
    if len(e):
        e["share"] = (e["early_votes"] / e["total"]).clip(0, 1)
        e["w"] = e["year"].map({**margin_w, **turnout_w}).fillna(0.1) * e["total"]
        early = e.groupby("county").apply(lambda d: np.average(d["share"], weights=d["w"]), include_groups=False)
    else:
        early = pd.Series(dtype=float)

    out = pd.DataFrame({"county": base.index, "base_margin": base.values}).merge(
        exp_votes.rename("exp_votes").reset_index(), on="county", how="left")
    out["exp_early_share"] = out["county"].map(early)
    if early_pattern is not None and len(early_pattern):
        # county early shares are scaled from one past election's pattern (columns county,early,total)
        ep = early_pattern.groupby("county")[["early", "total"]].sum()
        rel = (ep["early"] / ep["total"]) / (ep["early"].sum() / ep["total"].sum())
        scaled = (early_default * out["county"].map(rel)).clip(0.05, 0.95)
        out["exp_early_share"] = out["exp_early_share"].fillna(scaled)
    out["exp_early_share"] = out["exp_early_share"].fillna(early_default)
    notes["early_share_from_data"] = int(out["county"].isin(early.index).sum())
    out["exp_votes"] = out["exp_votes"].fillna(out["exp_votes"].median())

    # ---- regions ------------------------------------------------------------------------
    if regions is not None:
        out["region"] = out["county"].map(regions.set_index("county")["region"])
    if "region" not in out or out["region"].isna().any():
        size = pd.qcut(out["exp_votes"].rank(method="first"), 3, labels=["small", "mid", "large"])
        lean = pd.cut(out["base_margin"], [-1e9, -10, 10, 1e9], labels=["R-lean", "swing", "D-lean"])
        auto = size.astype(str) + " " + lean.astype(str)
        out["region"] = out["region"].fillna(auto) if "region" in out else auto
    out["base_margin"] = out["base_margin"].round(2)
    out["exp_votes"] = out["exp_votes"].round(0)
    out["exp_early_share"] = out["exp_early_share"].round(3)
    M0 = float((out["exp_votes"] * out["base_margin"]).sum() / out["exp_votes"].sum())
    notes["baseline_statewide_margin"] = round(M0, 2)
    notes["expected_two_party_votes"] = int(out["exp_votes"].sum())
    return out[["county", "region", "base_margin", "exp_votes", "exp_early_share"]].sort_values("county"), notes


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("history")
    ap.add_argument("--state", required=True)
    ap.add_argument("--race", required=True, help='e.g. "Governor", "U.S. Senate", "U.S. Senate (special)"')
    ap.add_argument("--margin-weights", default="2024:0.2,2022:0.3,2020:0.1,2018:0.25,2016:0.05",
                    help='years:weights; midterm years (2022, 2018) lead on purpose. Add e.g. ",2006:0.1" for '
                         'the 2006 lame-duck-midterm analog (use it for lean only, not turnout)')
    ap.add_argument("--turnout-weights", default="2022:0.65,2018:0.35")
    ap.add_argument("--growth", type=float, default=1.0)
    ap.add_argument("--early-default", type=float, default=0.4)
    ap.add_argument("--early-pattern", default=None,
                    help="CSV county,early,total from one past election (convert_ga.py writes it); scales "
                         "each county's early share around --early-default")
    ap.add_argument("--regions", default=None, help="CSV with columns county,region")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    reg = pd.read_csv(a.regions) if a.regions else None
    table, notes = build(pd.read_csv(a.history), a.state, a.race, parse_weights(a.margin_weights),
                         parse_weights(a.turnout_weights), a.growth, early_default=a.early_default, regions=reg,
                         early_pattern=(pd.read_csv(a.early_pattern).query('race == "President"') if a.early_pattern else None))
    path = os.path.join(a.out or race_dir(a.state.upper(), a.race), "counties.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    table.to_csv(path, index=False)
    print(f"wrote {path}: {len(table)} units")
    print("Statewide margin (D-R, two-party) per contest found - compare with certified results:")
    for y, rc, n, mg in sorted(notes["contests"]):
        print(f"  {y} {rc:22s} {n:3d} units  {mg:+.2f}")
    if notes.get("turnout_fallback"):
        print(f"NOTE: no midterm county results, so expected votes use {notes['turnout_fallback']}. Add 2018/2022 results to improve.")
    print(f"Baseline statewide margin from weights: {notes['baseline_statewide_margin']:+.2f}; "
          f"expected two-party votes {notes['expected_two_party_votes']:,}; "
          f"early share from data for {notes['early_share_from_data']}/{len(table)} units "
          f"(rest use {a.early_default}).")
