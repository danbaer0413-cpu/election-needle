"""
Louisiana Secretary of State live results: district totals for one race (no parish breakdown in this file).

The state's results page (voterportal.sos.la.gov/graphical) loads two JSON files per election date:
  Data?blob=<YYYYMMDD>/RacesCandidates_Multiparish.htm   race ids, titles and candidate ids ("Patricia \"Pat\" Moore (DEM)")
  Data?blob=<YYYYMMDD>/Votes_Multiparish.htm             votes per candidate id, precincts reporting / expected
Used by sources.py for rows with scope = la_sos (config/sources.csv, column sheet = the state's race id, e.g. 71423).
Returns the district total as a statewide dict for the model and a cross-check against civicAPI's count
(data/runoff_check.csv), so a stale or wrong feed shows up on the night.

Check by hand:   python la_sos.py LA-house-5
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import sys

BASE = "https://voterportal.sos.la.gov/ElectionResults/ElectionResults/Data?blob="
UA = {"User-Agent": "Mozilla/5.0 (election-needle; personal, non-commercial)", "Referer": "https://voterportal.sos.la.gov/graphical",
      "Accept": "application/json, text/javascript, */*"}
CHECK = "data/runoff_check.csv"


def _get(blob, timeout=15):
    import requests
    r = requests.get(BASE + blob, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _list(x):
    return x if isinstance(x, list) else ([x] if x else [])


def read(rid: str, race_id: str, date: str, dem_sn: str, rep_sn: str, get=None):
    """-> dict(dem, rep, pct_in, precincts, expected, title). date is YYYY-MM-DD."""
    get = get or _get
    ymd = date.replace("-", "")
    rc = get(f"{ymd}/RacesCandidates_Multiparish.htm")
    vt = get(f"{ymd}/Votes_Multiparish.htm")
    race = next((r for r in _list(rc["Races"]["Race"]) if str(r["ID"]) == str(race_id)), None)
    votes = next((r for r in _list(vt["Races"]["Race"]) if str(r["ID"]) == str(race_id)), None)
    if race is None or votes is None:
        raise ValueError(f"race {race_id} not in the state's {date} files")
    side = {}
    for c in _list(race["Choice"]):
        d = str(c.get("Desc", ""))
        if dem_sn and dem_sn.lower() in d.lower() or re.search(r"\(DEM\)", d):
            side[str(c["ID"])] = "D"
        elif rep_sn and rep_sn.lower() in d.lower() or re.search(r"\(REP\)", d):
            side[str(c["ID"])] = "R"
    D = R = 0.0
    for c in _list(votes["Choice"]):
        n = float(str(c.get("VoteTotal") or 0).replace(",", ""))
        if side.get(str(c["ID"])) == "D":
            D += n
        elif side.get(str(c["ID"])) == "R":
            R += n
    pr, pe = int(votes.get("PrecinctsReporting") or 0), int(votes.get("PrecinctsExpected") or 0)
    return dict(dem=D, rep=R, pct_in=round(100 * pr / pe, 1) if pe else None, precincts=pr, expected=pe,
                title=race.get("SpecificTitle"))


def log_check(rid, state_tot, civic_tot, log=print):
    """Append one row comparing the state's district total with civicAPI's sum, and log a warning when they disagree by more
    than 5% of the larger count (one feed lagging a little behind is normal; a different winner or a big gap is not)."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")
    s = state_tot["dem"] + state_tot["rep"]
    c = (civic_tot or {}).get("dem", 0) + (civic_tot or {}).get("rep", 0)
    m = lambda t: round(100 * (t["dem"] - t["rep"]) / (t["dem"] + t["rep"]), 2) if t and t["dem"] + t["rep"] else None
    gap = abs(s - c) / max(s, c) if max(s, c) else 0.0
    flag = "ok"
    if c and gap > 0.05:
        flag = "counts differ"
    if c and s and m(state_tot) * m(civic_tot) < 0:
        flag = "leaders differ"
    if flag != "ok":
        log(f"  WARNING {rid}: state total {s:,.0f} ({m(state_tot):+.1f}) vs civicAPI {c:,.0f} ({m(civic_tot):+.1f}): {flag}")
    new = not os.path.exists(CHECK)
    try:
        os.makedirs(os.path.dirname(CHECK), exist_ok=True)
        with open(CHECK, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["checked", "race", "state_dem", "state_rep", "state_pct_in", "civic_dem", "civic_rep", "flag"])
            w.writerow([now, rid, state_tot["dem"], state_tot["rep"], state_tot.get("pct_in"),
                        (civic_tot or {}).get("dem"), (civic_tot or {}).get("rep"), flag])
    except Exception:
        pass
    return flag


if __name__ == "__main__":
    import pandas as pd
    import civic_results
    rid = sys.argv[1]
    s = pd.read_csv("config/sources.csv", dtype=str).fillna("")
    row = s[(s.id == rid) & (s.scope == "la_sos")].iloc[0]
    c = pd.read_csv("config/candidates.csv", dtype=str).set_index("id")
    print(read(rid, row.sheet, civic_results.race_date(rid), c.loc[rid, "dem"], c.loc[rid, "rep"]))
