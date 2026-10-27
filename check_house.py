"""
Dry run for the House reader: shows what it reads from each House source right now. Writes nothing, changes nothing in the model.

  python check_house.py            (reads every row of config/house_sources.csv, ignoring the on/off switches)
  python check_house.py --file page.txt     (parse a saved page text instead)
Compare the printout to the page. If the percents match, set "house": true in config/switches.json.
"""
import sys
import pandas as pd
import house_live

if "--file" in sys.argv:
    found = house_live.parse(open(sys.argv[sys.argv.index("--file") + 1], encoding="utf-8", errors="replace").read())
else:
    import sources
    s = pd.read_csv("config/house_sources.csv", dtype=str).fillna("")
    found = {}
    for row in s.to_dict("records"):
        try:
            t = sources._text(row["url"], row.get("sheet", "").lower() == "browser")
            f = house_live.parse(t)
            print(f"{row['name']}: {len(f)} districts read from {row['url']}  (page text length {len(t):,})")
            for k, v in f.items():
                found[k] = max(found.get(k, 0), v)
        except Exception as ex:
            print(f"{row['name']}: FAILED ({str(ex)[:160]})")
for (st, d), v in sorted(found.items(), key=lambda x: (x[0][0], int(x[0][1]))):
    print(f"  {st}-{int(d):02d}  {v:g}% counted")
print(f"{len(found)} districts read.")
