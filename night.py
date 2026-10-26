"""
Election-night helper: write a race's statewide.csv / reporting.csv without opening a spreadsheet.

  python night.py MI-senate --dem 1523400 --rep 1488200 --pct 41
  python night.py MI-senate --county Wayne=85 Oakland=100:310200:285000 Macomb=70
      county=PCT            that county's % of expected vote counted
      county=PCT:DEM:REP    same, with its real vote counts
  python night.py MI-senate --county Wayne=85 --keep      (add to the existing reporting.csv instead of replacing it)
      --force                 the numbers beat scraped ones for 60 minutes (--minutes N to change); use it to correct a bad scrape
Then commit data/<race folder>/statewide.csv and reporting.csv and run the update workflow.
See STATEWIDE.md. Statewide-only numbers carry less weight in the model than real county counts (about one county's worth).
"""
import argparse, datetime as dt, json, os
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("id")
ap.add_argument("--dem", type=float); ap.add_argument("--rep", type=float); ap.add_argument("--pct", type=float)
ap.add_argument("--county", nargs="*", default=[])
ap.add_argument("--keep", action="store_true")
ap.add_argument("--force", action="store_true", help="these numbers override scraped ones for --minutes (default 60)")
ap.add_argument("--minutes", type=float, default=60)
a = ap.parse_args()
race = {r["id"]: r for r in json.load(open("config/races.json"))["races"]}.get(a.id)
if not race:
    raise SystemExit(f"unknown race id {a.id}")
folder = race.get("dir", f"data/{a.id}")
now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
now_utc = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
if a.dem is not None and a.rep is not None:
    pd.DataFrame([dict(dem=a.dem, rep=a.rep, pct_in=a.pct, as_of=now, as_of_utc=now_utc, force="yes" if a.force else "", force_minutes=a.minutes if a.force else "")]).to_csv(os.path.join(folder, "statewide.csv"), index=False)
    print(f"wrote {folder}/statewide.csv  D {a.dem:,.0f} R {a.rep:,.0f}")
if a.county:
    rows = []
    for item in a.county:
        name, _, rest = item.partition("=")
        bits = rest.split(":")
        r = dict(county=name.strip(), pct_in=float(bits[0]))
        if len(bits) == 3:
            r.update(dem=float(bits[1]), rep=float(bits[2]))
        rows.append(r)
    path = os.path.join(folder, "reporting.csv")
    new = pd.DataFrame(rows)
    if a.keep and os.path.exists(path):
        old = pd.read_csv(path)
        new = pd.concat([old[~old.county.isin(new.county)], new], ignore_index=True)
    new.to_csv(path, index=False)
    print(f"wrote {path} ({len(new)} counties)")
