"""Summarize the Ohio Statewide Voter File (SWVF) into small count tables. Counts only: no names, addresses, birth dates or voter IDs are written.

    python oh_summarize.py SWVF_1_22_txt.gz SWVF_23_44_txt.gz SWVF_45_66_txt.gz SWVF_67_88_txt.gz --out oh_summary

Accepts the four county-range files (.gz or plain .txt, comma separated). Needs pandas. Reads in chunks.
Ohio has no race or sex field. "Party" is the party of the last primary ballot a voter took (blank = never took one).
Age is as of Nov 3 2026, from date of birth.
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

CHUNK = 400_000
AS_OF = pd.Timestamp("2026-11-03")
GEN = {"g18": "GENERAL-11/06/2018", "g20": "GENERAL-11/03/2020", "g22": "GENERAL-11/08/2022", "g24": "GENERAL-11/05/2024", "g25": "GENERAL-11/04/2025"}
PRI26 = "PRIMARY-05/05/2026"
BANDS = [(0, 17, "under18"), (18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 54, "45-54"), (55, 64, "55-64"), (65, 200, "65+")]
COUNTIES = ("Adams Allen Ashland Ashtabula Athens Auglaize Belmont Brown Butler Carroll Champaign Clark Clermont Clinton Columbiana Coshocton "
            "Crawford Cuyahoga Darke Defiance Delaware Erie Fairfield Fayette Franklin Fulton Gallia Geauga Greene Guernsey Hamilton Hancock Hardin "
            "Harrison Henry Highland Hocking Holmes Huron Jackson Jefferson Knox Lake Lawrence Licking Logan Lorain Lucas Madison Mahoning Marion "
            "Medina Meigs Mercer Miami Monroe Montgomery Morgan Morrow Muskingum Noble Ottawa Paulding Perry Pickaway Pike Portage Preble Putnam "
            "Richland Ross Sandusky Scioto Seneca Shelby Stark Summit Trumbull Tuscarawas Union VanWert Vinton Warren Washington Wayne Williams Wood Wyandot").split()
USE = ["COUNTY_NUMBER", "DATE_OF_BIRTH", "REGISTRATION_DATE", "VOTER_STATUS", "PARTY_AFFILIATION", "PRECINCT_CODE", "CONGRESSIONAL_DISTRICT",
       "STATE_SENATE_DISTRICT", "STATE_REPRESENTATIVE_DISTRICT", *GEN.values(), PRI26]


def add(acc, key, g):
    acc[key] = g if acc.get(key) is None else acc[key].add(g, fill_value=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default="oh_summary")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    acc: dict = {}
    total = 0
    for path in a.files:
        for ch in pd.read_csv(path, dtype=str, usecols=USE, chunksize=CHUNK, encoding="latin-1", on_bad_lines="skip"):
            ch = ch.fillna("")
            age = (AS_OF - pd.to_datetime(ch["DATE_OF_BIRTH"], errors="coerce")).dt.days / 365.25
            ch["age_band"] = "unknown"
            for lo, hi, name in BANDS:
                ch.loc[(age >= lo) & (age < hi + 1), "age_band"] = name
            ch["county"] = pd.to_numeric(ch["COUNTY_NUMBER"], errors="coerce").fillna(0).astype(int)
            ch["party"] = ch["PARTY_AFFILIATION"].replace("", "none")
            ch["status"] = ch["VOTER_STATUS"]
            ch["reg_year"] = ch["REGISTRATION_DATE"].str[:4]
            for k, c in GEN.items():
                ch[k] = (ch[c] != "").astype(int)
            ch["pattern"] = ch["g18"].astype(str) + ch["g20"].astype(str) + ch["g22"].astype(str) + ch["g24"].astype(str)
            p = ch[PRI26]
            ch["p26_D"] = (p == "D").astype(int)
            ch["p26_R"] = (p == "R").astype(int)
            ch["p26_other"] = p.isin(["L", "G", "N", "X", "E"]).astype(int)   # third-party or issue-only ballot
            ch["n"] = 1
            ch["precinct"] = ch["PRECINCT_CODE"]
            ch["cd"] = ch["CONGRESSIONAL_DISTRICT"]
            ch["sd"] = ch["STATE_SENATE_DISTRICT"]
            ch["hd"] = ch["STATE_REPRESENTATIVE_DISTRICT"]
            add(acc, "registration_by_county_status_party_age", ch.groupby(["county", "status", "party", "age_band"]).size().rename("n"))
            add(acc, "registration_by_year_party", ch.groupby(["reg_year", "status", "party"]).size().rename("n"))
            add(acc, "turnout_pattern_by_county_party_age", ch.groupby(["county", "status", "party", "age_band", "pattern"]).size().rename("n"))
            vals = ["n", *GEN.keys(), "p26_D", "p26_R", "p26_other"]
            add(acc, "precinct_turnout", ch.groupby(["county", "precinct", "cd", "sd", "hd"])[vals].sum())
            add(acc, "district_party_age_turnout", ch.groupby(["cd", "party", "age_band"])[vals].sum())
            total += len(ch)
        print(f"{path}: running total {total:,} voters")
    names = {i + 1: c for i, c in enumerate(COUNTIES)}
    for k, g in acc.items():
        df = (g.to_frame() if isinstance(g, pd.Series) else g).reset_index()
        for c in df.columns:
            if c not in ("county", "precinct", "cd", "sd", "hd", "status", "party", "age_band", "pattern", "reg_year"):
                df[c] = df[c].round().astype(int)
        if "county" in df:
            df.insert(1, "county_name", df["county"].map(names))
        p = os.path.join(a.out, f"{k}.csv")
        df.to_csv(p, index=False)
        print(f"wrote {p} ({len(df):,} rows)")
    print(f"Done: {total:,} voters summarized. Counts only.")


if __name__ == "__main__":
    main()
