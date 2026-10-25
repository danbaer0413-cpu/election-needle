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


def parse_poll(p):
    """Best-effort: returns dict(pollster,end,n,d,r) or None. Adjust after checking data/polls_raw."""
    pollster = _find(p, "pollster") or _find(p, "source")
    if isinstance(pollster, dict):
        pollster = pollster.get("name") or pollster.get("title")
    end = _find(p, "end") or _find(p, "date")
    n = _find(p, "sample") or _find(p, "size")
    d = r = None
    cands = _find(p, "answer") or _find(p, "candidate") or _find(p, "result") or []
    if isinstance(cands, list):
        for c in cands:
            if not isinstance(c, dict):
                continue
            party = str(c.get("party") or c.get("party_code") or "").upper()[:3]
            pct = c.get("pct") or c.get("percent") or c.get("value")
            if pct is None:
                continue
            if party.startswith("D") and d is None:
                d = float(pct)
            elif party.startswith("R") and r is None:
                r = float(pct)
    if d is None: d = _find(p, "dem")
    if r is None: r = _find(p, "rep")
    try:
        return dict(pollster=str(pollster), end=str(end)[:10], n=float(n or 600), d=float(d), r=float(r))
    except Exception:
        return None


def _norm(s):
    s = re.sub(r"\b(the|inc|llc|corp|company|research|polling|poll|group|university|college|of)\b", " ", str(s).lower())
    return re.sub(r"[^a-z0-9]", "", s)


def grade_for(name, grades, _cache={}):
    """Silver Bulletin grade for a pollster name as it appears in the poll feed. Exact normalised match first, then
    containment either way (e.g. 'Emerson' / 'Emerson College', 'NYT/Siena' / 'The New York Times/Siena College')."""
    if not grades:
        return None
    if not _cache.get("n") or _cache.get("src") is not grades:
        _cache["n"] = {_norm(k): v for k, v in grades.items()}; _cache["src"] = grades
    n = _cache["n"]; k = _norm(name)
    if k in n:
        return n[k]
    if len(k) >= 5:
        hits = [v for kk, v in n.items() if len(kk) >= 5 and (k in kk or kk in k)]
        if hits:
            order = ["A+", "A", "A-", "A/B", "B+", "B", "B-", "B/C", "C+", "C", "C/D", "D+", "F"]
            return sorted(hits, key=lambda g: order.index(g) if g in order else 99)[-1]      # worst grade if ambiguous
    return None


def average(polls, days, grades):
    cut = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    polls = [p for p in polls if p["end"] >= cut]
    latest = {}
    for p in sorted(polls, key=lambda x: x["end"]):
        latest[p["pollster"]] = p
    use = list(latest.values())
    rule = "unrated"
    if grades:
        t1 = [p for p in use if grade_for(p["pollster"], grades) in GOOD]
        t2 = [p for p in use if grade_for(p["pollster"], grades) in OK2]
        if len(t1) >= 2: use, rule = t1, "tier1"
        elif t1 or t2: use, rule = t1 + t2, "tier1+2"
        else: use, rule = [], "none"
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
    rows, parsed_any = [], False
    for r in cfg["races"]:
        kind = "senate" if "senate" in r["id"] else "governor"
        try:
            polls = []
            try:
                raw, _ = get_all(kind, r["state"])
                json.dump(raw, open(f"data/polls_raw/{r['id']}.json", "w"))
                polls = [x for x in (parse_poll(p) for p in raw) if x]
            except Exception as ex:
                print(f"{r['id']}: PollResults failed ({ex})")
            seen = {(re.sub(r"\W.*", "", p["pollster"].lower()), p["end"]) for p in polls}
            extra = [b for b in bsky.get(r["id"], []) if (re.sub(r"\W.*", "", b["pollster"].lower()), b["end"]) not in seen]
            polls += extra
            parsed_any |= bool(polls)
            avg = average(polls, a.days, grades)
            print(f"{r['id']}: {len(polls)} polls ({len(extra)} from Bluesky) ->", avg and avg["poll_margin"])
            if avg:
                rows.append(dict(id=r["id"], **avg))
        except Exception as ex:
            print(f"{r['id']}: failed ({ex})")
    if grades:                              # pollsters we could not grade (excluded from the average): review and add aliases
        seen = {}
        for r in cfg["races"]:
            pass
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
