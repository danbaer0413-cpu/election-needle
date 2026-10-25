"""
Convert Georgia SoS results workbooks (the "Precinct Results"/"County Results" sheet, one row per
county x contest x choice) into history_results.csv rows.

    python convert_ga.py out.csv 2014=file.xlsx 2016=file.xlsx ...

Keeps statewide President / U.S. Senate / Governor general-election rows only. The county
column is the county name; early_votes stays blank (the files give early vote statewide only).
Also prints each year's statewide early/mail share from 'Total Votes by Group'.
"""
import json
import sys
import pandas as pd

RACES = {"president of the united states": "President", "president of the us": "President",
         "us senate": "U.S. Senate", "governor": "Governor"}


def convert(year, path):
    x = pd.ExcelFile(path)
    sh = [s for s in x.sheet_names if s in ("Precinct Results", "County Results")][0]
    d = x.parse(sh, usecols=range(7), dtype=str)
    d.columns = ["county", "office", "cid", "name", "choice", "party", "votes"]
    d["race"] = d["office"].str.strip().str.lower().map(RACES)
    d = d[d["race"].notna() & d["name"].notna()].copy()
    d["votes"] = pd.to_numeric(d["votes"], errors="coerce")
    d["county"] = d["county"].str.replace(r"\s+County$", "", regex=True).str.strip()
    d["p"] = d["party"].str.upper().fillna("")
    rows = []
    for (c, r), g in d.groupby(["county", "race"]):
        tot = g[g["name"] == "Total Votes"]["votes"].sum()
        cand = g[~g["name"].isin(["Total Votes", "Ballots Cast"])]
        dem, rep = cand[cand.p == "DEM"]["votes"].sum(), cand[cand.p == "REP"]["votes"].sum()
        rows.append(dict(state="GA", county=c, year=year, race=r, dem_votes=dem, rep_votes=rep,
                         other_votes=max(tot - dem - rep, 0), early_votes=None))
    g = x.parse("Total Votes by Group", usecols=range(7), dtype=str)
    g["Total"] = pd.to_numeric(g["Total"], errors="coerce")
    g = g[g["Ballot Name"] == "Total Votes"]
    top = g[g["Office Name"].str.strip().str.lower().isin(RACES)]
    share = None
    if len(top):
        o = top["Office Name"].iloc[0]
        t = top[top["Office Name"] == o].set_index("Group")["Total"]
        early = t[[i for i in t.index if i.lower().startswith(("absentee", "advance"))]].sum()
        share = early / t.sum()
    return pd.DataFrame(rows), share


# ---- Enhanced Voting JSON (the format results.sos.ga.gov serves; also what a live feed looks like) ----
JSON_RACES = {"president of the united states": "President", "president of the us": "President",
              "us senate (perdue)": "U.S. Senate", "us senate": "U.S. Senate",
              "us senate (loeffler) - special": "U.S. Senate (special)", "governor": "Governor"}


def convert_json(year, path):
    """County rows from the JSON: party sums per contest; early/mail votes per county from groupResults."""
    d = json.load(open(path))
    rows, early = [], []
    for c in d["localResults"]:
        county = c["name"].replace(" County", "").strip()
        for b in c["ballotItems"]:
            race = JSON_RACES.get(b["name"].strip().lower())
            if not race:
                continue
            dem = rep = oth = early_v = 0
            for o in b["ballotOptions"]:
                v, p = o["voteCount"] or 0, (o.get("politicalParty") or "").upper()
                if p == "DEM": dem += v
                elif p == "REP": rep += v
                else: oth += v
                for g in o.get("groupResults") or []:
                    if g["groupName"].lower().startswith(("absentee", "advance")):
                        early_v += g["voteCount"] or 0
            rows.append(dict(state="GA", county=county, year=year, race=race, dem_votes=dem, rep_votes=rep,
                             other_votes=oth, early_votes=None))
            early.append(dict(county=county, year=year, race=race, early=early_v, total=dem + rep + oth))
    return pd.DataFrame(rows), pd.DataFrame(early)


if __name__ == "__main__":
    out, args = sys.argv[1], sys.argv[2:]
    parts = []
    for a in args:
        y, p = a.split("=", 1)
        if p.endswith(".json"):
            df, early = convert_json(int(y), p)
            parts.append(df)
            early.to_csv(out.replace(".csv", f"_early_{y}.csv"), index=False)
            print(f"{y} (json): {df['race'].unique().tolist()} {df['county'].nunique()} counties")
            continue
        df, share = convert(int(y), p)
        parts.append(df)
        print(f"{y}: {df['race'].unique().tolist()} {df['county'].nunique()} counties; "
              f"statewide early+mail share {share:.1%}" if share else f"{y}: no group sheet")
    pd.concat(parts).to_csv(out, index=False)
    print("wrote", out)
