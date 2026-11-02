"""
Live vote counts from civicAPI (civicapi.org, free; credit them) as a results source for the model.

Used by sources.py for rows with scope = civic (config/sources.csv). For one race id (e.g. MI-senate) it
  1. finds civicAPI's race for that state, date and office (cached in data/civic_race_ids.json),
  2. reads candidates' statewide votes and the county / district breakdown (region_results),
  3. returns (county table with dem, rep, final) and (statewide dict dem, rep).
Dem and Rep are picked by surname from config/candidates.csv first, then by party label. Races flagged test_data are
skipped unless CIVIC_ALLOW_TEST=1. Anything it cannot read is skipped and logged; it never raises into the update run.

Rehearse on a past election:   python civic_results.py --date 2024-11-05 --only TX-senate
Check every race for Nov 3:     python civic_results.py
"""
from __future__ import annotations

import argparse
import json
import os
import re

import pandas as pd

BASE = "https://civicapi.org/api/v2"
UA = {"User-Agent": "election-needle (personal, non-commercial; attribution civicapi.org)"}
DATE = "2026-11-03"
CACHE = "data/civic_race_ids.json"
PROBE = "data/civic_probe.json"
DEM_WORDS = ("democrat", "dem", "dfl")
REP_WORDS = ("republican", "rep", "gop")


_FAILS = [0]
_T0 = [None]
BUDGET_S = 100          # all civicAPI calls in one update run must finish within this many seconds; then it is skipped


def _get(path, timeout=12):
    """One GET. After 3 failures in a run, civicAPI is skipped for the rest of that run, so a slow or down API cannot stall the update."""
    import requests
    import time
    if _FAILS[0] >= 3:
        raise RuntimeError("civicAPI skipped for this run after 3 failures")
    _T0[0] = _T0[0] or time.time()
    if time.time() - _T0[0] > BUDGET_S:
        raise RuntimeError(f"civicAPI time budget ({BUDGET_S}s) used up for this run")
    try:
        r = requests.get(BASE + path, headers=UA, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        _FAILS[0] += 1
        raise


def _kind(name: str):
    n = str(name)
    if "primary" in n.lower() or "runoff" in n.lower():
        return None
    if "Senate" in n and "State Senate" not in n:
        return "senate"
    if "Governor" in n and not re.search(r"Lieutenant|Board|College|University", n):
        return "governor"
    return None


def _date_ok(r, date):
    """True unless the race carries a date field that differs from the one we want."""
    for k in ("election_date", "date", "electionDate"):
        v = r.get(k)
        if v:
            return str(v)[:10] == date
    return True


def _want(rid: str):
    return "governor" if rid.lower().endswith("governor") else "senate"


def find_race(rid: str, state: str, date: str = DATE, get=None, log=print):
    """civicAPI race id for our race, cached per (race, date)."""
    get = get or _get
    cache = {}
    if os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE))
        except Exception:
            cache = {}
    key = f"{rid}|{date}"
    if key in cache:
        return cache[key]
    want, hits, off = _want(rid), [], 0
    if date == DATE and os.path.exists(PROBE):          # race ids saved by the civic-probe workflow: no searching on the night
        try:
            pj = json.load(open(PROBE))
            pr = (pj.get("states", {}).get(state, {}).get("races") or []) if pj.get("version", 1) >= 2 else []
            hits = [{"id": x[1], "election_name": x[2]} for x in pr if x[0] == want]
        except Exception:
            hits = []
    while not hits and off < 5000:
        sk = (state, date, off)
        # startDate/endDate are civicAPI's date filters (a plain `date=` is ignored and returns every year); limit up to 50000
        js = _SEARCH.get(sk) or get(f"/race/search?country=US&province={state}&startDate={date}&endDate={date}&limit=1000&offset={off}")
        _SEARCH[sk] = js
        races = (js or {}).get("races") or []
        for r in races:
            if _kind(r.get("election_name")) == want and _date_ok(r, date):
                hits.append(r)
        if len(races) < 1000:
            break
        off += 1000
    if not hits:
        log(f"  civicAPI: no {want} race for {state} on {date}")
        return None
    if len(hits) > 1:      # two Senate races in one state (regular + special): prefer the special for ids that say so
        spec = [h for h in hits if "special" in str(h.get("election_name", "")).lower()]
        hits = spec if (rid in SPECIAL and spec) else ([h for h in hits if h not in spec] or hits)
    cache[key] = hits[0]["id"]
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(cache, open(CACHE, "w"), indent=1)
    except Exception:
        pass
    return cache[key]


# First poll closing in each state, UTC, Nov 3 2026 (EST = UTC-5). Before it, any civicAPI numbers are ignored, even if
# test_data is off, so a premature or leftover test result can never move a needle.
POLL_CLOSE_UTC = {"GA": "2026-11-04T00:00", "SC": "2026-11-04T00:00", "FL": "2026-11-04T00:00", "NH": "2026-11-04T00:00",
                  "NC": "2026-11-04T00:30", "OH": "2026-11-04T00:30", "ME": "2026-11-04T01:00", "MI": "2026-11-04T01:00",
                  "MS": "2026-11-04T01:00", "TX": "2026-11-04T01:00", "KS": "2026-11-04T01:00", "MN": "2026-11-04T02:00",
                  "NE": "2026-11-04T02:00", "WI": "2026-11-04T02:00", "IA": "2026-11-04T03:00", "NV": "2026-11-04T03:00",
                  "AK": "2026-11-04T05:00"}


def polls_closed(state, now=None):
    import datetime as _dt
    now = now or _dt.datetime.now(_dt.timezone.utc)
    t = POLL_CLOSE_UTC.get(state, "2026-11-03T23:00")
    return now >= _dt.datetime.fromisoformat(t).replace(tzinfo=_dt.timezone.utc)


SPECIAL = {"OH-senate", "FL-senate"}
_SEARCH: dict = {}      # U.S. Senate (special) in config/races.json


def _surnames(rid):
    try:
        import sources
        return sources._surnames(rid)
    except Exception:
        return None, None


def _side(label, party, dem_sn, rep_sn, by_party=(True, True)):
    """'D', 'R' or None for one candidate / party label. Surname first. When our candidate's surname is on the ballot,
    other candidates of the same party do NOT count for that side (Alaska's top-four general can have several Republicans);
    by_party = (use party label for D, use it for R) is False for a side whose surname was found."""
    lab = str(label or "").lower()
    if dem_sn and dem_sn.lower() in lab:
        return "D"
    if rep_sn and rep_sn.lower() in lab:
        return "R"
    p = str(party or label or "").lower().strip()       # region tables keyed by party name ('Democratic': {...}) use the label
    if by_party[0] and (p in ("d", "dem") or any(w in p for w in ("democrat", "dfl"))):
        return "D"
    if by_party[1] and (p in ("r", "rep", "gop") or "republican" in p):
        return "R"
    return None


def _num(v):
    if isinstance(v, dict):
        for k in ("votes", "vote", "count", "total"):
            if k in v:
                return _num(v[k])
        return None
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def _pairs(x, cand_party):
    """Flatten one region's payload into [(label, party, votes)]. Handles a list of candidate dicts, a dict of
    {candidate or party: votes or {votes: n}}, and a dict holding such a list under candidates/results."""
    out = []
    if isinstance(x, list):
        for c in x:
            if isinstance(c, dict):
                lab = c.get("name") or c.get("candidate") or c.get("candidate_name") or c.get("id")
                out.append((lab, c.get("party") or cand_party.get(str(lab)), _num(c)))
    elif isinstance(x, dict):
        for k in ("candidates", "results", "votes_by_candidate"):
            if isinstance(x.get(k), (list, dict)):
                return _pairs(x[k], cand_party)
        for lab, v in x.items():
            if lab in ("percent_reporting", "pct", "name", "region", "id", "total", "precincts_reporting", "precincts_total"):
                continue
            n = _num(v)
            if n is not None:
                out.append((lab, (v.get("party") if isinstance(v, dict) else None) or cand_party.get(str(lab)), n))
    return out


def _region_pct(x):
    if isinstance(x, dict):
        for k in ("percent_reporting", "pct", "pct_reporting"):
            if x.get(k) is not None:
                try:
                    return float(x[k])
                except Exception:
                    pass
    return None


def _regions(rr):
    """[(region name, payload)] from region_results as a dict or a list."""
    if isinstance(rr, dict):
        out = []
        for key, item in rr.items():                     # civicAPI: {"slug": {"name": "Dane", "type": "County", "candidates": [...]}}
            if isinstance(item, dict) and str(item.get("type", "")).lower() == "state":
                continue
            nm = item.get("name") if isinstance(item, dict) and item.get("name") else key
            out.append((nm, item))
        return out
    out = []
    for item in rr or []:
        if isinstance(item, dict):
            nm = item.get("name") or item.get("region") or item.get("county") or item.get("region_name")
            if nm is not None and str(item.get("type", "")).lower() != "state":
                out.append((nm, item))
    return out


def _clean_region(name, state):
    s = str(name).strip()
    s = re.sub(r"\s+(County|Parish|Borough|Census Area)$", "", s, flags=re.I)
    if state == "AK":                                       # our Alaska units are 'District 01' ... 'District 40'
        m = re.search(r"(\d+)", s)
        if m and "district" in s.lower():
            s = f"District {int(m.group(1)):02d}"
    return s


def read_race(rid: str, state: str, date: str = DATE, get=None, log=print):
    """-> (county DataFrame or None, statewide dict or None, info dict)."""
    get = get or _get
    cid = find_race(rid, state, date, get=get, log=log)
    if cid is None:
        return None, None, {}
    d = get(f"/race/{cid}?data=json") or {}
    info = {"civic_id": cid, "name": d.get("election_name"), "pct": d.get("percent_reporting"), "test_data": d.get("test_data")}
    if d.get("test_data") and os.environ.get("CIVIC_ALLOW_TEST") != "1":
        log(f"  civicAPI {rid}: race flagged test_data; not used")
        return None, None, info
    if not polls_closed(state) and os.environ.get("CIVIC_ALLOW_TEST") != "1":
        log(f"  civicAPI {rid}: polls not closed yet in {state}; numbers not used")
        return None, None, info
    dem_sn, rep_sn = _surnames(rid)
    cands = d.get("candidates") or []
    cand_party = {str(c.get("name")): c.get("party") for c in cands if isinstance(c, dict)}
    names = [str(c.get("name", "")).lower() for c in cands if isinstance(c, dict)]
    bp = (not (dem_sn and any(dem_sn.lower() in x for x in names)), not (rep_sn and any(rep_sn.lower() in x for x in names)))
    D = R = 0.0
    for c in cands:
        if not isinstance(c, dict):
            continue
        side, n = _side(c.get("name"), c.get("party"), dem_sn, rep_sn, bp), _num(c)
        if side == "D" and n:
            D += n
        elif side == "R" and n:
            R += n
    sw = dict(dem=D, rep=R) if D + R > 0 else None
    rows = []
    for name, payload in _regions(d.get("region_results")):
        if str(name).strip().lower() in ("statewide", "total", state.lower()):
            continue
        dd = rr = 0.0
        for lab, party, n in _pairs(payload, cand_party):
            side = _side(lab, party, dem_sn, rep_sn, bp)
            if side == "D" and n:
                dd += n
            elif side == "R" and n:
                rr += n
        if dd + rr > 0:
            pct = _region_pct(payload)
            rows.append(dict(county=_clean_region(name, state), dem=dd, rep=rr, final=bool(pct is not None and pct >= 100)))
    df = pd.DataFrame(rows) if rows else None
    info.update(regions=len(rows), D=D, R=R)
    return df, sw, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=DATE)
    ap.add_argument("--only", default=None)
    ap.add_argument("--config", default="config/races.json")
    a = ap.parse_args()
    global BUDGET_S
    BUDGET_S = 900          # a standalone check may take longer than the 100 s allowed inside an update run
    from model import norm_name
    races = json.load(open(a.config))["races"]
    for r in races:
        if a.only and r["id"] != a.only:
            continue
        try:
            df, sw, info = read_race(r["id"], r["state"], a.date)
        except Exception as ex:
            print(f"{r['id']}: ERROR {str(ex)[:150]}")
            continue
        base = pd.read_csv(os.path.join(r["dir"], "counties.csv"))
        bk = set(base["county"].astype(str).map(norm_name))
        if df is not None:
            got = set(df["county"].astype(str).map(norm_name))
            miss = sorted(got - bk)[:6]
            print(f"{r['id']}: {info.get('name')} | statewide D {info.get('D', 0):,.0f} R {info.get('R', 0):,.0f} | {len(df)} regions, "
                  f"{len(got & bk)}/{len(bk)} match our counties" + (f" | not matched: {miss}" if miss else ""))
        else:
            print(f"{r['id']}: {info.get('name')} | statewide {sw} | no county breakdown | {info}")


if __name__ == "__main__":
    main()
