"""Nebraska step 2: how the page fills in electionType, eid, type, raceID, osn, party; then try the data service. Read-only. Saves data/portal_ne2.txt."""
import re
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
B = "https://electionresults.nebraska.gov"
S = "https://neresultswebservice.azurewebsites.us/"
out = []


def get(u, **kw):
    return requests.get(u, headers={"User-Agent": UA}, timeout=40, **kw)


for p in ["/Default.aspx", "/resultsSW.aspx?type=SW&map=CTY", "/Scripts/BuildCounties.js", "/maps/static/js/BuildCountyMap.js"]:
    try:
        t = get(B + p).text
    except Exception as ex:
        out.append(f"{p}: failed {ex}")
        continue
    out.append(f"\n===== {p} ({len(t):,} chars)")
    seen = 0
    for kw in ("electionType", "ElectionType", "eid", "electionID", "raceID", "osn", "var type", "party ="):
        for m in list(re.finditer(kw, t))[:4]:
            ctx = re.sub(r"\s+", " ", t[max(0, m.start() - 120): m.end() + 220])
            out.append(f"  [{kw}] ...{ctx}")
for ep in ["GetCandidates?ElectionType=GEN&ElectionID=", "GetCandidates?ElectionType=General&ElectionID=", "GetCandidates?ElectionType=&ElectionID=",
           "GetMapData?type=SW&category=CTY&raceID=0&osn=0&county=0&party=", "help", "GetElections", "GetElectionList"]:
    try:
        r = get(S + "ResultsAjax.svc/" + ep)
        out.append(f"\n== {ep}: HTTP {r.status_code}, {len(r.text):,} chars\n   {re.sub(chr(10), ' ', r.text[:900])}")
    except Exception as ex:
        out.append(f"\n== {ep}: failed {str(ex)[:150]}")
txt = "\n".join(out)
open("data/portal_ne2.txt", "w", encoding="utf-8").write(txt)
print(txt)
