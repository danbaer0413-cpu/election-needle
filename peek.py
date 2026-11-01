"""Look inside a huge NC voter file without opening it in Notepad. Runs on YOUR computer.

    py peek.py FILE.txt                      show the column names and the first 10 rows
    py peek.py FILE.txt --rows 25            show more rows
    py peek.py FILE.txt --county WAKE        only voters in one county (first 10 matches)
    py peek.py FILE.txt --county WAKE --precinct 01-01
    py peek.py FILE.txt --all-columns        include names/addresses (hidden by default)

By default only non-identifying columns are shown (county, precinct, status, party, race, ethnicity, sex, age, voting method...).
It stops as soon as it has enough rows, so it is fast even on a multi-gigabyte file. Needs pandas.
"""
import argparse
import sys

import pandas as pd

SAFE = ["county_desc", "precinct_abbrv", "precinct_desc", "pct_label", "voter_status_desc", "party_cd", "race_code", "ethnic_code",
        "gender_code", "sex_code", "age_at_year_end", "registr_dt", "election_lbl", "election_desc", "voting_method", "voted_party_cd"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--rows", type=int, default=10)
    ap.add_argument("--county")
    ap.add_argument("--precinct")
    ap.add_argument("--all-columns", action="store_true")
    a = ap.parse_args()
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)
    head = pd.read_csv(a.path, sep="\t", encoding="latin-1", dtype=str, nrows=3, on_bad_lines="skip")
    cols = list(head.columns)
    print("COLUMNS IN THIS FILE:")
    print(", ".join(cols))
    show = cols if a.all_columns else [c for c in cols if c.lower() in SAFE]
    if not show:
        show = cols[:6]
    print("\nShowing:", ", ".join(show), "\n")
    found = []
    n = 0
    for chunk in pd.read_csv(a.path, sep="\t", encoding="latin-1", dtype=str, chunksize=200_000, on_bad_lines="skip"):
        low = {c.lower(): c for c in chunk.columns}
        if a.county:
            c = low.get("county_desc") or low.get("county")
            chunk = chunk[chunk[c].str.upper() == a.county.upper()] if c else chunk
        if a.precinct:
            c = low.get("precinct_abbrv") or low.get("pct_label") or low.get("precinct_desc")
            chunk = chunk[chunk[c].str.upper() == a.precinct.upper()] if c else chunk
        found.append(chunk[show])
        n += len(chunk)
        if n >= a.rows:
            break
    out = pd.concat(found).head(a.rows) if found else pd.DataFrame(columns=show)
    if out.empty:
        print("No matching rows found.")
    else:
        print(out.to_string(index=False))


if __name__ == "__main__":
    main()
