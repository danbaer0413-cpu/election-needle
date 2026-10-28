"""Round 2: civicAPI early-vote endpoints found in round 1 are /api/v2/early-vote/{country}/{state}, .../capabilities, /US/{x}.
Tries them for our gap states and saves the JSON (trimmed) to data/civic_probe.json. Read-only."""
import json, requests

BASE = "https://civicapi.org/api/v2"
H = {"User-Agent": "election-needle-probe/1.0 (personal project; attribution: civicapi.org)"}
out = {"tries": [], "found": []}


def get(p):
    u = BASE + p
    try:
        r = requests.get(u, headers=H, timeout=25)
        ct = r.headers.get("content-type", "")
        ok = r.status_code == 200 and "json" in ct.lower()
        body = r.text
    except Exception as ex:
        r, ok, body = None, False, str(ex)[:200]
    out["tries"].append({"path": p, "status": getattr(r, "status_code", 0), "json": ok, "bytes": len(body), "head": body[:2500] if ok else body[:200]})
    print(("OK  " if ok else "no  "), getattr(r, "status_code", 0), len(body), p)
    if ok:
        out["found"].append(p)
        print("     ", body[:400].replace("\n", " "))
    return body if ok else None


paths = ["/early-vote/US/capabilities", "/early-vote/US/2026", "/early-vote/US/ME", "/early-vote/US/me", "/early-vote/US/Maine"]
for st in ("NE", "WI", "IA", "KS", "NH", "MS", "SC", "AK", "MN", "NV", "MI", "OH"):
    paths.append(f"/early-vote/US/{st}")
paths += ["/early-vote/US/ME/demographics", "/early-vote/historical/US/ME/2022", "/race", "/race/search", "/getElectionYears", "/getElectionDates?country=US&year=2026"]
for p in paths:
    get(p)
json.dump(out, open("data/civic_probe.json", "w"), indent=1)
print("JSON endpoints found:", out["found"] or "none")
