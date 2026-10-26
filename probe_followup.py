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
    j = get("https://results.sos.ga.gov/results/public/api/jurisdictions/Georgia").json()
    say("jurisdictions keys:", list(j.keys()))
    for k, v in j.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and k != "childLocalities":
            say(f"  list {k}: {len(v)} items, first: {trim(v[0], 500)}")
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(user_agent=UA, viewport={"width": 1400, "height": 900}, ignore_https_errors=True)
        page = ctx.new_page()
        seen = []

        def on_resp(r):
            ct = r.headers.get("content-type", "")
            if "json" in ct and "/api/" in r.url:
                try:
                    seen.append((r.status, r.url, r.body()))
                except Exception:
                    seen.append((r.status, r.url, b""))

        page.on("response", on_resp)
        page.goto("https://results.sos.ga.gov/results/public/Georgia", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(5000)
        links = page.eval_on_selector_all("a", "els => els.map(e => [e.innerText.trim().slice(0,70), e.href])")
        say("election links:", [l for l in links if "elections/" in l[1] or "General" in l[0]][:15])
        for pat in (r"November 5, 2024", r"2024.*General", r"November 8, 2022", r"November 3, 2026"):
            loc = page.get_by_text(re.compile(pat, re.I)).first
            if loc.count():
                say("clicking:", pat)
                n0 = len(seen)
                try:
                    loc.click(timeout=5000)
                    page.wait_for_timeout(7000)
                except Exception as ex:
                    say("  click failed", str(ex)[:100])
                say("  now at:", page.url)
                for s, u, b in seen[n0:]:
                    say(f"  API {s} {u[:220]} {len(b):,}B")
                    try:
                        say("     shape: " + trim(json.loads(b), 500))
                    except Exception:
                        pass
                # try one race / county click for the deeper calls
                for t in (r"Senate|President", r"County|Counties"):
                    l2 = page.get_by_text(re.compile(t, re.I)).first
                    if l2.count():
                        n1 = len(seen)
                        try:
                            l2.click(timeout=4000)
                            page.wait_for_timeout(5000)
                        except Exception:
                            continue
                        say("  after clicking", t, "->", page.url)
                        for s, u, b in seen[n1:]:
                            say(f"    API {s} {u[:240]} {len(b):,}B")
                            try:
                                say("       shape: " + trim(json.loads(b), 600))
                            except Exception:
                                pass
                break
        br.close()


if __name__ == "__main__":
    for f in (texas, georgia):
        try:
            f()
        except Exception as ex:
            say(f"{f.__name__} FAILED: {type(ex).__name__}: {str(ex)[:300]}")
    print("\n".join(OUT))
