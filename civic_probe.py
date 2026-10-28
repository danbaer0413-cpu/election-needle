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
    if "Governor" in n and "Lieutenant" not in n:
        return "governor"
    if ("U.S. House" in n or "US House" in n or "Congressional" in n or "United States House" in n) and "State" not in n:
        return "house"
    return None


out = {"states": {}, "detail": {}}
for st in STATES:
    found, off = [], 0
    while off < 400:
        code, js = get(f"/race/search?country=US&province={st}&date=2026-11-03&offset={off}")
        if not js or not js.get("races"):
            break
        for r in js["races"]:
            k = kind(r.get("election_name"))
            if k:
                found.append((k, r["id"], r.get("election_name")))
        off += 20
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
                "n_regions": len(rr) if rr else 0, "region_sample": (list(rr.items())[:1] if isinstance(rr, dict) else (rr or [])[:1])}
        out["detail"][k] = info
        print(f"{k.upper()} sample {nm} ({st}) id {rid}: test_data={info['test_data']} pct={info['pct']} regions={info['n_regions']} candidates={info['candidates']}")
        code, h = get(f"/race/{rid}/history")
        print("   history", code, json.dumps(h, default=str)[:200])
json.dump(out, open("data/civic_probe.json", "w"), indent=1, default=str)
print("saved data/civic_probe.json")
