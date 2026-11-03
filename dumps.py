"""Vote-dump log: every batch of votes the update run saw, county by county (display only; the model never reads this).

    python dumps.py            (run by the update workflow right after run_update.py)

Compares the per-county counted votes in data/latest.json with the previous run's snapshot (data/dumps_prev.json) and appends one row
per county whose count changed to data/vote_dumps.csv:
  ts_utc, race, state, county, kind, added, batch_net, batch_margin, county_pct_in, race_pct_in, needle
    kind          county      a county reported new votes
                  statewide   the state only reported a total (the model spreads it over counties), so it is logged once, for the state
                  correction  a county's count went DOWN (a feed fixed a number)
    added         new votes in this batch
    batch_net     Dem minus GOP votes in the batch (from the counted margin before and after; approximate when third parties are big)
    batch_margin  batch_net as % of the batch
    needle        the race's needle (median margin) after this update
    dem_votes, rep_votes   the batch split by candidate: (added +/- batch_net) / 2. The model counts Dem + GOP votes only, so these add up
                  to `added`; worked out from the rounded counted margin, so good to about +/-0.05% of the county's running total
Anything that fails here is printed and skipped: it can never stop the update or touch the forecast.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os

import numpy as np

LATEST, PREV, OUT = "data/latest.json", "data/dumps_prev.json", "data/vote_dumps.csv"
MIN_VOTES = 100          # smaller changes are noise / rounding
KEEP = 6000              # newest rows kept in the csv
FIELDS = ["ts_utc", "race", "state", "county", "kind", "added", "batch_net", "batch_margin", "county_pct_in", "race_pct_in", "needle",
          "dem_votes", "rep_votes"]


def snapshot(latest: dict) -> dict:
    snap = {}
    for rid, r in (latest.get("races") or {}).items():
        s = r.get("summary") or {}
        rows = {}
        for t in s.get("table") or []:
            n = float(t.get("counted") or 0)
            m = float(t.get("counted_margin") or 0)
            exp = n + float(t.get("remaining") or 0)
            rows[str(t.get("county"))] = [n, n * m / 100.0, exp, float(t.get("pct_in") or 0)]
        snap[rid] = {"counties": rows, "pct_in": float(s.get("pct_in") or 0), "median": s.get("median")}
    return snap


def split(add, net):
    """batch votes by candidate (Dem, GOP), never below zero"""
    d = max(0.0, min(add, (add + net) / 2))
    return [round(d), round(add - d)]


def diff(prev: dict, cur: dict, ts: str) -> list[list]:
    out = []
    for rid, c in cur.items():
        p = (prev.get(rid) or {}).get("counties") or {}
        st = rid.split("-")[0]
        ups, downs = [], []
        for county, (n, net, exp, pin) in c["counties"].items():
            n0, net0 = (p.get(county) or [0.0, 0.0])[:2]
            add = n - n0
            if add >= MIN_VOTES:
                ups.append((county, add, net - net0, exp, pin))
            elif add <= -MIN_VOTES:
                downs.append((county, add, net - net0, exp, pin))
        tail = [round(c["pct_in"], 1), None if c["median"] is None else round(float(c["median"]), 2)]
        # a statewide total spread over counties shows up as every county growing by the same share of its expected vote
        share = np.array([a / e for _, a, _, e, _ in ups if e > 0])
        if len(share) >= 8 and share.mean() > 0 and share.std() / share.mean() < 0.02:
            add = sum(a for _, a, _, _, _ in ups)
            net = sum(x for _, _, x, _, _ in ups)
            out.append([ts, rid, st, "Statewide total", "statewide", round(add), round(net), round(100 * net / add, 1) if add else 0.0, None] + tail
                       + split(add, net))
        else:
            for county, add, net, _, pin in sorted(ups, key=lambda x: -x[1]):
                out.append([ts, rid, st, county, "county", round(add), round(net), round(max(-100, min(100, 100 * net / add)), 1), round(pin, 1)] + tail
                           + split(add, net))
        for county, add, net, _, pin in downs:
            out.append([ts, rid, st, county, "correction", round(add), round(net), None, round(pin, 1)] + tail + ["", ""])
    return out


def main():
    latest = json.load(open(LATEST))
    cur = snapshot(latest)
    ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    prev = json.load(open(PREV)) if os.path.exists(PREV) else None
    rows = diff(prev, cur, ts) if prev is not None else []
    if prev is None:
        print("vote dumps: first run, snapshot saved (nothing to compare yet)")
    old = []
    if os.path.exists(OUT):
        with open(OUT, newline="") as f:
            old = list(csv.reader(f))[1:]
    allrows = (old + rows)[-KEEP:]
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        w.writerows(allrows)
    with open(PREV, "w") as f:
        json.dump(cur, f)
    print(f"vote dumps: {len(rows)} new batches logged -> {OUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"vote dumps skipped ({str(ex)[:150]})")
