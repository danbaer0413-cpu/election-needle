"""
Pull individual 2026 Senate/governor polls from PollResults.org (free API, NYT poll data, CC BY 4.0,
non-commercial) and average them into data/poll_inputs_auto.csv.

    python fetch_polls.py [--config config/races.json] [--days 21]

Data: "Poll data from the New York Times" via PollResults.org (CC BY 4.0). Not affiliated with the NYT.
Raw responses are saved to data/polls_raw/<id>.json so the parser can be checked against the real format.
Never fails the workflow: on any problem it leaves the previous poll_inputs_auto.csv in place.
Averaging rule: last N days, each pollster's latest poll, weight sqrt(sample), two-party margin (D-R)/(D+R).
Pollster grades are applied from data/pollster_grades.csv (pollster,grade) when that file exists.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, json, math, os, re, sys, time
import requests

BASE = "https://api.pollresults.org/v1.0/politics/results"
GOOD = {"A+", "A", "A-", "A/B", "B+"}
OK2 = {"B", "B-"}


def get_all(kind, state):
    out, cursor = [], None
    for _ in range(20):
        params = {"state": state, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{BASE}/{kind}", params=params, timeout=30, headers={"User-Agent": "election-needle (personal, non-commercial)"})
        r.raise_for_status()
        j = r.json()
        rows = j if isinstance(j, list) else next((v for v in j.values() if isinstance(v, list)), [])
        out += rows
        cursor = (j.get("next_cursor") or j.get("cursor") or j.get("next")) if isinstance(j, dict) else None
        if not cursor or not rows:
            break
        time.sleep(0.5)
    return out, j


def _find(d, *needles):
    for k, v in d.items():
        kl = k.lower()
        if all(n in kl for n in needles):
            return v
    return None


def _date(x):
    """'10/16/26' or '2026-10-16' -> '2026-10-16'."""
    x = str(x or "").strip()
    for f in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(x[:10] if f == "%Y-%m-%d" else x.split()[0], f).date().isoformat()
        except Exception:
            pass
    return ""


def _last(name):
    return re.sub(r"[^a-z]", "", str(name).lower().replace("jr.", "").split()[-1] if str(name).strip() else "")


def parse_poll(p, cand=None):
    """PollResults.org poll -> dict(pollster,end,n,d,r) or None.
    Schema (seen in data/polls_raw): poll{pollster,endDate 'M/D/YY',partisan,internal,hypothetical,questions[]}, each
    question{sampleSize,population,stage,answers[{party,pct,candidateName}]}.
    cand = {'dem': surname, 'rep': surname} from config/candidates.csv (needed for independents such as Osborn, who are
    listed as IND). Skips partisan/internal/hypothetical polls and primaries. Picks the question with the largest Dem+Rep
    share (the head-to-head / final ranked-choice round), preferring likely voters."""
    if str(p.get("partisan") or "").strip() or str(p.get("internal") or "").strip() or str(p.get("hypothetical") or "").strip():
        return None
    end = _date(p.get("endDate"))
    if not end:
        return None
    best = None
    for q in p.get("questions") or []:
        if str(q.get("stage") or "general").lower() != "general" or str(q.get("subpopulation") or "").strip():
            continue
        d = r = None
        for a in q.get("answers") or []:
            name, party, pct = str(a.get("candidateName") or a.get("answer") or ""), str(a.get("party") or "").upper(), a.get("pct")
            if pct is None or "generic" in name.lower() or "generic" in str(a.get("answer") or "").lower():
                continue
            ln = _last(name)
            if cand and ln == cand["dem"]:
                d = max(d or 0, float(pct))
            elif cand and ln == cand["rep"]:
                r = max(r or 0, float(pct))
            elif not cand or (ln not in (cand["dem"], cand["rep"])):
                pass
        if cand is None or d is None or r is None:         # fall back to party codes (largest candidate per party)
            if cand is not None and (d is None) != (r is None):
                continue                                    # one of our two candidates is missing: wrong matchup
            if d is None:
                ds = [float(a["pct"]) for a in q.get("answers") or [] if str(a.get("party")).upper().startswith("D") and a.get("pct") is not None and "generic" not in str(a.get("candidateName")).lower()]
                rs = [float(a["pct"]) for a in q.get("answers") or [] if str(a.get("party")).upper().startswith("R") and a.get("pct") is not None and "generic" not in str(a.get("candidateName")).lower()]
                if not ds or not rs:
                    continue
                d, r = max(ds), max(rs)
        pop = str(q.get("population") or "").lower()
        key = (d + r, pop in ("lv", "v"), pop == "rv", float(q.get("sampleSize") or 0))
        if best is None or key > best[0]:
            best = (key, d, r, float(q.get("sampleSize") or 600))
    if not best:
        return None
    pollster = p.get("pollsterRatingName") or p.get("displayName") or p.get("pollster")
    return dict(pollster=str(pollster), end=end, n=best[3], d=best[1], r=best[2])


def _norm(s):
    s = re.sub(r"\b(the|inc|llc|corp|company|research|polling|poll|group|university|college|of)\b", " ", str(s).lower())
    return re.sub(r"[^a-z0-9]", "", s)


ALIASES = {   # short names seen on Bluesky -> the name in Silver Bulletin's ratings (keys are _norm() of the short name)
    "stanselm": "Saint Anselm College", "unf": "University of North Florida", "uh": "University of Houston",
    "aarp": "Fabrizio Lee & Associates/Impact Research", "impact": "Fabrizio Lee & Associates/Impact Research",
    "gsg": "Global Strategy Group", "beaconshaw": "Beacon Research/Shaw & Co. Research", "shawbeacon": "Beacon Research/Shaw & Co. Research", "ajc": "University of Georgia", "uga": "University of Georgia",
    "scharpoll": "The Washington Post/George Mason University Schar School of Policy and Government",
    "utt": "University of Texas at Tyler", "ut tyler": "University of Texas at Tyler", "fau": "Florida Atlantic University",
}


def _match(name, grades, _cache={}):
    """-> (canonical normalised key, Silver Bulletin grade or None). Exact normalised match first, then containment either
    way ('Emerson' / 'Emerson College', 'NYT/Siena' / 'The New York Times/Siena College'); the worst grade wins if ambiguous."""
    k = _norm(name)
    if k in {_norm(x) for x in ALIASES}:
        k = _norm(ALIASES[next(x for x in ALIASES if _norm(x) == k)])
    if not grades:
        return k, None
    if _cache.get("src") is not grades:
        _cache["n"] = {_norm(x): v for x, v in grades.items()}; _cache["src"] = grades
    n = _cache["n"]
    if k in n:
        return k, n[k]
    if len(k) >= 5:
        hits = [(kk, v) for kk, v in n.items() if len(kk) >= 5 and (k in kk or kk in k)]
        if hits:
            order = ["A+", "A", "A-", "A/B", "B+", "B", "B-", "B/C", "C+", "C", "C/D", "D+", "F"]
            kk, v = sorted(hits, key=lambda h: order.index(h[1]) if h[1] in order else 99)[-1]
            return kk, v
    return k, None


def grade_for(name, grades):
    return _match(name, grades)[1]


def average(polls, days, grades, _retry=True):
    cut = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    allp = polls
    polls = [p for p in polls if p["end"] >= cut]
    latest = {}
    for p in sorted(polls, key=lambda x: x["end"]):
        latest[_match(p["pollster"], grades)[0]] = p       # same firm under different names counts once
    use = list(latest.values())
    rule = "unrated"
    if grades:
        t1 = [p for p in use if grade_for(p["pollster"], grades) in GOOD]
        t2 = [p for p in use if grade_for(p["pollster"], grades) in OK2]
        if len(t1) >= 2: use, rule = t1, "tier1"
        elif t1 or t2: use, rule = t1 + t2, "tier1+2"
        else: use, rule = [], "none"
    if not use or (len(use) < 2 and _retry):                 # sparse race: widen the window once, to 35 days, and say so
        wide = average(allp, max(days, 35), grades, _retry=False) if days < 35 else None
        if wide and wide["n_polls"] > len(use):
            wide["rule_used"] += f",{max(days, 35)}d"
            return wide
    if not use:
        return None
    w = [math.sqrt(p["n"]) for p in use]
    m = sum(wi * (p["d"] - p["r"]) / (p["d"] + p["r"]) * 100 for wi, p in zip(w, use)) / sum(w)
    return dict(poll_margin=round(m, 2), n_polls=len(use), rule_used=rule, pollsters=";".join(p["pollster"] for p in use),
                window_start=cut, window_end=dt.date.today().isoformat())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/races.json")
    ap.add_argument("--out", default="data/poll_inputs_auto.csv")
    ap.add_argument("--days", type=int, default=21)
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    grades = {}
    if os.path.exists("data/pollster_grades.csv"):
        import pandas as pd
        g = pd.read_csv("data/pollster_grades.csv")
        grades = {str(x): str(y) for x, y in zip(g["pollster"], g["grade"])}
    os.makedirs("data/polls_raw", exist_ok=True)
    bsky = {}
    try:                                   # Bluesky poll posts (usapolling.bsky.social); optional extra source
        from bsky_polls import run as bsky_run
        for p in bsky_run():
            bsky.setdefault(p["id"], []).append(dict(pollster=p["pollster"], end=p["end"], n=p["n"], d=p["d"], r=p["r"]))
    except Exception as ex:
        print("bluesky source skipped:", ex)
    cmap = {}
    try:
        import pandas as pd
        for _, c in pd.read_csv('config/candidates.csv').iterrows():
            cmap[c['id']] = dict(dem=_last(c['dem']), rep=_last(c['rep']))
    except Exception as ex:
        print('candidates.csv not read:', ex)
    rows, parsed_any, ungraded = [], False, set()
    for r in cfg["races"]:
        kind = "senate" if "senate" in r["id"] else "governor"
        try:
            polls = []
            try:
                raw, _ = get_all(kind, r["state"])
                json.dump(raw, open(f"data/polls_raw/{r['id']}.json", "w"))
                polls = [x for x in (parse_poll(p, cmap.get(r['id'])) for p in raw) if x]
            except Exception as ex:
                print(f"{r['id']}: PollResults failed ({ex})")
            seen = {(re.sub(r"\W.*", "", p["pollster"].lower()), p["end"]) for p in polls}
            seen2 = {(p["end"], round(p["d"]), round(p["r"])) for p in polls}      # same numbers on the same day = same poll
            extra = [b for b in bsky.get(r["id"], []) if (re.sub(r"\W.*", "", b["pollster"].lower()), b["end"]) not in seen
                     and (b["end"], round(b["d"]), round(b["r"])) not in seen2]
            polls += extra
            parsed_any |= bool(polls)
            avg = average(polls, a.days, grades)
            ungraded |= {p['pollster'] for p in polls if grades and grade_for(p['pollster'], grades) is None}
            print(f"{r['id']}: {len(polls)} polls ({len(extra)} from Bluesky) ->", avg and avg["poll_margin"])
            if avg:
                rows.append(dict(id=r["id"], **avg))
        except Exception as ex:
            print(f"{r['id']}: failed ({ex})")
    if grades and ungraded:
        print("UNGRADED pollsters (excluded from averages; add to data/pollster_grades.csv if wrong):", "; ".join(sorted(ungraded)))
    if parsed_any and rows:
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "poll_margin", "n_polls", "rule_used", "pollsters", "window_start", "window_end"])
            w.writeheader(); w.writerows(rows)
        print(f"wrote {a.out}")
    else:
        print("nothing parsed; kept previous file (check data/polls_raw)")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print("fetch_polls failed:", ex)
        sys.exit(0)
