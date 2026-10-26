"""
Follow-up probe. (1) Texas: show how County.json stores candidate votes + how to find the 2026 election.
(2) Georgia: open a past general election in a browser and record the data calls the results page makes.
Saves data/portal_followup.txt. Read-only.
"""
import json
import re
import requests
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
OUT = []


def say(*a):
    OUT.append(" ".join(str(x) for x in a))
    open("data/portal_followup.txt", "w").write("\n".join(OUT) + "\n")


def get(url):
    return requests.get(url, headers={"User-Agent": UA}, timeout=40)


def trim(x, n=1500):
    return json.dumps(x)[:n]


def texas():
    say("==== TEXAS ====")
    B = "https://results.texas-election.com/static/data/"
    v = get(B + "Version.json").json()["___versionNo"]
    ec = get(f"{B}ElectionConstants_{v}.json").json()
    info = ec.get("electionInfo", {})
    say("top-level keys:", list(ec.keys()))
    for yr in ("2024", "2026"):
        say(f"electionInfo[{yr}]:", trim(info.get(yr, "MISSING"), 1800))
    eid, ver = "49664", None
    ver = get(f"{B}election/{eid}/Version.json").json()
    say("election 49664 version:", ver)
    base = f"{B}election/{eid}/{ver['___versionNo']}/"
    race = get(base + "Race.json").json()
    for ot in race["OfficeTypes"]:
        for r in ot["Races"]:
            if re.search(r"senat|governor|president", r["N"], re.I):
                say("  race:", r)
    cj = get(base + "County.json").json()
    a = cj["48001"]
    say("County.json ANDERSON top keys:", {k: (v if not isinstance(v, dict) else "dict") for k, v in a.items()})
    for rid in ("1001",):
        say(f"  ANDERSON race {rid}:", trim(a["Races"].get(rid), 1500))
    say("Federal.json first race:", trim(get(base + "Federal.json").json()["Races"][0], 900))
    lk = get(base + "Lookups.json").json()
    say("Lookups sample candidates:", trim(lk["Candidates"][:3]), " counties:", trim(lk["County"][:3]))


def georgia():
    say("\n==== GEORGIA ====")
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(user_agent=UA, viewport={"width": 1400, "height": 900}, ignore_https_errors=True)
        for slug in ("2024NovGen", "11032026GeneralAndSpecialElection"):
            page = ctx.new_page()
            seen = []

            def on_resp(r, seen=seen):
                ct = r.headers.get("content-type", "")
                if "json" in ct and "/api/" in r.url:
                    try:
                        seen.append((r.status, r.url, r.body()))
                    except Exception:
                        seen.append((r.status, r.url, b""))

            page.on("response", on_resp)
            url = f"https://results.sos.ga.gov/results/public/Georgia/{slug}"
            say(f"-- {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(9000)
                say("  text:", re.sub(r"\s+", " ", page.inner_text("body"))[:500])
                links = page.eval_on_selector_all("a", "els => els.map(e => [e.innerText.trim().slice(0,60), e.href])")
                say("  links:", [l for l in links if "Georgia/" in l[1] and slug in l[1]][:12])
                for s_, u, b in seen:
                    say(f"  API {s_} {u[:240]} {len(b):,}B")
                    try:
                        say("     shape: " + trim(json.loads(b), 700))
                    except Exception:
                        pass
                # open the first race link / US Senate / President to trigger the race and county calls
                for t in (r"U\.?S\.? Senate|President|Governor|Senator",):
                    loc = page.get_by_text(re.compile(t, re.I)).first
                    if loc.count():
                        n1 = len(seen)
                        try:
                            loc.click(timeout=5000)
                            page.wait_for_timeout(8000)
                        except Exception as ex:
                            say("  click failed:", str(ex)[:100])
                        say("  after race click ->", page.url)
                        for s_, u, b in seen[n1:]:
                            say(f"  API {s_} {u[:260]} {len(b):,}B")
                            try:
                                say("     shape: " + trim(json.loads(b), 900))
                            except Exception:
                                pass
            except Exception as ex:
                say("  FAILED:", type(ex).__name__, str(ex)[:200])
            page.close()
        br.close()


if __name__ == "__main__":
    for f in (texas, georgia):
        try:
            f()
        except Exception as ex:
            say(f"{f.__name__} FAILED: {type(ex).__name__}: {str(ex)[:300]}")
    print("\n".join(OUT))
