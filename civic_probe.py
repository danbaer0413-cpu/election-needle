"""Round 5: (a) find U.S. Senate races (round 4 found governors only), (b) look at a COMPLETED 2022 governor race to see the county/results format.
Read-only. Saves data/civic_probe.json."""
import json, requests

BASE = "https://civicapi.org/api/v2"
H = {"User-Agent": "election-needle-probe/1.0 (personal project; attribution: civicapi.org)"}


def get(p):
    try:
        r = requests.get(BASE + p, headers=H, timeout=40)
        return r.status_code, (r.json() if "json" in r.headers.get("content-type", "") else None)
    except Exception as ex:
        return 0, None


out = {"senate": [], "detail": {}}
tries = ["country=US&type=Senate&date=2026-11-03", "country=US&type=U.S.%20Senate&date=2026-11-03", "country=US&province=US&date=2026-11-03",
         "country=US&type=United%20States%20Senate&date=2026-11-03", "country=US&search=Senate&date=2026-11-03", "search=Collins&date=2026-11-03",
         "country=US&province=GA&search=Ossoff", "country=US&province=GA&search=Senate&date=2026-11-03", "country=US&province=GA&date=2026-11-03&election_type=Federal"]
seen = {}
for q in tries:
    for off in (0, 20, 40):
        code, js = get(f"/race/search?{q}&offset={off}")
        if not js or not js.get("races"):
            print("no ", code, q, off)
            break
        for r in js["races"]:
            nm = r.get("election_name") or ""
            if "Senate" in nm and "State Senate" not in nm:
                seen[r["id"]] = {"id": r["id"], "name": nm, "type": r.get("type"), "province": r.get("province"), "scope": r.get("election_type"),
                                 "has_breakdown": r.get("has_breakdown"), "date": r.get("election_date")}
        print("ok ", code, q, off, "count", js.get("count"), "senate seen so far", len(seen))
out["senate"] = list(seen.values())
for s in out["senate"][:60]:
    print("SENATE", s["id"], s["name"], s["province"], s["type"], s["scope"], s["date"])

# completed race for format: Georgia governor 2022
code, js = get("/race/search?country=US&province=GA&date=2022-11-08&offset=0")
cands = [r for r in (js or {}).get("races", []) if r.get("election_name") == "Georgia Governor"]
print("GA 2022 governor search:", [(r["id"], r["election_name"], r.get("has_breakdown")) for r in cands])
for r in cands[:1]:
    for suffix in ("?data=json", "?data=json&precinct"):
        code, d = get(f"/race/{r['id']}{suffix}")
        reg = (d or {}).get("regions")
        out["detail"][suffix] = {"status": code, "keys": list((d or {}).keys()), "pct": (d or {}).get("percent_reporting"), "n_regions": len(reg) if reg else 0,
                                 "sample": (list(reg.items())[:2] if isinstance(reg, dict) else (reg[:2] if reg else None)), "candidates": (d or {}).get("candidates", [])[:3]}
        print("2022 GA gov", suffix, code, "keys", out["detail"][suffix]["keys"], "regions", out["detail"][suffix]["n_regions"])
        print("   sample:", json.dumps(out["detail"][suffix]["sample"], default=str)[:600])
    code, h = get(f"/race/{r['id']}/history")
    out["detail"]["history"] = {"status": code, "head": json.dumps(h, default=str)[:800]}
    print("history", code, json.dumps(h, default=str)[:400])
json.dump(out, open("data/civic_probe.json", "w"), indent=1, default=str)
