"""
Fallback when a state feed breaks: copy the county table from the state's results page and paste it.

    python paste_results.py TX-senate --cols dem,rep            # then paste, finish with Ctrl-D (Ctrl-Z Enter on Windows)
    python paste_results.py TX-senate --cols dem,rep,pct < table.txt

--cols is the order of the numbers on each line after the county name. Use dem, rep, other (ignored), pct
(percent reporting; 100 marks the county final). Lines that do not start with a known county are ignored.
Writes data/<race folder>/results.csv. run_update.py uses it automatically when the URL feed is missing or fails.
"""
import argparse, json, os, re, sys
import pandas as pd
from model import norm_name

ap = argparse.ArgumentParser(); ap.add_argument("id"); ap.add_argument("--cols", default="dem,rep")
a = ap.parse_args()
race = {r["id"]: r for r in json.load(open("config/races.json"))["races"]}[a.id]
folder = race.get("dir", f"data/{a.id}")
base = pd.read_csv(os.path.join(folder, "counties.csv"))
names = {norm_name(c): c for c in base["county"]}
cols = [c.strip() for c in a.cols.split(",")]
rows, unknown = [], []
for line in sys.stdin.read().splitlines():
    m = re.match(r"^\s*([A-Za-z.'\- ]+?)(?:\s+County)?\s*[\t ,|]+([\d,.%\-\t ,|]+)$", line)
    if not m: continue
    key = norm_name(m.group(1))
    nums = [float(x.replace(",", "").replace("%", "")) for x in re.findall(r"-?[\d,]*\.?\d+%?", m.group(2))]
    if key not in names:
        unknown.append(m.group(1)); continue
    if len(nums) < len(cols): continue
    rec = dict(zip(cols, nums)); rec["county"] = names[key]; rows.append(rec)
if not rows:
    sys.exit("no county rows recognised; check the paste and --cols")
df = pd.DataFrame(rows).drop_duplicates("county", keep="last")
out = pd.DataFrame({"county": df["county"], "dem": df["dem"], "rep": df["rep"]})
out["final"] = (df["pct"] >= 100) if "pct" in df else False
path = os.path.join(folder, "results.csv"); out.to_csv(path, index=False)
print(f"wrote {path}: {len(out)}/{len(base)} counties, D {out['dem'].sum():,.0f} R {out['rep'].sum():,.0f}")
if unknown: print("unrecognised names (ignored):", sorted(set(unknown))[:10])
