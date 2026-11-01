"""Summarize a big North Carolina voter file into small count tables you can share. Runs on YOUR computer.

    python nc_summarize.py PATH_TO_FILE.txt [--out summary_out]

Works on either NCSBE file type (it checks the column names):
  * registration file / snapshot (ncvoter*.txt, or a Snapshots file)  -> counts by county, precinct, status, party, race, ethnicity, sex, age band
  * voter history file (ncvhis*.txt)                                  -> counts by election, voting method, county, precinct, party voted

It keeps ONLY counts. Names, addresses, voter numbers and birth data are never read into the output.
Needs: python 3 and pandas (pip install pandas). Reads the file in chunks, so a large file is fine.
Tab-separated, latin-1 text, as NCSBE publishes. If your file is a .zip, unzip it first.
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

CHUNK = 500_000

# column-name candidates (lower case). First one found is used.
PICK = {
    "county": ["county_desc", "county"],
    "precinct": ["precinct_abbrv", "precinct_desc", "pct_label", "precinct", "pct_description"],
    "status": ["voter_status_desc", "voter_status_reason_desc", "status_cd"],
    "party": ["party_cd", "party_desc", "party"],
    "race": ["race_code", "race_desc", "race"],
    "ethnic": ["ethnic_code", "ethnic_desc", "ethnicity"],
    "sex": ["sex_code", "gender_code", "sex", "gender"],
    "age": ["age_at_year_end", "age"],
    "election": ["election_lbl", "election_date", "election_desc"],
    "method": ["voting_method", "vote_method"],
    "voted_party": ["voted_party_cd", "voted_party_desc"],
}
BANDS = [(0, 17, "under18"), (18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 54, "45-54"), (55, 64, "55-64"), (65, 200, "65+")]


def band(age):
    a = pd.to_numeric(age, errors="coerce")
    out = pd.Series("unknown", index=a.index)
    for lo, hi, name in BANDS:
        out[(a >= lo) & (a <= hi)] = name
    return out


def find_cols(cols):
    low = {c.lower().strip(): c for c in cols}
    found = {}
    for k, cands in PICK.items():
        for c in cands:
            if c in low:
                found[k] = low[c]
                break
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--out", default="summary_out")
    a = ap.parse_args()
    if not os.path.exists(a.path):
        sys.exit(f"File not found: {a.path}")
    os.makedirs(a.out, exist_ok=True)
    head = pd.read_csv(a.path, sep="\t", encoding="latin-1", dtype=str, nrows=5, on_bad_lines="skip")
    cols = find_cols(head.columns)
    is_hist = "method" in cols or ("election" in cols and "party" not in cols)
    kind = "history" if is_hist else "registration"
    print(f"Detected a {kind} file. Columns used: {cols}")
    if not is_hist and "county" not in cols:
        sys.exit("Could not find a county column. Send me the header row (first line only) and I will adjust.")

    dims_by_table = {}
    if is_hist:
        dims_by_table["by_election_method_county"] = ["election", "method", "county"]
        dims_by_table["by_election_method_party"] = ["election", "method", "voted_party"]
        dims_by_table["by_election_precinct"] = ["election", "county", "precinct"]
    else:
        dims_by_table["by_county_party_race_sex_age"] = ["county", "status", "party", "race", "ethnic", "sex", "age_band"]
        dims_by_table["by_precinct_party_race"] = ["county", "precinct", "status", "party", "race"]
        dims_by_table["by_precinct_sex_age"] = ["county", "precinct", "status", "sex", "age_band"]

    use = sorted({cols[k] for k in cols})
    acc = {name: None for name in dims_by_table}
    total = 0
    for chunk in pd.read_csv(a.path, sep="\t", encoding="latin-1", dtype=str, usecols=use, chunksize=CHUNK, on_bad_lines="skip"):
        ren = {v: k for k, v in cols.items()}
        chunk = chunk.rename(columns=ren)
        if "age" in chunk:
            chunk["age_band"] = band(chunk["age"])
        total += len(chunk)
        for name, dims in dims_by_table.items():
            d = [x for x in dims if x in chunk.columns]
            if not d:
                continue
            g = chunk.fillna("").groupby(d).size().rename("n")
            acc[name] = g if acc[name] is None else acc[name].add(g, fill_value=0)
        print(f"  ...{total:,} rows", end="\r")
    print(f"\nRead {total:,} rows.")
    for name, g in acc.items():
        if g is None:
            continue
        df = g.reset_index()
        df["n"] = df["n"].astype(int)
        p = os.path.join(a.out, f"{kind}_{name}.csv")
        df.to_csv(p, index=False)
        print(f"Wrote {p}  ({len(df):,} rows)")
    print(f"\nDone. Send me the CSV files in '{a.out}' (they contain counts only).")


if __name__ == "__main__":
    main()
