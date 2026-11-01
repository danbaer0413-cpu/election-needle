"""Load Redistricting Data Hub / L2 block-level files (any state, any of the layouts) into one long-format voter database. Counts only.

    python rdh_load.py MI_l2_2024_gen_stats_2020block.zip MI_l2_2022stats_2020block.zip ... --out voter_db

Layouts it understands (decided column by column, so new variants usually just work):
  * 2024 style   voted_<group> / reg_<group>                       (one election, named in the file name)
  * 2020/2022    <elec>_voted_<group> / <elec>_reg_<group>          (many elections)
  * plain        <elec>  (e.g. g20221108)                           (voters registered on the snapshot who voted; group "all", no reg)
  * profile      anything else numeric (total_reg, age_*, party_*, eth1_*, ...) = registration snapshot, stored separately
<elec> codes: g=general, p=primary, pp=presidential primary, r=runoff, s=special, cg/cp=consolidated general/primary + YYYYMMDD.

Output (per input file, in voter_db/parts/, then combined):
    NATIONAL_county_long.csv.gz   state, countyfp, source, election, grp, voted, reg
    NATIONAL_tract_long.csv.gz    state, countyfp, tract, source, election, grp, voted, reg   (core groups only)
    NATIONAL_profile_county.csv.gz state, countyfp, source, field, n
Voters L2 could not place on a map block are kept in their county when the label says which one, else under county "unassigned".
The same election can appear in several files (different snapshot dates); every row keeps its `source` so you can pick the snapshot closest to the election.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import zipfile

import pandas as pd

ELEC_NAMES = {"2024_gen": "g20241105"}
GROUP_FIX = {"gender_m": "gender_male", "gender_f": "gender_female", "gender_unk": "gender_unknown"}
TRACT_GROUPS = {"all", "eur", "aa", "hisp", "esa", "gender_male", "gender_female", "party_democratic", "party_republican", "party_ind_npp",
                "age_18_19", "age_20_24", "age_25_29", "age_30_34", "age_35_44", "age_45_54", "age_55_64", "age_65_74", "age_75_84", "age_85over"}
E = r"[a-z]{1,2}\d{8}"


def open_csv(path):
    if path.lower().endswith(".zip"):
        z = zipfile.ZipFile(path)
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        return z.open(name), os.path.basename(name)
    return open(path, "rb"), os.path.basename(path)


def classify(cols, default_elec):
    """return list of (column, election, group, kind) with kind in voted/reg/profile"""
    out = []
    for c in cols:
        if c in ("geoid20", "vtd_geoid20") or c.startswith("Unnamed"):
            continue
        if "pct_" in c:
            continue
        m = re.fullmatch(rf"({E})_(voted|reg)_(.+)", c)
        if m:
            out.append((c, m.group(1), GROUP_FIX.get(m.group(3), m.group(3)), m.group(2)))
            continue
        m = re.fullmatch(r"(voted|reg)_(.+)", c)
        if m:
            out.append((c, default_elec, GROUP_FIX.get(m.group(2), m.group(2)), m.group(1)))
            continue
        if re.fullmatch(E, c):
            out.append((c, c, "all", "voted"))
            continue
        out.append((c, "", c, "profile"))
    return out


def long_from_wide(df, keys, spec, groups=None):
    """df has been grouped to `keys` (index) and summed; spec = classified columns. Returns (votes_long, profile_long)."""
    vr = {}
    for c, el, g, k in spec:
        if k == "profile" or (groups is not None and g not in groups):
            continue
        vr.setdefault((el, g), {})[k] = c
    rows = []
    for (el, g), d in vr.items():
        part = df[keys].copy() if keys else pd.DataFrame(index=df.index)
        part["election"], part["grp"] = el, g
        part["voted"] = df[d["voted"]].values if "voted" in d else pd.NA
        part["reg"] = df[d["reg"]].values if "reg" in d else pd.NA
        rows.append(part)
    v = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default="voter_db")
    a = ap.parse_args()
    parts = os.path.join(a.out, "parts")
    os.makedirs(parts, exist_ok=True)
    for path in a.files:
        fh, name = open_csv(path)
        state = name[:2].upper()
        stem = os.path.splitext(name)[0]
        m = re.search(r"l2_(\d{4}_[a-z0-9]+)_stats", name.lower())
        default_elec = ELEC_NAMES.get(m.group(1), m.group(1)) if m else "unknown"
        head = list(pd.read_csv(fh, nrows=0).columns)
        fh.close()
        spec = classify(head, default_elec)
        use = ["geoid20"] + [c for c, *_ in spec]
        fh, _ = open_csv(path)
        cols = [c for c, *_ in spec]
        pieces, n_blocks = [], 0
        # read in chunks (big states have 500k+ blocks and 500+ columns) and add up to tract level as we go
        for d in pd.read_csv(fh, usecols=use, dtype={"geoid20": str}, chunksize=60_000):
            d[cols] = d[cols].apply(pd.to_numeric, errors="coerce").fillna(0)
            # some files lose the leading zero of states whose FIPS starts with 0 (AL, AK, AZ, AR, CA, CO, CT): 14 digits instead of 15
            short = d.geoid20.str.fullmatch(r"\d{14}")
            d.loc[short, "geoid20"] = "0" + d.loc[short, "geoid20"]
            std = d.geoid20.str.fullmatch(r"\d{15}")
            county = d.geoid20.str[2:5].copy()
            lead = d.geoid20.str.extract(r"(\d{3})", expand=False)
            county[~std] = lead[~std].fillna("unassigned")
            tract = d.geoid20.str[5:11].copy()
            tract[~std] = "no block"
            d["countyfp"], d["tract"] = county, tract
            pieces.append(d.groupby(["countyfp", "tract"])[cols].sum())
            n_blocks += len(d)
        fh.close()
        t_wide = pd.concat(pieces).groupby(level=["countyfp", "tract"]).sum().reset_index()
        del pieces
        c_wide = t_wide.groupby("countyfp")[cols].sum().reset_index()
        cl = long_from_wide(c_wide, ["countyfp"], spec)
        cl.insert(0, "state", state)
        cl.insert(2, "source", stem)
        prof = [(c, g) for c, el, g, k in spec if k == "profile"]
        pl = pd.DataFrame()
        if prof:
            pl = c_wide[["countyfp"] + [c for c, _ in prof]].melt(id_vars="countyfp", var_name="field", value_name="n")
            pl.insert(0, "state", state)
            pl.insert(2, "source", stem)
        tl = long_from_wide(t_wide, ["countyfp", "tract"], spec, groups=TRACT_GROUPS)
        if len(tl):
            tl.insert(0, "state", state)
            tl.insert(3, "source", stem)
        for df_, kind in ((cl, "county"), (tl, "tract"), (pl, "profile_county")):
            if len(df_):
                for col in ("voted", "reg", "n"):
                    if col in df_:
                        df_[col] = pd.to_numeric(df_[col], errors="coerce").round().astype("Int64")
                df_.to_csv(os.path.join(parts, f"{kind}__{state}__{stem}.csv.gz"), index=False)
        els = sorted({el for _, el, _, k in spec if k != "profile"})
        print(f"{state} {stem}: {n_blocks:,} blocks, {len(els)} elections, {c_wide.shape[0]} counties, {tl.countyfp.nunique() if len(tl) else 0} tract-counties, profile cols {len(prof)}")
    for kind, out in (("county", "NATIONAL_county_long"), ("tract", "NATIONAL_tract_long"), ("profile_county", "NATIONAL_profile_county")):
        fs = sorted(glob.glob(os.path.join(parts, f"{kind}__*.csv.gz")))
        if fs:
            df = pd.concat([pd.read_csv(f, dtype={"countyfp": str, "tract": str}) for f in fs], ignore_index=True)
            df.to_csv(os.path.join(a.out, out + ".csv.gz"), index=False)
            print(f"{out}.csv.gz: {df.state.nunique()} states, {len(df):,} rows")


if __name__ == "__main__":
    main()
