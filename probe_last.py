"""
Probe 6: Nebraska's data-service methods, Minnesota's result pages, New Hampshire's results page, Nevada's Clark and Washoe
results sites, Alaska's table layout, and the Wisconsin county results pages that loaded. Read-only.
Saves data/portal_last.txt.
"""
import json
import re
import requests
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
OUT = []
SKIP = re.compile(r"google|analytics|gtag|doubleclick|facebook|monsido|userway|docaccess|optimonk|mixpanel|demdex|qualtrics|weglot|cloudflare|\.(png|jpg|svg|css|woff2?|ico|ttf|js)(\?|$)", re.I)
BLOCK = re.compile(r"verify you are not a bot|security verification|Just a moment|Access Denied|you are a bot|captcha|Pardon Our Interruption", re.I)


def say(*a):
    OUT.append(" ".join(str(x) for x in a))
    open("data/portal_last.txt", "w").write("\n".join(OUT) + "\n")


def nebraska_methods():
    say("==== NEBRASKA data-service methods ====")
    try:
        js = requests.get("https://neresultswebservice.azurewebsites.us/Scripts/script.bundle.js", headers={"User-Agent": UA}, timeout=60).text
        names = sorted(set(re.findall(r"ResultsAjax\.svc/(\w+)", js)))
        say("  methods:", names)
        for n in names[:14]:
            m = re.search(r".{120}ResultsAjax\.svc/" + n + r".{220}", js, re.S)
            if m:
                say(f"  {n}: ...{re.sub(chr(10), ' ', m.group(0))}")
    except Exception as ex:
        say("  failed:", type(ex).__name__, str(ex)[:150])


def visit(ctx, label, url, wait=8000, links_re=r"result|xlsx|csv|download|export|county|2026|canvass|unofficial|media", ntab=4):
    say(f"\n==== {label}: {url} ====")
    page = ctx.new_page()
    calls = []

    def on_resp(r):
        ct = r.headers.get("content-type", "")
        if not SKIP.search(r.url) and re.search(r"json|xml|csv|excel|spreadsheet", ct, re.I):
            calls.append((r.status, r.url, ct))

    page.on("response", on_resp)
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(wait)
        text = re.sub(r"\s+", " ", page.inner_text("body"))
        say(f"  status {resp.status if resp else '?'} BLOCKED={bool(BLOCK.search(text[:500] + page.title()))} title={page.title()[:60]!r}")
        say(f"  text: {text[:300]!r}")
        tabs = page.query_selector_all("table")
        say(f"  tables: {len(tabs)}")
        for i, t in enumerate(tabs[:ntab]):
            say(f"  table {i}: " + re.sub(r"\s+", " ", t.inner_text())[:420])
        ls = page.eval_on_selector_all("a", "els => els.map(e => [e.innerText.trim().replace(/\\s+/g,' ').slice(0,60), e.href])")
        seen, n = set(), 0
        for t, h in ls:
            if h and h not in seen and re.search(links_re, t + " " + h, re.I) and not h.endswith("#"):
                seen.add(h)
                say(f"  link {t!r} -> {h}")
                n += 1
                if n >= 18:
                    break
        for s, u, ct in list(dict.fromkeys(calls))[:12]:
            say(f"  data call {s} {u[:190]} [{ct[:26]}]")
    except Exception as ex:
        say("  FAILED:", type(ex).__name__, str(ex)[:150])
    page.close()


SITES = [
    ("MN governor (Aug primary)", "https://electionresults.sos.mn.gov/Results/Index?ersElectionId=200&scenario=Governor&officeInElectionId=38695"),
    ("MN US Senate (Aug primary)", "https://electionresults.sos.mn.gov/Results/Index?ErsElectionId=200&officeInElectionIdList=38485&officeInElectionIdList=-1&scenario=USSenate&electionDate=08%2F11%2F2026%2000%3A00%3A00"),
    ("NH 2026 results", "https://www.sos.nh.gov/2026-election-results"),
    ("NH 2024 results", "https://www.sos.nh.gov/2024-election-results"),
    ("NV Clark results TV", "https://elections.clarkcountynv.gov/ElectionResultsTV/"),
    ("NV Clark early vote", "https://elections.clarkcountynv.gov/ElectionResultsTV/evturnout.aspx"),
    ("NV Washoe dashboard", "https://electionresults.washoecounty.gov/"),
    ("NV Washoe files", "https://www.washoecounty.gov/voters/results/results.php"),
    ("AK 2024 general tables", "https://www.elections.alaska.gov/election-results/e/?id=24genr"),
    ("WI Dane latest", "https://elections.countyofdane.com/Election-Result/197"),
    ("WI Waukesha", "http://electionresults.waukeshacounty.gov/contests.aspx?contest=-1"),
    ("WI Brown results", "https://www.browncountywi.gov/departments/county-clerk/elections/election-results/"),
    ("WI Outagamie 2026", "https://www.outagamie.gov/Our-County/County-Clerk/Elections/Outagamie-County-Election-Results/2026-Elections"),
    ("WI Kenosha Nov 2024", "https://www.kenoshacountywi.gov/2364/Election-Results-for-11052024"),
]


def main():
    nebraska_methods()
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(user_agent=UA, viewport={"width": 1400, "height": 900}, ignore_https_errors=True)
        for label, url in SITES:
            try:
                visit(ctx, label, url)
            except Exception as ex:
                say(f"  {label} crashed: {ex}")
        br.close()
    print("\n".join(OUT))


if __name__ == "__main__":
    main()
