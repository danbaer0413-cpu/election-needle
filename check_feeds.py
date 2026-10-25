"""
Test every feed in config/feeds.csv before election night (run on Nov 2, and again once polls close).

    python check_feeds.py [--id TX-senate] [--feeds config/feeds.csv]

For each race with a URL: downloads it, shows the detected columns, how many counties matched your
counties.csv, and the statewide D/R totals. Fix feeds.csv until every line says OK.
"""
import argparse, os
import pandas as pd
from feeds import load_feed
from model import norm_name

ap = argparse.ArgumentParser(); ap.add_argument("--id"); ap.add_argument("--feeds", default="config/feeds.csv")
a = ap.parse_args()
import json
races = {r["id"]: r for r in json.load(open("config/races.json"))["races"]}
fd = pd.read_csv(a.feeds, dtype=str).fillna("")
bad = 0
for row in fd.to_dict("records"):
    rid = row["id"]
    if a.id and rid != a.id: continue
    if not row.get("url", "").strip():
        print(f"{rid:14s} (no url yet)"); continue
    try:
        res = load_feed(row)
        folder = races[rid].get("dir", f"data/{rid}")
        base = pd.read_csv(os.path.join(folder, "counties.csv"))
        have = {norm_name(c) for c in res["county"]}
        want = {norm_name(c) for c in base["county"]}
        miss = sorted(want - have)
        extra = sorted(have - want)
        d, r = res["dem"].sum(), res["rep"].sum()
        ok = len(res) > 0 and len(extra) <= max(2, 0.05 * len(res))   # early in the night most counties are not in the feed yet; that is normal
        print(f"{rid:14s} {'OK ' if ok else 'CHECK'} {len(res)} rows | matched {len(want)-len(miss)}/{len(want)} counties | D {d:,.0f} R {r:,.0f}")
        if miss and len(miss) < 0.5 * len(want): print("               not in feed yet  :", miss[:8])
        if extra: print("               IN FEED BUT NOT BASELINE (name mismatch?):", extra[:8])
        bad += 0 if ok else 1
    except Exception as ex:
        bad += 1
        print(f"{rid:14s} FAIL  {ex}")
print("\nall good" if not bad else f"\n{bad} feed(s) need attention")
