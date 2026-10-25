"""
MIT county presidential returns (countypres_2000-2024.csv) -> history_results.csv rows for chosen states/years.

    python convert_countypres.py countypres_2000-2024.csv 2016,2020,2024 AK,FL,GA,...

Uses mode TOTAL when a county has it, else sums the modes. early_votes = early + absentee + mail modes when the
file splits them (blank otherwise). Merges into data/<ST>/history_results.csv without replacing any
(year, race) that is already there (so Georgia's official-file rows stay).
"""
import os
import sys

import pandas as pd

src, years, states = sys.argv[1], [int(y) for y in sys.argv[2].split(",")], sys.argv[3].split(",")
d = pd.read_csv(src, dtype={"county_fips": str})
d = d[d.state_po.isin(states) & d.year.isin(years) & d.office.eq("US PRESIDENT")].copy()
d["mode"] = d["mode"].astype(str).str.upper()
d["candidatevotes"] = pd.to_numeric(d["candidatevotes"], errors="coerce").fillna(0)
rows = []
for (st, yr, cty), g in d.groupby(["state_po", "year", "county_name"]):
    use = g[g["mode"].eq("TOTAL")] if g["mode"].eq("TOTAL").any() else g
    v = use.groupby("party")["candidatevotes"].sum()
    dem, rep = int(v.get("DEMOCRAT", 0)), int(v.get("REPUBLICAN", 0))
    early = g[g["mode"].str.contains("EARLY|ABSENTEE|MAIL|ADVANCE", regex=True) & ~g["mode"].eq("TOTAL")]["candidatevotes"].sum()
    rows.append(dict(state=st, county=cty.title(), year=int(yr), race="President", dem_votes=dem, rep_votes=rep,
                     other_votes=int(v.sum() - dem - rep), early_votes=int(early) if early > 0 else None))
new = pd.DataFrame(rows)
for st, n in new.groupby("state"):
    p = f"data/{st}/history_results.csv"
    old = pd.read_csv(p) if os.path.exists(p) else pd.DataFrame(columns=n.columns)
    have = set(zip(old["year"], old["race"]))
    add = n[[(y, r) not in have for y, r in zip(n["year"], n["race"])]]
    pd.concat([old, add], ignore_index=True).to_csv(p, index=False)
t = new.groupby(["state", "year"])[["dem_votes", "rep_votes"]].sum()
t["margin"] = ((t.dem_votes - t.rep_votes) / (t.dem_votes + t.rep_votes) * 100).round(2)
t["units"] = new.groupby(["state", "year"])["county"].nunique()
print(t["margin"].unstack("year").join(t["units"].unstack("year").add_prefix("n")).to_string())
