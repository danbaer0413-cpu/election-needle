"""Round 4: find civicAPI's Nov 3 2026 statewide races for our states (U.S. Senate, Governor) and see what their detail looks like.
Read-only. Prints race ids, whether county breakdowns exist, and saves data/civic_probe.json."""
import json, requests

BASE = "https://civicapi.org/api/v2"
H = {"User-Agent": "election-needle-probe/1.0 (personal project; attribution: civicapi.org)"}
STATES = ["AK", "FL", "GA", "IA", "KS", "ME", "MI", "MN", "MS", "NE", "NH", "NV", "OH", "SC", "TX", "WI", "NC"]


def get(p):
    try:
        r = requests.get(BASE + p, headers=H, timeout=40)
        return r.status_code, (r.json() if "json" in r.headers.get("content-type", "") else None)
    except Exception as ex:
        return 0, None


out = {"types": {}, "races": {}, "detail": {}}
for st in STATES:
    found, off = [], 0
    while off < 400:
        code, js = get(f"/race/search?country=US&province={st}&date=2026-11-03&offset={off}")
        if not js or not js.get("races"):
            break
        for r in js["races"]:
            out["types"][r.get("type")] = out["types"].get(r.get("type"), 0) + 1
            nm = (r.get("election_name") or "")
            if r.get("election_type") == "Statewide" and "State Senate" not in nm and "State House" not in nm and any(
                    w in nm for w in ("Senate", "Governor")):
                found.append({"id": r["id"], "name": nm, "type": r.get("type"), "scope": r.get("election_type"), "has_breakdown": r.get("has_breakdown"),
                              "pct": r.get("percent_reporting"), "cands": [(c.get("name"), c.get("party")) for c in r.get("candidates", [])][:6]})
        off += js.get("limit", 20)
        if off >= (js.get("count") or 0):
            break
    out["races"][st] = found
    print(st, "statewide Senate/Governor races:", [(f["id"], f["name"]) for f in found] or "none found")
first = [f for st in STATES for f in out["races"][st]][:3]
for f in first:
    for suffix in ("?data=json", "?data=json&precinct"):
        code, js = get(f"/race/{f['id']}{suffix}")
        keys = list(js.keys()) if isinstance(js, dict) else None
        reg = js.get("regions") if isinstance(js, dict) else None
        info = {"status": code, "keys": keys, "n_regions": len(reg) if reg else 0,
                "sample_region": (list(reg.items())[:1] if isinstance(reg, dict) else (reg[:1] if reg else None)), "candidates": (js or {}).get("candidates", [])[:3]}
        out["detail"][f"{f['id']}{suffix}"] = info
        print(f["id"], f["name"], suffix, "status", code, "regions:", info["n_regions"])
print("types seen:", out["types"])
json.dump(out, open("data/civic_probe.json", "w"), indent=1, default=str)
