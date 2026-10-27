"""
Live U.S. House progress (% of each district counted) -> county % counted for the statewide mode.

config/house_sources.csv   name, url, sheet (browser = draw the page first), switch
config/switches.json       {"house": false}  (off until you have checked it with check_house.py on election night)

The reader is deliberately simple and cautious: it looks for district labels such as OH-07 or NC-11 in the page text and, between a label
and the next label, a "NN% reporting / in / counted". Anything it cannot read cleanly is skipped. Counts only go up, so a district's
number never goes down. It writes data/house/live.csv; run_update turns it into county % counted ONLY where the race has no real county
count and no typed reporting.csv entry. It never changes a vote count.
"""
from __future__ import annotations
import datetime as dt
import os
import re
import pandas as pd

LIVE = "data/house/live.csv"
STATES = ["AK", "FL", "GA", "IA", "KS", "ME", "MI", "MN", "MS", "NC", "NE", "NH", "NV", "OH", "SC", "TX", "WI"]
LABEL = re.compile(r"\b(" + "|".join(STATES) + r")\s*[-– ]\s*(0?\d{1,2}|AL)\b")
ANYLABEL = re.compile(r"\b[A-Z]{2}\s*[-\u2013]\s*(?:0?\d{1,2}|AL)\b")
PCT = [re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:of\s+(?:the\s+)?(?:expected\s+)?(?:votes?\s+)?)?(?:est\.?\s*)?(?:reporting|in\b|counted|of\s+votes)", re.I),
       re.compile(r"(?:reporting|counted|precincts?\s+reporting|est\.?\s*votes?\s+in)\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\s*%", re.I)]
SEATS = {"AK": 1, "FL": 28, "GA": 14, "IA": 4, "KS": 4, "ME": 2, "MI": 13, "MN": 8, "MS": 4, "NC": 14, "NE": 3, "NH": 2, "NV": 4, "OH": 15, "SC": 7, "TX": 38, "WI": 8}


def parse(text):
    """-> {(state, district): pct}. Takes the largest percent found next to each label; ignores anything over 100."""
    out = {}
    stops = [m.start() for m in ANYLABEL.finditer(text)]      # any other code like XX-NN ends a district's segment
    for m in LABEL.finditer(text):
        nxt = [p for p in stops if p > m.start()]
        end = min([m.end() + 400] + nxt[:1])
        seg = text[m.end(): end]
        st, d = m.group(1), m.group(2).upper()
        d = "1" if d == "AL" else d.lstrip("0") or "0"
        if int(d) > SEATS[st]:
            continue
        for rx in PCT:
            for pm in rx.finditer(seg):
                v = float(pm.group(1))
                if 0 <= v <= 100:
                    out[(st, d)] = max(out.get((st, d), 0.0), v)
    return out


def fetch_all(path="config/house_sources.csv", log=print):
    import feeds, sources
    if not os.path.exists(path):
        return {}
    s = pd.read_csv(path, dtype=str).fillna("")
    got = {}
    for row in s.to_dict("records"):
        sw = row.get("switch", "").strip()
        if sw and not sources.switch_on(sw):
            continue
        try:
            text = sources._text(row["url"], row.get("sheet", "").lower() == "browser")
            found = parse(text)
            log(f"  house source '{row.get('name')}': {len(found)} districts with a % counted")
            for k, v in found.items():
                got[k] = max(got.get(k, 0.0), v)
        except Exception as ex:
            log(f"  house source '{row.get('name')}' skipped ({str(ex)[:120]})")
    return got


def refresh(log=print):
    """Fetch, keep the larger of old and new per district, save data/house/live.csv."""
    import sources
    if not sources.switch_on("house"):
        return
    new = fetch_all(log=log)
    old = {}
    if os.path.exists(LIVE):
        try:
            for r in pd.read_csv(LIVE, dtype={"district": str}).to_dict("records"):
                old[(r["state"], str(r["district"]))] = float(r["pct_in"])
        except Exception:
            pass
    for k, v in new.items():
        old[k] = max(old.get(k, 0.0), v)
    if not old:
        return
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    pd.DataFrame([dict(state=k[0], district=k[1], pct_in=v, as_of_utc=now) for k, v in sorted(old.items())]).to_csv(LIVE, index=False)
    log(f"  house: {len(old)} districts saved to {LIVE}")


def county_pct_for(state, county_names):
    """{normalized county: % counted} from data/house/live.csv (empty if the house switch is off or no data)."""
    import sources
    from house_county import county_pct
    if not sources.switch_on("house") or not os.path.exists(LIVE):
        return {}
    try:
        d = pd.read_csv(LIVE, dtype={"district": str})
        d = d[d.state == state]
        return county_pct(state, {r.district: r.pct_in for r in d.itertuples()}, county_names)
    except Exception:
        return {}
