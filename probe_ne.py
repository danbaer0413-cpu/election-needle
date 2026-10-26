"""Nebraska: list every data-service call the results pages make (ResultsAjax.svc/<Method>?...). Read-only. Saves data/portal_ne.txt."""
import re
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
B = "https://electionresults.nebraska.gov"
PAGES = ["/resultsSW.aspx?type=SW&map=CTY", "/Default.aspx", "/Scripts/utils.js", "/Scripts/BuildCounties.js", "/Scripts/BuildPrecincts.js",
         "/maps/static/js/BuildCountyMap.js", "/maps/static/js/CreateMap.js", "/Scripts/CountyTurnoutChart.js", "/Scripts/HeaderTurnoutChart.js", "/ResultsMedia.aspx"]
out = []
for p in PAGES:
    try:
        t = requests.get(B + p, headers={"User-Agent": UA}, timeout=40).text
    except Exception as ex:
        out.append(f"{p}: failed {ex}")
        continue
    hits = list(re.finditer(re.escape("ResultsAjax.svc/"), t))
    out.append(f"\n== {p}: {len(t):,} chars, {len(hits)} service calls")
    seen = set()
    for m in hits:
        ctx = re.sub(r"\s+", " ", t[max(0, m.start() - 60):m.end() + 200])
        key = re.search(r"ResultsAjax\.svc/(\w+)", t[m.start():m.start() + 80])
        k = key.group(1) if key else ctx
        if k not in seen:
            seen.add(k)
            out.append(f"   {k}: ...{ctx}")
    for kw in ("getValues", "ServiceRoot"):
        m = re.search(kw + r".{0,200}", t)
        if m and "ResultsAjax" not in m.group(0):
            out.append(f"   [{kw}] {re.sub(chr(10), ' ', m.group(0))[:240]}")
txt = "\n".join(out)
open("data/portal_ne.txt", "w").write(txt + "\n")
print(txt)
