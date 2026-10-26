"""
Second-stage probe: look INSIDE the pages we found data hints for, and sample the endpoints themselves.
Run on GitHub: Actions -> probe-deep -> Run workflow. Saves data/portal_deep.txt (send it to me).

For each site it (1) reads the page's JavaScript files and prints every place that mentions a data URL pattern (cdn/results,
/api/..., .json, export, detail.xml, .csv, .xlsx) with surrounding text, so the URL templates are visible, and
(2) downloads the known endpoints below and prints the status, size, and the first part of the content (JSON: its structure).
Read-only requests to public pages.
"""
import json
import re
import sys
from urllib.parse import urljoin, urlparse
import requests
from probe_portals import BROWSER, UA, get

SITES = {
    "GA": "https://results.sos.ga.gov/results/public/Georgia", "TX": "https://results.texas-election.com/",
    "NE": "https://electionresults.nebraska.gov/", "NV": "https://silverstateelection.nv.gov/",
    "FL": "https://floridaelectionwatch.gov/", "OH": "https://liveresults.ohiosos.gov/",
    "MI": "https://mvic.sos.state.mi.us/", "KS": "https://ent.sos.ks.gov/kssos_ent.html",
    "IA": "https://electionresults.iowa.gov/", "SC": "https://www.enr-scvotes.org/SC/",
    "NH": "https://www.sos.nh.gov/elections", "AK": "https://www.elections.alaska.gov/results/",
}
ENDPOINTS = [
    "https://results.texas-election.com/Version.json", "https://results.texas-election.com/Race.json",
    "https://results.texas-election.com/County.json", "https://results.texas-election.com/OfficeSummary.json",
    "https://results.texas-election.com/Home.json", "https://results.texas-election.com/Lookups.json",
    "https://results.sos.ga.gov/results/public/api", "https://results.sos.ga.gov/cdn/results/",
    "https://liveresults.ohiosos.gov/Api/v1/Contest/getContestList", "https://liveresults.ohiosos.gov/Api/v1/Contest/getCountyList",
    "https://liveresults.ohiosos.gov/Api/v1/Contest/getTabs", "https://liveresults.ohiosos.gov/Api/v1/Contest/getStatistics",
    "https://liveresults.ohiosos.gov/Api/v1/Contest/GetElectionSummaryCsv",
    "https://floridaelectionwatch.gov/CountyReportingStatus", "https://floridaelectionwatch.gov/TrackCounty/ALA",
    "https://electionresults.sos.mn.gov/Results/Index?ersElectionId=200&scenario=Governor&officeInElectionId=38695",
    "https://electionresults.sos.mn.gov/Results/CountyStatisticsStatewide/Index?ersElectionId=200",
]
PAT = re.compile(r"(cdn/results[^\"'\s)]*|/api/[A-Za-z0-9_/.\-]+|[A-Za-z0-9_/.\-]+\.(?:json|csv|xlsx|xml|zip)\b|export[A-Za-z0-9_\-]*|detail\.xml|summary\.json)", re.I)
JUNK = re.compile(r"manifest|browserconfig|package|sourcemap|\.min\.js|jquery|bootstrap|fonts|svg|png", re.I)


def shape(x, depth=0):
    if isinstance(x, dict):
        return {k: (shape(v, depth + 1) if depth < 2 else type(v).__name__) for k, v in list(x.items())[:14]}
    if isinstance(x, list):
        return [shape(x[0], depth + 1) if x else "empty", f"... {len(x)} items"]
    return type(x).__name__ if depth else x


def mine_js(name, url, out):
    try:
        code, ct, final, html = get(url)
    except Exception as ex:
        out.append(f"== {name}: {url}\n  FAILED {type(ex).__name__}: {str(ex)[:120]}"); return
    out.append(f"== {name}: {final} (status {code}, {len(html):,} chars)")
    scripts = [urljoin(final, s) for s in re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, re.I)]
    scripts = [s for s in scripts if urlparse(s).netloc == urlparse(final).netloc and not JUNK.search(s)][:15]
    seen = set()
    for src in [final] + scripts:
        try:
            c2, t2, f2, body = (code, ct, final, html) if src == final else get(src, cap=6_000_000)
        except Exception:
            continue
        for m in PAT.finditer(body):
            tok = m.group(1)
            if tok in seen or JUNK.search(tok) or len(tok) < 6:
                continue
            seen.add(tok)
            a, b = max(0, m.start() - 70), min(len(body), m.end() + 70)
            out.append(f"  [{urlparse(src).path.split('/')[-1] or 'page'}] ...{body[a:b].replace(chr(10), ' ')}...")
            if len(seen) >= 45:
                break
        if len(seen) >= 45:
            break
    if not seen:
        out.append("  no data URL patterns found")


def sample(url, out):
    try:
        r = requests.get(url, headers=BROWSER, timeout=30)
    except Exception as ex:
        out.append(f"-- {url}\n  FAILED {type(ex).__name__}: {str(ex)[:120]}"); return
    ct = r.headers.get("content-type", "").split(";")[0]
    out.append(f"-- {url}\n  status {r.status_code} | {ct} | {len(r.content):,} bytes")
    if r.status_code >= 400:
        return
    try:
        out.append("  JSON shape: " + json.dumps(shape(r.json()))[:1500])
    except Exception:
        out.append("  start: " + re.sub(r"\s+", " ", r.text[:700]))


def main():
    out = []
    for n, u in SITES.items():
        mine_js(n, u, out)
    out.append("\n######## ENDPOINT SAMPLES ########")
    for u in ENDPOINTS:
        sample(u, out)
    txt = "\n".join(out) + "\n"
    open("data/portal_deep.txt", "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
