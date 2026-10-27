"""Nebraska step 3: race names + ids on the results page, the BuildCounty(...) calls, and what GetMapData returns for each race. Read-only. Saves data/portal_ne3.txt."""
import re, json
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
B = "https://electionresults.nebraska.gov"
S = "https://neresultswebservice.azurewebsites.us/ResultsAjax.svc/"
out = []
t = requests.get(B + "/resultsSW.aspx?type=SW&map=CTY", headers={"User-Agent": UA}, timeout=40).text
out.append(f"page {len(t):,} chars")
for m in list(re.finditer(r"BuildCounty\w*\(", t))[:8]:
    out.append("  [call] " + re.sub(r"\s+", " ", t[max(0, m.start() - 80): m.end() + 120]))
races = re.findall(r'raceid="(\d+)"\s+party="([^"]*)"\s+officeseqno="(\d+)"', t)
out.append(f"race buttons: {len(races)}  {sorted(set(races))[:40]}")
for m in list(re.finditer(r'class="[^"]*(?:race|office)[^"]*"[^>]*>\s*([^<]{3,80})<', t))[:40]:
    out.append("  [title] " + m.group(1).strip())
for rid, party, osn in sorted(set(races))[:6]:
    for typ in ("SW", "S", "CTY"):
        try:
            r = requests.get(f"{S}GetMapData?type={typ}&category=CTY&raceID={rid}&osn={osn}&county=0&party=0", headers={"User-Agent": UA}, timeout=40)
            out.append(f"\n== race {rid} osn {osn} type={typ}: HTTP {r.status_code}, {len(r.text):,} chars\n   {r.text[:700]}")
        except Exception as ex:
            out.append(f"\n== race {rid} type={typ}: failed {str(ex)[:120]}")
try:
    r = requests.get(S + "GetCandidates?ElectionType=General&ElectionID=0", headers={"User-Agent": UA}, timeout=40)
    out.append(f"\n== GetCandidates: HTTP {r.status_code}, {len(r.text):,} chars\n   {r.text[:1500]}")
except Exception as ex:
    out.append(f"\n== GetCandidates failed {str(ex)[:120]}")
txt = "\n".join(out)
open("data/portal_ne3.txt", "w", encoding="utf-8").write(txt)
print(txt)
