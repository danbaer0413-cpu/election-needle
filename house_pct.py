"""
House district % reporting -> county % reporting for a Senate/governor race (election-night helper).

  python house_pct.py MI-senate 13=85 12=60 11=70 [--keep]

Each district=PCT is the % of that district's vote counted (the House results page shows it). For every county the crosswalk
(data/house/crosswalk.csv) says what share of the county's vote sits in each district; the county's % counted is the share-weighted
average of the districts you gave, and it is written to reporting.csv (county,pct_in), where statewide mode uses it to place the
counted vote. A county is skipped if the districts you gave cover less than half of it. Counties with no share (list-only rows)
split their vote equally across their districts. Needs a State total in statewide.csv to matter (see STATEWIDE.md).
Not for OH (crosswalk is on old lines, so the script refuses it). FL and TX use the 2026 crosswalk; split counties missing a share are split equally, so treat those as rough.
"""
import argparse, json, os
import pandas as pd
from model import norm_name
from house_county import county_pct, REFUSE

ap = argparse.ArgumentParser()
ap.add_argument("id"); ap.add_argument("district", nargs="+", help="DISTRICT=PCT, e.g. 13=85"); ap.add_argument("--keep", action="store_true")
a = ap.parse_args()
race = {r["id"]: r for r in json.load(open("config/races.json"))["races"]}.get(a.id)
if not race:
    raise SystemExit(f"unknown race id {a.id}")
st = race["state"]
if st in REFUSE:
    raise SystemExit(f"{st}: crosswalk is on old lines; use county screenshots instead")
folder = race.get("dir", f"data/{a.id}")
base = pd.read_csv(os.path.join(folder, "counties.csv"))
pcts = {}
for item in a.district:
    d, _, v = item.partition("=")
    pcts[d.strip()] = float(v)
res = county_pct(st, pcts, base["county"])
names = {norm_name(c): c for c in base["county"]}
rows = [dict(county=names[k], pct_in=v) for k, v in res.items()]
path = os.path.join(folder, "reporting.csv")
new = pd.DataFrame(rows)
if a.keep and os.path.exists(path):
    old = pd.read_csv(path)
    new = pd.concat([old[~old.county.isin(new.county)], new], ignore_index=True)
new.to_csv(path, index=False)
print(f"wrote {path}: {len(rows)} counties from districts {sorted(pcts)}")
