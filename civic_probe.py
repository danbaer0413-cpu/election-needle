"""Election-day readiness probe (run on/after Nov 2-3, 2026).  Read-only.
For every state we cover it looks up the Nov 3 2026 races civicAPI has filed and reports, per race type
(U.S. Senate, Governor, U.S. House), how many exist, whether any are flagged test_data, whether they report percent_reporting / votes,
and whether county-level `region_results` are present.  Also pulls one House district in detail.
Saves data/civic_probe.json and prints a summary."""
import json, requests

BASE = "https://civicapi.org/api/v2"
H = {"User-Agent": "election-needle-probe/1.0 (personal project; attribution: civicapi.org)"}
STATES = ["AK", "FL", "GA", "IA", "KS", "ME", "MI", "MN", "MS", "NE", "NH", "NV", "OH", "SC", "TX", "WI", "NC"]


def get(p):
    try:
        r = requests.get(BASE + p, headers=H, timeout=40)
        return r.status_code, (r.json() if "json" in r.headers.get("content-type", "") else None)
    except Exception:
        return 0, None


def kind(name):
    n = str(name)
    if "Primary" in n:
        return None
    if "Senate" in n and "State Senate" not in n:
        return "senate"
    if "Governor" in n and not any(w in n for w in ("Lieutenant", "Board", "College", "University")):
        return "governor"
    if ("U.S. House" in n or "US House" in n or "Congressional" in n or "United States House" in n) and "State" not in n:
        return "house"
    return None


out = {"version": 2, "states": {}, "detail": {}}
for st in STATES:
    found, off, seen_ids = [], 0, set()
    while off < 20000:
        # startDate/endDate are the API's date filters (`date=` is ignored and returns every year); limit up to 50000
        code, js = get(f"/race/search?country=US&province={st}&startDate=2026-11-03&endDate=2026-11-03&limit=1000&offset={off}")
        races = (js or {}).get("races") or []
        for r in races:
            k = kind(r.get("election_name"))
            if k and r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                found.append((k, r["id"], r.get("election_name")))
        if len(races) < 1000:
            break
        off += 1000
    cnt = {k: sum(1 for f in found if f[0] == k) for k in ("senate", "governor", "house")}
    out["states"][st] = {"counts": cnt, "races": found}
    print(st, cnt)

# detail on one race of each kind (first found anywhere), then one House race in a covered state
seen = set()
for st in STATES:
    for k, rid, nm in out["states"][st]["races"]:
        if k in seen:
            continue
        seen.add(k)
        code, d = get(f"/race/{rid}?data=json")
        d = d or {}
        rr = d.get("region_results")
        info = {"id": rid, "name": nm, "state": st, "status": code, "test_data": d.get("test_data"), "pct": d.get("percent_reporting"),
                "called_at": d.get("called_at"), "candidates": [(c.get("name"), c.get("party"), c.get("votes")) for c in (d.get("candidates") or [])[:4]],
                "n_regions": len(rr) if rr else 0, "region_sample": (list(rr.items())[:2] if isinstance(rr, dict) else (rr or [])[:2]),
                "region_names": [(v.get("name"), v.get("type")) for v in (rr.values() if isinstance(rr, dict) else rr or []) if isinstance(v, dict)]}
        out["detail"][k] = info
        print(f"{k.upper()} sample {nm} ({st}) id {rid}: test_data={info['test_data']} pct={info['pct']} regions={info['n_regions']} candidates={info['candidates']}")
        code, h = get(f"/race/{rid}/history")
        print("   history", code, json.dumps(h, default=str)[:200])
json.dump(out, open("data/civic_probe.json", "w"), indent=1, default=str)
print("saved data/civic_probe.json")
