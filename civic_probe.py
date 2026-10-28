"""Round 3. Round 2 showed /early-vote/{STATE}/capabilities works with STATE="US", and the error lists categories requested/returned/inperson/grace,
so the real shape is probably /early-vote/{STATE}/{category}. Also probes race search for election-night results. Read-only; saves data/civic_probe.json."""
import json, re, requests

BASE = "https://civicapi.org/api/v2"
H = {"User-Agent": "election-needle-probe/1.0 (personal project; attribution: civicapi.org)"}
out = {"tries": [], "found": []}


def get(p, show=500):
    u = BASE + p
    try:
        r = requests.get(u, headers=H, timeout=30)
        ct = r.headers.get("content-type", "")
        ok = r.status_code == 200 and "json" in ct.lower()
        body = r.text
        code = r.status_code
    except Exception as ex:
        ok, body, code = False, str(ex)[:200], 0
    out["tries"].append({"path": p, "status": code, "json": ok, "bytes": len(body), "head": body[:3000] if ok else body[:200]})
    print(("OK  " if ok else "no  "), code, len(body), p)
    if ok:
        out["found"].append(p)
        print("     ", body[:show].replace("\n", " "))
    return body if ok else None


for p in ["/early-vote/US/returned", "/early-vote/US/inperson", "/early-vote/ME/capabilities", "/early-vote/ME/returned", "/early-vote/ME/requested",
          "/early-vote/ME/inperson", "/early-vote/ME/grace", "/early-vote/ME/returned/demographics", "/early-vote/ME/demographics?category=returned"]:
    get(p, 900)
for st in ("NE", "WI", "IA", "KS", "NH", "MS", "SC", "AK", "MN", "NV", "MI", "OH", "FL", "GA", "NC", "TX"):
    for cat in ("returned", "inperson"):
        get(f"/early-vote/{st}/{cat}", 250)

# election-night results: find 2026 general races
for p in ["/race/search?country=US&province=Maine&election_date=2026-11-03",
          "/race/search?country=US&province=ME&date=2026-11-03",
          "/race/search?country=US&province=Maine&year=2026&type=senate",
          "/race/search?search=Maine%20Senate%202026",
          "/race/search?query=Susan%20Collins",
          "/race/search?country=US&province=Maine&election_type=general",
          "/getElectionDates?country=US&year=2026&month=11"]:
    get(p, 1200)
ids = set()
for t in out["tries"]:
    if t["json"] and "race/search" in t["path"]:
        ids |= set(re.findall(r'"(?:raceId|race_id|id)"\s*:\s*"?(\d{4,8})', t["head"]))
print("race ids seen:", sorted(ids)[:10])
for i in sorted(ids)[:2]:
    get(f"/race/{i}?data=json", 1500)
    get(f"/race/{i}?data=json&precinct", 800)
json.dump(out, open("data/civic_probe.json", "w"), indent=1)
print("JSON endpoints found:", len(out["found"]))
