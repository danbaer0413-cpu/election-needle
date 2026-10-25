"""
Convert MIT Election Lab precinct-level files (the MEDSL "*-elections-official" format) to
history_results.csv rows: statewide President / U.S. Senate / Governor, general election, by county.

    python convert_medsl.py out.csv file1.csv [file2.csv ...]      (append mode: pass history to extend)

Vote modes: a precinct may appear as TOTAL or split into ELECTION DAY / ABSENTEE / etc. For each precinct
and candidate we use TOTAL when present, otherwise the sum of the modes (never both). ABSENTEE votes
become early_votes (mail only; in-person early voting is not separated in these files).
Prints statewide Dem/Rep totals per contest: compare them with certified results before use.
"""
import os
import sys

import pandas as pd

OFFICES = {"US PRESIDENT": "President", "PRESIDENT": "President", "US SENATE": "U.S. Senate",
           "U.S. SENATE": "U.S. Senate", "GOVERNOR": "Governor"}
COLS = ["precinct", "office", "party_simplified", "mode", "votes", "county_name", "candidate", "stage", "special",
        "year", "state_po", "district"]


def read_filtered(path, states=None, chunksize=500_000):
    """Read a big nationwide file in chunks, keeping only general-election rows for the offices and states we use."""
    keep = []
    for ch in pd.read_csv(path, usecols=lambda c: c in COLS, dtype={"district": str, "precinct": str},
                          chunksize=chunksize, low_memory=False):
        m = ch["stage"].astype(str).str.upper().eq("GEN") & ch["office"].astype(str).str.upper().str.strip().isin(OFFICES)
        if states:
            m &= ch["state_po"].isin(states)
        keep.append(ch[m])
    return pd.concat(keep, ignore_index=True)


def convert(path, states=None):
    d = read_filtered(path, states)
    if "precinct" not in d:          # county-level files have no precinct column
        d["precinct"] = ""
    d = d[d["stage"].astype(str).str.upper() == "GEN"].copy()
    d["office_n"] = d["office"].astype(str).str.upper().str.strip()
    d = d[d["office_n"].isin(OFFICES)].copy()
    d["race"] = d["office_n"].map(OFFICES)
    sp = d["special"].astype(str).str.upper().eq("TRUE")
    d.loc[sp & d["race"].eq("U.S. Senate"), "race"] = "U.S. Senate (special)"
    d = d[d["candidate"].notna() & d["candidate"].astype(str).str.strip().ne("")].copy()
    d = d[~d["candidate"].astype(str).str.upper().str.contains(
        r"BALLOTS|CAST VOTES|VOTES CAST|REGISTERED|OVER ?VOTE|UNDER ?VOTE|BLANK|^TOTAL|SCATTER", regex=True)].copy()
    d["votes"] = pd.to_numeric(d["votes"], errors="coerce").fillna(0)
    d["is_total"] = d["mode"].astype(str).str.upper().eq("TOTAL")
    key = ["state_po", "year", "county_name", "precinct", "race", "candidate", "party_simplified"]
    d[key] = d[key].astype(object).where(d[key].notna(), "")
    has_total = d.groupby(key)["is_total"].transform("any").astype(bool)
    d = d[(has_total & d["is_total"]) | (~has_total & ~d["is_total"])].copy()
    d["absentee"] = d["votes"].where(d["mode"].astype(str).str.upper().eq("ABSENTEE"), 0)
    g = d.groupby(["state_po", "year", "county_name", "race", "party_simplified"])[["votes", "absentee"]].sum()
    g = g.reset_index()
    rows = []
    for (st, yr, cty, race), s in g.groupby(["state_po", "year", "county_name", "race"]):
        v = s.set_index("party_simplified")["votes"]
        dem, rep = v.get("DEMOCRAT", 0), v.get("REPUBLICAN", 0)
        rows.append(dict(state=st, county=cty.title(), year=int(yr), race=race, dem_votes=int(dem), rep_votes=int(rep),
                         other_votes=int(v.sum() - dem - rep),
                         early_votes=int(s["absentee"].sum()) if s["absentee"].sum() > 0 else None))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out, files = sys.argv[1], sys.argv[2:]
    states = os.environ.get("STATES", "").split(",") if os.environ.get("STATES") else None
    parts = [convert(f, states) for f in files]
    new = pd.concat(parts, ignore_index=True)
    if os.path.exists(out):
        old = pd.read_csv(out)
        new = pd.concat([old[~old.set_index(["state", "year", "race"]).index.isin(
            new.set_index(["state", "year", "race"]).index)], new], ignore_index=True)
    new.to_csv(out, index=False)
    t = new.groupby(["state", "year", "race"])[["dem_votes", "rep_votes", "other_votes"]].sum()
    t["margin"] = ((t.dem_votes - t.rep_votes) / (t.dem_votes + t.rep_votes) * 100).round(2)
    t["counties"] = new.groupby(["state", "year", "race"])["county"].nunique()
    print(t.to_string())
    print("wrote", out)
