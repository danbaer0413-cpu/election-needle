"""
Live House results for the map's hover box, from civicAPI (civicapi.org, free; credit them).

For every district on the House map (data/house/lean.json) it finds civicAPI's Nov 3 race ("Georgia US House 5",
"Alaska US House At-Large"), reads the top two candidates' votes and the percent reporting, and attaches them to the
district as d["live"] = {"a": [name, party, votes, pct], "b": [...], "pct_in": n, "as_of": iso}.
Display only: it never changes a lean, a call or a seat count. Races flagged test_data are shown as "no results yet".
One search per state plus one request per district; after 3 failures civicAPI is skipped for the rest of the run.
Fetched at most every EVERY_MIN minutes (default 30); between fetches the last numbers are carried over.
Off switch: "house_results": false in config/switches.json.
"""
from __future__ import annotations

import datetime as dt
import re

BASE = "https://civicapi.org/api/v2"
UA = {"User-Agent": "election-needle (personal, non-commercial; attribution civicapi.org)"}
DATE = "2026-11-03"
EVERY_MIN = 30
NAME = re.compile(r"US House\s+(\d+|At[- ]Large)\b", re.I)
_FAILS = [0]
_T0 = [None]
BUDGET_S = 75           # the House lookups get at most this many seconds per run (display only)


def _get(path, timeout=12):
    import requests
    import time
    if _FAILS[0] >= 3:
        raise RuntimeError("civicAPI skipped for this run after 3 failures")
    _T0[0] = _T0[0] or time.time()
    if time.time() - _T0[0] > BUDGET_S:
        raise RuntimeError(f"House results time budget ({BUDGET_S}s) used up")
    try:
        r = requests.get(BASE + path, headers=UA, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        _FAILS[0] += 1
        raise


def district_ids(state: str, get=None) -> dict:
    """{'5': id, 'AL': id} for one state's Nov 3 general House races (specials, runoffs and primaries left out)."""
    get = get or _get
    out, off = {}, 0
    while off < 20000:
        js = get(f"/race/search?country=US&province={state}&startDate={DATE}&endDate={DATE}&limit=1000&offset={off}") or {}
        races = js.get("races") or []
        for r in races:
            nm = str(r.get("election_name") or "")
            if re.search(r"Special|Runoff|Primary", nm, re.I):
                continue
            m = NAME.search(nm)
            if m:
                k = "AL" if not m.group(1).isdigit() else str(int(m.group(1)))
                out.setdefault(k, r["id"])
        if len(races) < 1000:
            break
        off += 1000
    return out


def _party(p):
    p = str(p or "").lower()
    return "D" if p.startswith("democ") or p == "dfl" else "R" if p.startswith("republ") else (p[:3].upper() or "?")


def race_live(rid, get=None, now=None):
    import os
    get = get or _get
    now = now or dt.datetime.now(dt.timezone.utc)
    if now < dt.datetime(2026, 11, 3, 23, 0, tzinfo=dt.timezone.utc) and os.environ.get("CIVIC_ALLOW_TEST") != "1":
        return None                                   # before the first polls close (6 pm ET): nothing real to show
    d = get(f"/race/{rid}?data=json&light=true") or {}
    if d.get("test_data") and os.environ.get("CIVIC_ALLOW_TEST") != "1":
        return None
    cands = [c for c in (d.get("candidates") or []) if isinstance(c, dict)]
    tot = sum(float(c.get("votes") or 0) for c in cands)
    if tot <= 0:
        return None
    top = sorted(cands, key=lambda c: -float(c.get("votes") or 0))[:2]
    row = lambda c: [str(c.get("name", "")), _party(c.get("party")), int(float(c.get("votes") or 0)), round(float(c.get("votes") or 0) / tot * 100, 1)]
    return {"a": row(top[0]), "b": row(top[1]) if len(top) > 1 else None,
            "pct_in": d.get("percent_reporting"), "winner": next((_party(c.get("party")) for c in cands if c.get("winner")), None),
            "as_of": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}


def attach(h: dict, get=None, log=print) -> int:
    """Adds d['live'] to the districts in h (in place). Returns how many districts got numbers."""
    n, ids = 0, {}
    for st in sorted({d["state"] for d in h.get("districts", [])}):
        try:
            ids[st] = district_ids(st, get)
        except Exception as ex:
            log(f"  house results: {st} search skipped ({str(ex)[:80]})")
            ids[st] = {}
    for d in h.get("districts", []):
        k = "AL" if str(d["district"]).upper() in ("AL", "0") else str(int(d["district"])) if str(d["district"]).isdigit() else str(d["district"])
        rid = ids.get(d["state"], {}).get(k)
        if rid is None:
            continue
        try:
            lv = race_live(rid, get)
        except Exception:
            lv = None
        if lv:
            d["live"] = lv
            n += 1
    log(f"  house results: live numbers for {n} of {len(h.get('districts', []))} map districts (civicAPI)")
    return n


def attach_throttled(h: dict, old_path: str, every_min: float = None, log=print, get=None, now=None) -> str:
    """Fetch fresh results if the last fetch (saved in the old lean.json) is EVERY_MIN+ minutes old; otherwise copy the
    previous numbers onto the new districts. Returns 'fetched' or 'carried'."""
    import json
    import os
    every_min = EVERY_MIN if every_min is None else every_min
    now = now or dt.datetime.now(dt.timezone.utc)
    old = {}
    try:
        old = json.load(open(old_path)) if os.path.exists(old_path) else {}
    except Exception:
        old = {}
    last = old.get("live_fetched_at")
    try:
        age = (now - dt.datetime.fromisoformat(last)).total_seconds() / 60 if last else None
    except Exception:
        age = None
    if age is not None and age < every_min:
        prev = {(d["state"], str(d["district"])): d.get("live") for d in old.get("districts", []) if d.get("live")}
        for d in h.get("districts", []):
            lv = prev.get((d["state"], str(d["district"])))
            if lv:
                d["live"] = lv
        h["live_fetched_at"] = last
        log(f"  house results: kept numbers from {age:.0f} min ago (refresh every {every_min:.0f} min)")
        return "carried"
    attach(h, get=get, log=log)
    h["live_fetched_at"] = now.isoformat(timespec="seconds")
    return "fetched"
