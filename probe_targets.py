"""
Third probe: the specific things we still need to read Ohio, Texas, Georgia, Florida and Nebraska.
Run on GitHub: Actions -> probe-targets -> Run workflow. Saves data/portal_targets.txt (send it to me). Read-only requests.
"""
import io
import json
import re
from urllib.parse import urljoin, urlparse
import pandas as pd
import requests
from probe_portals import BROWSER

OUT = []


def say(*a):
    OUT.append(" ".join(str(x) for x in a))


def fetch(url, **kw):
    try:
        return requests.get(url, headers=BROWSER, timeout=40, **kw)
    except requests.exceptions.SSLError:
        requests.packages.urllib3.disable_warnings()
        return requests.get(url, headers=BROWSER, timeout=40, verify=False, **kw)


def shape(x, depth=0):
    if isinstance(x, dict):
        return {k: (shape(v, depth + 1) if depth < 3 else type(v).__name__) for k, v in list(x.items())[:16]}
    if isinstance(x, list):
        return [shape(x[0], depth + 1) if x else "empty", f"... {len(x)} items"]
    return x if depth == 0 or isinstance(x, (int, float, bool)) or (isinstance(x, str) and len(x) < 40) else type(x).__name__


def js_bodies(page_url, limit=12):
    r = fetch(page_url)
    srcs = [urljoin(r.url, s) for s in re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", r.text, re.I)]
    srcs = [s for s in srcs if urlparse(s).netloc == urlparse(r.url).netloc][:limit]
    return [(s, fetch(s).text) for s in srcs]


def grep(bodies, patterns, width=260, per=12):
    for pat in patterns:
        n = 0
        for src, body in bodies:
            for m in re.finditer(pat, body):
                say(f"  [{src.rsplit('/', 1)[-1]}] /{pat[:30]}/ -> ...{body[max(0, m.start() - 40):m.end() + width].replace(chr(10), ' ')}")
                n += 1
                if n >= per:
                    break
            if n >= per:
                break
        if n == 0:
            say(f"  (no match for /{pat[:40]}/)")


def ohio():
    say("\n==== OHIO ====")
    base = "https://liveresults.ohiosos.gov/Api/v1/Contest/"
    lst = fetch(base + "getContestList").json()
    rows = [(g["displayName"], c["contestName"], c["contestObjectId"]) for g in lst for c in g.get("contestGroupings", [])]
    say(f"{len(rows)} contests; Senate/Governor ones:")
    hits = [r for r in rows if re.search(r"senate|governor", f"{r[0]} {r[1]}", re.I)]
    for r in hits[:12]:
        say("  ", r)
    if not hits:
        say("  first 15 contests:", rows[:15])
    pick = hits[0] if hits else (rows[0] if rows else None)
    if pick:
        for lvl in ("County", "county", "State", "Statewide"):
            r = fetch(base + "GetContestDetailsObject", params={"contestName": pick[1], "contestObjectId": pick[2], "resultsLevel": lvl, "countyId": ""})
            say(f"  GetContestDetailsObject resultsLevel={lvl!r}: status {r.status_code}, {len(r.content):,} bytes")
            try:
                say("    shape:", json.dumps(shape(r.json()))[:1800])
            except Exception:
                say("    start:", re.sub(r"\s+", " ", r.text[:300]))
            if r.status_code == 200 and len(r.content) > 500:
                break


def texas():
    say("\n==== TEXAS (Enhanced Voting) ====")
    grep(js_bodies("https://results.texas-election.com/"),
         [r"appJsonPath", r"getElectionVersionUrl\(\)\s*\{", r"GetJsonFilePath\(\)\s*\{", r"jsonFilePath", r"electionVersion"], per=6)


def georgia():
    say("\n==== GEORGIA (Enhanced Voting) ====")
    grep(js_bodies("https://results.sos.ga.gov/results/public/Georgia"),
         [r"environment\.api", r"\.api\}", r"apiBase", r"mediaExportPath", r"graphQlEndpoint", r"query\s*[A-Z][A-Za-z]+\s*[\(\{]"], per=8)
    for p in ("/results/public/api/elections", "/results/public/api/elections/Georgia", "/results/public/api/states", "/results/public/api/config",
              "/results/public/api/election-lookup"):
        r = fetch("https://results.sos.ga.gov" + p)
        say(f"  GET {p}: status {r.status_code}, {len(r.content)} bytes {re.sub(chr(10), ' ', r.text[:200])}")


def tables(url, label, limit=6):
    say(f"\n==== {label}: {url} ====")
    r = fetch(url)
    say(f"  status {r.status_code}, {len(r.text):,} chars")
    try:
        ts = pd.read_html(io.StringIO(r.text))
    except Exception as ex:
        say(f"  no tables: {ex}")
        ts = []
    say(f"  {len(ts)} tables")
    for i, t in enumerate(ts[:limit]):
        say(f"  table {i}: shape {t.shape}, columns {[str(c)[:40] for c in t.columns][:10]}")
        say("    " + t.head(4).to_string().replace("\n", "\n    ")[:900])
    words = re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", r.text))
    for kw in ("Senate", "Governor"):
        m = re.search(kw, words)
        say(f"  mentions {kw}: {bool(m)}" + (f" ...{re.sub(chr(10), ' ', words[max(0, m.start() - 60):m.start() + 120])}" if m else ""))
    return r


def florida():
    tables("https://floridaelectionwatch.gov/CountyReportingStatus", "FLORIDA reporting status")
    r = tables("https://floridaelectionwatch.gov/TrackCounty/ALA", "FLORIDA county page")
    say("  links on county page:", sorted(set(re.findall(r"href=[\"']([^\"']*(?:Download|download|Export|export|csv|Csv|Statewide|Race|Contest)[^\"']*)", r.text)))[:20])
    h = fetch("https://floridaelectionwatch.gov/")
    say("  home-page links:", sorted(set(re.findall(r"href=[\"'](/[A-Za-z][^\"']{2,60})", h.text)))[:40])


def nebraska():
    r = tables("https://electionresults.nebraska.gov/", "NEBRASKA")
    say("  form inputs:", re.findall(r"<input[^>]+(?:name|id)=[\"']([^\"']+)[\"'][^>]*value=[\"']([^\"']{0,40})", r.text)[:15])
    say("  links:", sorted(set(re.findall(r"href=[\"']([^\"'#]{3,90})", r.text)))[:40])


def nevada():
    say("\n==== NEVADA ====")
    r = fetch("https://silverstateelection.nv.gov/")
    say("  html:", re.sub(r"\s+", " ", r.text[:900]))


def main():
    for f in (ohio, texas, georgia, florida, nebraska, nevada):
        try:
            f()
        except Exception as ex:
            say(f"  {f.__name__} FAILED: {type(ex).__name__}: {str(ex)[:200]}")
    txt = "\n".join(OUT) + "\n"
    open("data/portal_targets.txt", "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
