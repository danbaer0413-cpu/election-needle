"""
Preflight: run `python check_setup.py` before pushing. Exits nonzero if something that would silently blank a needle is wrong.
Checks: every race has a baseline (counties.csv) and a candidates row, config files parse, fundamentals cover all races
(NE-senate is excluded on purpose), and no input is stale.
"""
from __future__ import annotations
import datetime as dt, json, os, sys
import pandas as pd

bad, warn = [], []
cfg = json.load(open("config/races.json"))["races"]
cand = pd.read_csv("config/candidates.csv")["id"].tolist() if os.path.exists("config/candidates.csv") else []
feeds = pd.read_csv("config/feeds.csv")["id"].tolist() if os.path.exists("config/feeds.csv") else []
for r in cfg:
    rid = r["id"]; folder = r.get("dir", f"data/{rid}")
    if not os.path.exists(os.path.join(folder, "counties.csv")):
        bad.append(f"{rid}: missing {folder}/counties.csv")
    if rid not in cand: warn.append(f"{rid}: not in config/candidates.csv (poll pull skips it)")
    if rid not in feeds: warn.append(f"{rid}: not in config/feeds.csv")
try:
    from fundamentals import compute
    fm = compute(out=None)
    fcfg = json.load(open("config/fundamentals.json"))
    miss = [r["id"] for r in cfg if r["id"] not in fm and r["id"] not in fcfg.get("skip_races", [])]
    if miss: warn.append(f"no fundamentals for: {', '.join(miss)}")
except Exception as ex:
    bad.append(f"fundamentals failed: {ex}")
if not os.path.exists('config/poll_error.json'): warn.append('config/poll_error.json missing: run python poll_error_fit.py')
for f, days in (("data/poll_inputs_2026.csv", 14), ("data/poll_inputs_auto.csv", 3), ("data/latest.json", 2)):
    if os.path.exists(f):
        age = (dt.datetime.now() - dt.datetime.fromtimestamp(os.path.getmtime(f))).days
        if age > days: warn.append(f"{f} is {age} days old")
    elif f != "data/latest.json":
        warn.append(f"{f} not found (first run creates it)" if "auto" in f else f"{f} not found")
print(f"{len(cfg)} races checked")
for w in warn: print("  warn:", w)
for b in bad: print("  FAIL:", b)
print("OK" if not bad else "PROBLEMS FOUND")
sys.exit(1 if bad else 0)
