"""Louisiana probe: open the Secretary of State's results site in headless Chromium, click into the Nov 3 U.S. House races
for the 5th and 6th districts and their parish breakdown, and save every data response the page loads
(data/probe_la/index.txt plus the bodies). Read-only. Run on GitHub: Actions -> probe-la."""
import json, os, re
from playwright.sync_api import sync_playwright

OUT = "data/probe_la"; os.makedirs(OUT, exist_ok=True)
SKIP = re.compile(r"google|analytics|gtag|doubleclick|facebook|cloudflareinsights|fonts\.|\.(png|jpg|gif|svg|css|woff2?|ico)(\?|$)", re.I)
log, seen = [], {}

def say(*a):
    log.append(" ".join(str(x) for x in a)); print(*a)

def on_resp(r):
    try:
        if SKIP.search(r.url) or r.url in seen or r.request.resource_type in ("image", "stylesheet", "font"): return
        ct = r.headers.get("content-type", ""); b = b""
        try: b = r.body()
        except Exception: pass
        n = len(seen); seen[r.url] = n
        if b and (re.search(r"json|xml|csv|text/plain|html", ct, re.I)) and n < 400:
            open(f"{OUT}/{n:03d}.txt", "wb").write(b[:400000])
        say(f"{n:03d} {r.request.method} {r.status} {r.url[:240]} [{ct[:40]}] {len(b):,}B")
    except Exception as ex:
        say("resp error", ex)

def click(page, pat, wait=3000):
    try:
        loc = page.get_by_text(re.compile(pat, re.I)).first
        if loc.count():
            loc.click(timeout=4000); page.wait_for_timeout(wait); say(f"clicked /{pat}/"); return True
    except Exception as ex:
        say(f"click /{pat}/ failed: {str(ex)[:80]}")
    return False

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                         viewport={"width": 1400, "height": 900}, ignore_https_errors=True)
    page = ctx.new_page(); page.on("response", on_resp)
    for url in ("https://voterportal.sos.la.gov/graphical", "https://voterportal.sos.la.gov/ElectionResults/ElectionResults"):
        try:
            page.goto(url, wait_until="networkidle", timeout=60000); page.wait_for_timeout(5000)
            say(f"== {url}: {page.title()[:80]!r}")
            say("text:", re.sub(r"\s+", " ", page.inner_text("body"))[:1500])
            for pat in (r"Nov(ember)?\.? ?0?3,? 2026|11/0?3/2026", r"Congress", r"U\.? ?S\.? Representative", r"5th Congressional", r"Parish"):
                click(page, pat)
            say("text after clicks:", re.sub(r"\s+", " ", page.inner_text("body"))[:1500])
            page.go_back(); page.wait_for_timeout(2000)
            for pat in (r"6th Congressional", r"Parish"):
                click(page, pat)
        except Exception as ex:
            say(f"{url} failed: {type(ex).__name__} {str(ex)[:160]}")
    br.close()
open(f"{OUT}/index.txt", "w").write("\n".join(log) + "\n")
