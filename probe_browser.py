"""
Browser probe: opens each results site in headless Chromium like a real visitor and records every
data request the page makes (JSON / XML / CSV / xlsx). That reveals the hidden endpoints the
single-page sites load their numbers from. Read-only. Run on GitHub: Actions -> probe-browser.
Saves data/portal_browser.txt (send it to me).
"""
import json
import re
import sys
from playwright.sync_api import sync_playwright

SITES = {
    "GA": ["https://results.sos.ga.gov/results/public/Georgia"],
    "GA2": ["https://sos.ga.gov/election-data-hub", "https://sos.ga.gov/page/election-data-hub-unofficial-turnout"],
    "TX": ["https://results.texas-election.com/"],
    "MI": ["https://app.powerbigov.us/view?r=eyJrIjoiMTk3MjM4ZWQtMTlkZi00N2QxLTk5ZTktODdhYjk3YTVmMzk3IiwidCI6ImQ1ZmI3MDg3LTM3NzctNDJhZC05NjZhLTg5MmVmNDcyMjVkMSJ9", "https://www.michigan.gov/sos/elections/election-results-and-data", "https://mielections.us/election/results/", "https://mielections.us/election/results/2024GEN_CENR.html"],
    "NV": ["https://silverstateelection.nv.gov/"],
    "MN": ["https://electionresults.sos.mn.gov/"],
    "WI": ["https://elections.wi.gov/wisconsin-county-election-websites", "https://elections.wi.gov/elections-voting/results"],
    "NE": ["https://electionresults.nebraska.gov/"],
    "IA": ["https://electionresults.iowa.gov/", "https://sos.iowa.gov/iowans/election-results-statistics"],
    "SC": ["https://www.enr-scvotes.org/SC/", "https://scvotes.gov/elections-statistics/election-results/"],
    "KS": ["https://sos.ks.gov/elections/election-results.html"],
    "AK": ["https://www.elections.alaska.gov/election-results/"],
    "NH": ["https://www.sos.nh.gov/2026-general-election-results"],
    "FL": ["https://floridaelectionwatch.gov/", "https://dos.fl.gov/elections/data-statistics/elections-data/precinct-level-election-results/"],
    "ME": ["https://www.maine.gov/sos/elections-voting/election-results-data", "https://www.maine.gov/sos/cec/elec/results/index.html"],
    "MS": ["https://www.sos.ms.gov/elections-voting/election-results"],
    "OH": ["https://liveresults.ohiosos.gov/", "https://www.ohiosos.gov/data", "https://data.ohiosos.gov/portal/election-dashboards", "https://data.ohiosos.gov/portal/election-dashboards/absentee"],
}
DATA = re.compile(r"json|xml|csv|spreadsheet|excel|octet-stream|javascript\+json", re.I)
SKIP = re.compile(r"google|analytics|gtag|doubleclick|facebook|cloudflareinsights|fonts\.|\.(png|jpg|svg|css|woff2?)(\?|$)", re.I)
OUT = []


def say(*a):
    OUT.append(" ".join(str(x) for x in a))


def shape(x, d=0):
    if isinstance(x, dict):
        return {k: (shape(v, d + 1) if d < 3 else type(v).__name__) for k, v in list(x.items())[:14]}
    if isinstance(x, list):
        return [shape(x[0], d + 1) if x else "empty", f"...{len(x)} items"]
    return x if isinstance(x, (int, float, bool)) or (isinstance(x, str) and len(x) < 40) else type(x).__name__


def probe(ctx, st, url):
    say(f"\n==== {st}: {url} ====")
    page = ctx.new_page()
    seen = []

    def on_resp(r):
        try:
            ct = r.headers.get("content-type", "")
            if SKIP.search(r.url) or not (DATA.search(ct) or re.search(r"\.(json|csv|xml|xlsx)(\?|$)", r.url, re.I)):
                return
            body = b""
            try:
                body = r.body()
            except Exception:
                pass
            seen.append((r.request.method, r.status, r.url, ct, body))
        except Exception:
            pass

    page.on("response", on_resp)
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(6000)
        say(f"  page status {resp.status if resp else '?'}, title: {page.title()[:80]!r}")
        page.wait_for_timeout(4000)
        # click through anything that looks like a race / county link to trigger more data loads
        for text in ("Senate", "Governor", "U.S. Senate", "Statewide", "County"):
            try:
                loc = page.get_by_text(re.compile(text, re.I)).first
                if loc.count():
                    loc.click(timeout=3000)
                    page.wait_for_timeout(2500)
            except Exception:
                pass
        say(f"  visible text: {re.sub(r'\\s+', ' ', page.inner_text('body'))[:350]!r}")
    except Exception as ex:
        say(f"  FAILED: {type(ex).__name__}: {str(ex)[:160]}")
    say(f"  {len(seen)} data responses:")
    done = set()
    for m, s, u, ct, b in seen:
        if u in done:
            continue
        done.add(u)
        line = f"  {m} {s} {u[:200]}  [{ct[:40]}] {len(b):,}B"
        say(line)
        if b and len(b) > 2:
            try:
                say("      shape: " + json.dumps(shape(json.loads(b)))[:700])
            except Exception:
                say("      start: " + re.sub(r"\s+", " ", b[:200].decode("utf-8", "replace")))
    page.close()


def main(only=None):
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                             viewport={"width": 1400, "height": 900}, ignore_https_errors=True)
        for st, urls in SITES.items():
            if only and st not in only:
                continue
            for u in urls:
                try:
                    probe(ctx, st, u)
                except Exception as ex:
                    say(f"  {st} crashed: {ex}")
                open("data/portal_browser.txt", "w").write("\n".join(OUT) + "\n")
        br.close()
    txt = "\n".join(OUT) + "\n"
    open("data/portal_browser.txt", "w").write(txt)
    print(txt)


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
