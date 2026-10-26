"""
Targeted trial for the hard states: MN, NV, NH, MI, WI (plus a Kansas/Alaska recheck).
Opens each page like a visitor and reports: status, whether we were blocked, tables on the page,
data calls the page makes, and links to results/downloads. Many county addresses below are from memory
and may be wrong; a 404 here just means "find the right link". Read-only. Saves data/portal_struggling.txt.
"""
import json
import re
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
SITES = [
    ("MN state", "https://electionresults.sos.mn.gov/"),
    ("MN Hennepin", "https://vote.hennepin.us/"),
    ("MN Ramsey", "https://www.ramseycounty.us/residents/elections-voting"),
    ("MN Dakota", "https://www.co.dakota.mn.us/Government/Elections/Pages/default.aspx"),
    ("MN Anoka", "https://www.anokacounty.us/elections"),
    ("MN St. Louis", "https://www.stlouiscountymn.gov/departments-a-m/elections/"),
    ("NV Clark", "https://elections.clarkcountynv.gov/"),
    ("NV Clark dept", "https://www.clarkcountynv.gov/government/departments/elections"),
    ("NV Washoe", "https://www.washoecounty.gov/voters/"),
    ("NV Washoe results", "https://www.washoecounty.gov/voters/results/"),
    ("NH SOS elections", "https://www.sos.nh.gov/elections"),
    ("NH electionstats", "https://nh.electionstats.com/"),
    ("NH Manchester", "https://www.manchesternh.gov/Departments/City-Clerk/Elections"),
    ("MI state", "https://mielections.us/election/results/"),
    ("MI Wayne", "https://www.waynecounty.com/elected/clerk/election-results.aspx"),
    ("MI Oakland", "https://www.oakgov.com/clerk-register-of-deeds/elections"),
    ("MI Kent", "https://www.accesskent.com/Elections/"),
    ("WI Milwaukee", "http://county.milwaukee.gov/ElectionResults23729.htm"),
    ("WI Dane", "https://elections.countyofdane.com/Election-Dates"),
    ("WI Waukesha", "http://electionresults.waukeshacounty.gov/contests.aspx?contest=-1"),
    ("WI Brown", "https://www.browncountywi.gov/departments/county-clerk/elections/"),
    ("WI Racine", "https://www.racinecounty.com/departments/county-clerk/election-information/election-results"),
    ("WI Kenosha", "https://www.kenoshacountywi.gov/1405/Election-Results"),
    ("WI Outagamie", "https://www.outagamie.gov/Our-County/County-Clerk/Elections"),
    ("WI Winnebago", "https://www.winnebagocountywi.gov/262/Election-Information"),
    ("WI Rock", "https://www.co.rock.wi.us/departments/county-clerk/election-information"),
    ("WI Marathon", "https://www.marathoncounty.gov/services/elections-voting/results"),
    ("WI Eau Claire", "https://www.eauclairecounty.gov/departments/county_clerk/elections/election_results.php"),
    ("WI La Crosse", "https://lacrossecounty.org/countyclerk/elections/election-results"),
    ("KS state", "https://sos.ks.gov/elections/election-results.html"),
    ("AK results", "https://www.elections.alaska.gov/election-results/"),
]
SKIP = re.compile(r"google|analytics|gtag|doubleclick|facebook|twitter|cloudflare|monitor\.azure|office\.net|bing\.com|virtualearth|fonts\.|\.(png|jpg|svg|css|woff2?|ico)(\?|$)", re.I)
BLOCK = re.compile(r"verify you are not a bot|security verification|Just a moment|Access Denied|you are a bot|captcha|unusual traffic", re.I)
OUT = []


def say(*a):
    OUT.append(" ".join(str(x) for x in a))
    open("data/portal_struggling.txt", "w").write("\n".join(OUT) + "\n")


def run(ctx, label, url):
    say(f"\n==== {label}: {url} ====")
    page = ctx.new_page()
    seen = []

    def on_resp(r):
        ct = r.headers.get("content-type", "")
        if SKIP.search(r.url) or not re.search(r"json|xml|csv|excel|spreadsheet", ct, re.I):
            return
        try:
            seen.append((r.status, r.url, ct, len(r.body())))
        except Exception:
            seen.append((r.status, r.url, ct, 0))

    page.on("response", on_resp)
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(6000)
        text = re.sub(r"\s+", " ", page.inner_text("body"))
        blocked = bool(BLOCK.search(text[:600] + page.title()))
        say(f"  status {resp.status if resp else '?'}  BLOCKED={blocked}  title={page.title()[:70]!r}")
        say(f"  text: {text[:260]!r}")
        say(f"  tables on page: {len(page.query_selector_all('table'))}")
        ls = page.eval_on_selector_all("a", "els => els.map(e => [e.innerText.trim().replace(/\\s+/g,' ').slice(0,60), e.href])")
        hits, seenl = [], set()
        for t, h in ls:
            if h in seenl or not h:
                continue
            seenl.add(h)
            if re.search(r"result|2026|general|csv|xlsx|download|export|unofficial|canvass", t + " " + h, re.I):
                hits.append((t, h))
        for t, h in hits[:14]:
            say(f"  link {t!r} -> {h}")
        done = set()
        for s, u, ct, n in seen:
            if u not in done:
                done.add(u)
                say(f"  data call {s} {u[:200]} [{ct[:30]}] {n:,}B")
    except Exception as ex:
        say(f"  FAILED: {type(ex).__name__}: {str(ex)[:140]}")
    page.close()


def main():
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(user_agent=UA, viewport={"width": 1400, "height": 900}, ignore_https_errors=True)
        for label, url in SITES:
            try:
                run(ctx, label, url)
            except Exception as ex:
                say(f"  {label} crashed: {ex}")
        br.close()
    print("\n".join(OUT))


if __name__ == "__main__":
    main()
