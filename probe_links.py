"""
Probe 4: list the links on the static pages (AK, ME, WI counties, FL), find Nebraska's vote-total call,
and open an Iowa past election to see the SOE Software data files (Iowa and South Carolina share it).
Saves data/portal_links.txt. Read-only.
"""
import json
import re
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
OUT = []


def say(*a):
    OUT.append(" ".join(str(x) for x in a))
    open("data/portal_links.txt", "w").write("\n".join(OUT) + "\n")


def shape(x, d=0):
    if isinstance(x, dict):
        return {k: (shape(v, d + 1) if d < 3 else type(v).__name__) for k, v in list(x.items())[:14]}
    if isinstance(x, list):
        return [shape(x[0], d + 1) if x else "empty", f"...{len(x)} items"]
    return x if isinstance(x, (int, float, bool)) or (isinstance(x, str) and len(x) < 50) else type(x).__name__


def links(ctx, url, label, pat=None, limit=80, wait=6000):
    say(f"\n==== {label}: {url} ====")
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(wait)
        ls = page.eval_on_selector_all("a", "els => els.map(e => [e.innerText.trim().replace(/\\s+/g,' ').slice(0,70), e.href])")
        seen, n = set(), 0
        for t, h in ls:
            if not h or h in seen or h.startswith("javascript"):
                continue
            seen.add(h)
            if pat is None or re.search(pat, t + " " + h, re.I):
                say(f"  {t!r} -> {h}")
                n += 1
                if n >= limit:
                    break
        say(f"  ({n} shown of {len(seen)} unique links)")
        return page
    except Exception as ex:
        say("  FAILED:", type(ex).__name__, str(ex)[:150])
        page.close()


def capture(ctx, url, label, host_re, clicks=(), wait=8000):
    say(f"\n==== {label}: {url} ====")
    page = ctx.new_page()
    seen = []

    def on_resp(r):
        if re.search(host_re, r.url) and not re.search(r"\.(png|jpg|svg|css|woff2?|ico)(\?|$)", r.url, re.I):
            try:
                seen.append((r.status, r.url, r.body()))
            except Exception:
                seen.append((r.status, r.url, b""))

    page.on("response", on_resp)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(wait)
        say("  text:", re.sub(r"\s+", " ", page.inner_text("body"))[:400])
        for c in clicks:
            n0 = len(seen)
            loc = page.get_by_text(re.compile(c, re.I)).first
            if loc.count():
                try:
                    loc.click(timeout=5000)
                    page.wait_for_timeout(7000)
                    say(f"  clicked /{c}/ -> {page.url}")
                except Exception as ex:
                    say(f"  click /{c}/ failed: {str(ex)[:80]}")
        done = set()
        for s, u, b in seen:
            if u in done:
                continue
            done.add(u)
            say(f"  {s} {u[:230]} {len(b):,}B")
            try:
                say("     shape: " + json.dumps(shape(json.loads(b)))[:800])
            except Exception:
                say("     start: " + re.sub(r"\s+", " ", b[:160].decode("utf-8", "replace")))
    except Exception as ex:
        say("  FAILED:", type(ex).__name__, str(ex)[:150])
    page.close()


def powerbi(ctx, url, label):
    """Print the data tables and columns a public Power BI report exposes (its conceptual schema)."""
    say(f"\n==== {label} (Power BI schema) ====")
    page = ctx.new_page()
    got = []

    def on_resp(r):
        if "conceptualschema" in r.url:
            try:
                got.append(r.json())
            except Exception:
                pass

    page.on("response", on_resp)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(12000)
        say("  text:", re.sub(r"\s+", " ", page.inner_text("body"))[:900])
        for g in got:
            for sc in g.get("schemas", []):
                for e in sc.get("schema", {}).get("Entities", []):
                    cols = [c.get("Name") for c in e.get("Properties", [])]
                    say(f"  table {e.get('Name')!r}: {len(cols)} fields: {cols[:40]}")
        if not got:
            say("  no schema captured")
    except Exception as ex:
        say("  FAILED:", type(ex).__name__, str(ex)[:150])
    page.close()


def ga_deep(ctx):
    import requests
    say("\n==== GEORGIA deep ====")
    base = "https://results.sos.ga.gov/results/public/api/elections/Georgia/11032026GeneralAndSpecialElection/data"
    try:
        d = requests.get(base, headers={"User-Agent": UA}, timeout=60).json()
        say("  data top-level keys:", list(d.keys()))
        for k, v in d.items():
            if k == "jurisdiction":
                continue
            if isinstance(v, list):
                say(f"  {k}: list of {len(v)}; first item shape: {json.dumps(shape(v[0], 0))[:1500] if v else ''}")
            elif isinstance(v, dict):
                say(f"  {k}: dict keys {list(v.keys())[:20]}; shape {json.dumps(shape(v))[:1200]}")
            else:
                say(f"  {k}: {str(v)[:120]}")
    except Exception as ex:
        say("  data fetch failed:", type(ex).__name__, str(ex)[:150])
    for label, u in (("2026 US Senate", "https://results.sos.ga.gov/results/public/Georgia/elections/11032026GeneralAndSpecialElection/ballot-items/01000000-3a82-a359-4042-08df23e5ff36"),
                     ("2024 President", "https://results.sos.ga.gov/results/public/Georgia/elections/2024NovGen/ballot-items/01000000-d884-2e72-6367-08dcda4b86b5")):
        capture(ctx, u, "GA ballot item " + label, r"results\.sos\.ga\.gov/results/public/api", wait=10000)


def main():
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(user_agent=UA, viewport={"width": 1400, "height": 900}, ignore_https_errors=True)
        links(ctx, "https://www.elections.alaska.gov/election-results/", "ALASKA", r"result|general|2026|2024|xlsx|csv|pdf|rcv", 60)
        links(ctx, "https://www.maine.gov/sos/elections-voting/election-results-data", "MAINE", r"2026|2024|general|result|xlsx|csv|pdf|download", 60)
        links(ctx, "https://elections.wi.gov/wisconsin-county-election-websites", "WISCONSIN counties",
              r"milwaukee|dane|waukesha|brown|racine|kenosha|outagamie|winnebago|rock|marathon|washington|eau claire|la crosse|sheboygan|ozaukee|fond|jefferson|walworth", 60)
        links(ctx, "https://floridaelectionwatch.gov/", "FLORIDA", r"senator|governor|county|download|export|csv|result", 40)
        capture(ctx, "https://electionresults.nebraska.gov/", "NEBRASKA", r"neresultswebservice|electionresults\.nebraska",
                clicks=(r"U\.?S\.? Senate|Senator", r"Governor", r"County|Counties"))
        capture(ctx, "https://electionresults.iowa.gov/", "IOWA (SOE Software)", r"electionresults\.iowa\.gov",
                clicks=(r"2024 General Election",))
        ga_deep(ctx)
        powerbi(ctx, "https://app.powerbigov.us/view?r=eyJrIjoiMTk3MjM4ZWQtMTlkZi00N2QxLTk5ZTktODdhYjk3YTVmMzk3IiwidCI6ImQ1ZmI3MDg3LTM3NzctNDJhZC05NjZhLTg5MmVmNDcyMjVkMSJ9", "MICHIGAN dashboard")
        br.close()


if __name__ == "__main__":
    main()
