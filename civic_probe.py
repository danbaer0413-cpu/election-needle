"""Round 6: (a) every Nov 3 2026 race name for GA, NC, ME (to see how the U.S. Senate races are filed),
(b) the structure of `region_results` on a COMPLETED statewide race (Arizona U.S. Senate 2024, id 29243) and on the 2026 Georgia governor race.
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


out = {"names": {}, "detail": {}}
for st in ("GA", "NC", "ME"):
    names, off = [], 0
    while off < 300:
        code, js = get(f"/race/search?country=US&province={st}&date=2026-11-03&offset={off}")
        if not js or not js.get("races"):
            break
        names += [(r["id"], r.get("election_name"), r.get("type"), r.get("election_type")) for r in js["races"]]
        off += 20
    out["names"][st] = names
    short = [n for n in names if "House" not in str(n[1]) and "Judge" not in str(n[1]) and "Court" not in str(n[1])]
    print(st, len(names), "races on 2026-11-03; non-local sample:", short[:25])

for label, rid in (("AZ Senate 2024", 29243), ("GA Governor 2026", 87088)):
    code, d = get(f"/race/{rid}?data=json")
    rr = (d or {}).get("region_results")
    info = {"status": code, "pct": (d or {}).get("percent_reporting"), "called_at": (d or {}).get("called_at"), "candidates": (d or {}).get("candidates", [])[:3],
            "region_results_type": type(rr).__name__, "n": len(rr) if rr else 0}
    if isinstance(rr, dict):
        info["sample"] = list(rr.items())[:2]
    elif isinstance(rr, list):
        info["sample"] = rr[:2]
    out["detail"][label] = info
    print(label, code, "pct", info["pct"], "region_results:", info["region_results_type"], info["n"])
    print("  candidates:", json.dumps(info["candidates"], default=str)[:500])
    print("  sample:", json.dumps(info.get("sample"), default=str)[:900])
code, h = get("/race/29243/history")
print("history AZ", code, json.dumps(h, default=str)[:300])
json.dump(out, open("data/civic_probe.json", "w"), indent=1, default=str)
