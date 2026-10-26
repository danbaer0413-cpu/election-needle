"""
Probe 5. Georgia: the field names inside a race's county breakdown. Florida: statewide-by-county pages.
Nebraska, Alaska, Iowa: the pages/data behind their results. Ohio: the contest names. Read-only.
Saves data/portal_next.txt.
"""
import json
import re
import requests
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
H = {"User-Agent": UA}
OUT = []


def say(*a):
    OUT.append(" ".join(str(x) for x in a))
    open("data/portal_next.txt", "w").write("\n".join(OUT) + "\n")


def shape(x, d=0, maxd=7):
    if isinstance(x, dict):
        return {k: (shape(v, d + 1, maxd) if d < maxd else type(v).__name__) for k, v in list(x.items())[:18]}
    if isinstance(x, list):
        return [shape(x[0], d + 1, maxd) if x else "empty", f"...{len(x)} items"]
    return x if isinstance(x, (int, float, bool)) or (isinstance(x, str) and len(x) < 50) else type(x).__name__


def georgia():
    say("==== GEORGIA ballot-item breakdown ====")
    B = "https://results.sos.ga.gov/results/public/api/elections/Georgia/"
    for label, slug, bid in (("2024 President (finished)", "2024NovGen", "01000000-d884-2e72-6367-08dcda4b86b5"),
                             ("2026 US Senate (empty)", "11032026GeneralAndSpecialElection", "01000000-3a82-a359-4042-08df23e5ff36")):
        try:
            d = requests.get(f"{B}{slug}/data/ballot-item/{bid}", headers=H, timeout=90).json()
            say(f"-- {label}: top keys {list(d.keys())}")
            b = d.get("ballotItemWithBreakdown")
            say("   ballotItemWithBreakdown:", json.dumps(shape(b))[:3500])
        except Exception as ex:
            say(f"   {label} failed: {type(ex).__name__}: {str(ex)[:150]}")
    try:
        d = requests.get(f"{B}11032026GeneralAndSpecialElection/data", headers=H, timeout=90).json()
        names = [(x["name"][0]["text"], x["id"]) for x in d["ballotItems"] if re.search(r"^US Senate|^Governor$", x["name"][0]["text"])]
        say("2026 Senate/Governor ids:", names)
    except Exception as ex:
        say("ids failed:", str(ex)[:150])


def florida():
    say("\n==== FLORIDA ====")
    import pandas as pd, io
    B = "https://floridaelectionwatch.gov"
    for p in ("/FederalOffices/USSenator", "/StateOffices/Governor", "/Downloads"):
        try:
            t = requests.get(B + p, headers=H, timeout=40).text
            say(f"-- {p}: {len(t):,} chars")
            links = sorted(set(re.findall(r"href=[\"']([^\"']*(?:ContestResults|Download|download|csv|zip|xml|txt)[^\"']*)", t)))
            say("   links:", links[:25])
            try:
                tabs = pd.read_html(io.StringIO(t))
                say(f"   {len(tabs)} tables")
                for i, tb in enumerate(tabs[:3]):
                    say(f"   table {i} shape {tb.shape}:\n      " + tb.head(6).to_string().replace("\n", "\n      ")[:900])
            except Exception as ex:
                say("   no tables:", str(ex)[:60])
            if p != "/Downloads":
                m = re.search(r"href=[\"'](/ContestResultsByCounty/\d+)", t)
                if m:
                    t2 = requests.get(B + m.group(1), headers=H, timeout=40).text
                    tabs = pd.read_html(io.StringIO(t2))
                    say(f"   {m.group(1)}: {len(tabs)} tables; first: shape {tabs[0].shape}, columns {[str(c)[:30] for c in tabs[0].columns][:12]}")
                    say("      " + tabs[0].head(5).to_string().replace("\n", "\n      ")[:900])
        except Exception as ex:
            say(f"   {p} failed: {type(ex).__name__}: {str(ex)[:120]}")


def ohio():
    say("\n==== OHIO contest names ====")
    try:
        lst = requests.get("https://liveresults.ohiosos.gov/Api/v1/Contest/getContestList", headers=H, timeout=40).json()
        names = [c["contestName"] for g in lst for c in g.get("contestGroupings", [])]
        say("statewide-looking:", [n for n in names if re.search(r"senat|governor|president|attorney|secretary|treasurer|auditor|supreme", n, re.I) and "District" not in n][:20])
    except Exception as ex:
        say("failed:", str(ex)[:150])


def browse(ctx, label, url, host_re, wait=9000, mine=None):
    say(f"\n==== {label}: {url} ====")
    page = ctx.new_page()
    seen = []

    def on_resp(r):
        if re.search(host_re, r.url) and not re.search(r"\.(png|jpg|jpeg|svg|css|woff2?|ico|ttf)(\?|$)", r.url, re.I):
            try:
                seen.append((r.status, r.url, r.headers.get("content-type", ""), r.body()))
            except Exception:
                seen.append((r.status, r.url, "", b""))

    page.on("response", on_resp)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(wait)
        say("  text:", re.sub(r"\s+", " ", page.inner_text("body"))[:500])
        say(f"  tables: {len(page.query_selector_all('table'))}")
        for i, t in enumerate(page.query_selector_all("table")[:2]):
            say(f"  table {i}: " + re.sub(r"\s+", " ", t.inner_text())[:500])
        done = set()
        for s, u, ct, b in seen:
            if u in done:
                continue
            done.add(u)
            say(f"  {s} {u[:200]} [{ct[:28]}] {len(b):,}B")
            if "json" in ct or u.endswith(".json"):
                try:
                    say("     shape: " + json.dumps(shape(json.loads(b), 0, 4))[:700])
                except Exception:
                    pass
            if mine and re.search(mine, u):
                body = b.decode("utf-8", "replace")
                for pat in (r"current_ver", r"\.json", r"summary", r"/\$\{[^}]+\}/", r"ElectionId|electionId|EID"):
                    hits = [body[max(0, m.start() - 80):m.end() + 140].replace("\n", " ") for m in re.finditer(pat, body)][:4]
                    say(f"     JS /{pat}/ x{len(hits)}: " + " || ".join(hits)[:900])
    except Exception as ex:
        say("  FAILED:", type(ex).__name__, str(ex)[:150])
    page.close()


def main():
    for f in (georgia, florida, ohio):
        try:
            f()
        except Exception as ex:
            say(f"{f.__name__} FAILED: {ex}")
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(user_agent=UA, viewport={"width": 1400, "height": 900}, ignore_https_errors=True)
        browse(ctx, "NEBRASKA statewide by county", "https://electionresults.nebraska.gov/resultsSW.aspx?type=SW&map=CTY", r"nebraska\.gov|neresultswebservice")
        browse(ctx, "NEBRASKA congressional", "https://electionresults.nebraska.gov/resultsSW.aspx?type=CG&map=DIST", r"neresultswebservice")
        browse(ctx, "ALASKA 2024 general", "https://www.elections.alaska.gov/election-results/e/?id=24genr", r"elections\.alaska\.gov")
        browse(ctx, "IOWA primary election page", "https://electionresults.iowa.gov/IA/126082/", r"electionresults\.iowa\.gov", mine=r"main\.[0-9a-f]+\.js")
        browse(ctx, "SC list", "https://www.enr-scvotes.org/SC/", r"enr-scvotes\.org")
        br.close()


if __name__ == "__main__":
    main()
