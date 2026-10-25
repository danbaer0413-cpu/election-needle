"""
Check every configured race's files before you trust them.

    python validate.py [--config config/races.json]

Flags: missing/misnamed columns, bad numbers, units in early/results that don't match
counties.csv (the usual way this breaks), duplicate units, and odd baselines.
"""
from __future__ import annotations

import argparse
import json
import os

import pandas as pd

from model import norm_name

NEED = {
    "counties.csv": ["county", "region", "base_margin", "exp_votes", "exp_early_share"],
    "early.csv": ["county", "early_returned"],
    "results.csv": ["county", "dem", "rep"],
}


def check_race(folder: str) -> list[str]:
    issues: list[str] = []
    cpath = os.path.join(folder, "counties.csv")
    if not os.path.exists(cpath):
        return ["counties.csv missing"]
    c = pd.read_csv(cpath)
    if c.empty:
        return ["counties.csv has no rows yet"]
    miss = [x for x in NEED["counties.csv"] if x not in c]
    if miss:
        return [f"counties.csv missing columns {miss}"]
    for col in ("base_margin", "exp_votes", "exp_early_share"):
        if pd.to_numeric(c[col], errors="coerce").isna().any():
            issues.append(f"counties.csv: non-numeric or blank values in {col}")
    if c["county"].map(norm_name).duplicated().any():
        issues.append("counties.csv: duplicate unit names: " +
                      ", ".join(sorted(c.loc[c["county"].map(norm_name).duplicated(keep=False), "county"].unique())[:5]))
    if (c["exp_early_share"] > 1).any() or (c["exp_early_share"] < 0).any():
        issues.append("counties.csv: exp_early_share should be between 0 and 1")
    if (c["base_margin"].abs() > 100).any():
        issues.append("counties.csv: base_margin outside +/-100 (should be points, e.g. 12.5)")
    keys = set(c["county"].map(norm_name))
    for name in ("early.csv", "results.csv"):
        p = os.path.join(folder, name)
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p)
        if d.empty:
            continue
        miss = [x for x in NEED[name] if x not in d]
        if miss:
            issues.append(f"{name} missing columns {miss}")
            continue
        dk = d["county"].map(norm_name)
        unknown = sorted(set(d.loc[~dk.isin(keys), "county"].astype(str)))
        if unknown:
            issues.append(f"{name}: {len(unknown)} units not in counties.csv, e.g. {unknown[:5]}")
        absent = len(keys - set(dk))
        if absent:
            issues.append(f"{name}: {absent} of {len(keys)} counties.csv units have no row (treated as zero)")
    return issues


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/races.json")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    ok = 0
    for r in cfg["races"]:
        problems = check_race(r.get("dir", f"data/{r['id']}"))
        if problems:
            print(f"{r['id']}: " + "; ".join(problems))
        else:
            ok += 1
            print(f"{r['id']}: ok")
    print(f"\n{ok}/{len(cfg['races'])} races ready")
