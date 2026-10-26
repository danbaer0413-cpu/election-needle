"""
Probe 7 (small): Nebraska script details, Alaska's ENRbyPrecinct.csv, Minnesota's county view, Nevada Clark/Washoe file links.
Saves data/portal_final.txt. Read-only.
"""
import re
import requests
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
OUT = []


def say(*a):
    OUT.append(" ".join(str(x) for x in a))
    open("data/portal_final.txt", "w").write("\n".join(OUT) + "\n")


def nebraska():
    say("==== NEBRASKA script ====")
    try:
        js = requests.get("https://neresultswebservice.azurewebsites.us/Scripts/script.bundle.js", headers={"User-Agent": UA}, timeout=60).text
        say(f"  bundle {len(js):,} chars")
        ids = sorted(set(re.findall(r"\b(Get[A-Z]\w+)\b", js)))
        say("  Get* names:", ids[:60])
        for key in ("GetCandidates", "GetVoterTurnoutData", "GetCountyResults", "GetResults", "ResultsAjax"):
            for m in list(re.finditer(key, js))[:2]:
                say(f"  [{key}] ...{re.sub(r'\\s+', ' ', js[max(0, m.start() - 160):m.end() + 260])}")
    except Exception as ex:
        say("  failed:", type(ex).__name__, str(ex)[:150])
    try:
        pg = requests.get("https://electionresults.nebraska.gov/resultsSW.aspx?type=SW&map=CTY", headers={"User-Agent": UA}, timeout=40).text
        for key in ("ResultsAjax", "ajax(", "ServiceUrl", "webservice"):
            for m in list(re.finditer(key, pg, re.I))[:2]:
                say(f"  [page {key}] ...{re.sub(r'\\s+', ' ', pg[max(0, m.start() - 120):m.end() + 240])}")
    except Exception as ex:
        say("  page failed:", str(ex)[:120])


def browse(ctx, label, url, file_re=None, wait=7000, show_text=300, selects=False):
    say(f"\n==== {label}: {url} ====")
    page = ctx.new_page()
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(wait)
        text = re.sub(r"\s+", " ", page.inner_text("body"))
        say(f"  status {resp.status if resp else '?'} title={page.title()[:60]!r} text={text[:show_text]!r}")
        ls = page.eval_on_selector_all("a", "els => els.map(e => [e.innerText.trim().replace(/\\s+/g,' ').slice(0,60), e.href])")
        seen = set()
        for t, h in ls:
            if h in seen:
                continue
            seen.add(h)
            if file_re and re.search(file_re, h + " " + t, re.I):
                say(f"  link {t!r} -> {h}")
        if selects:
            for sel in page.query_selector_all("select")[:4]:
                opts = [o.inner_text().strip() for o in sel.query_selector_all("option")][:12]
                say("  select options:", opts)
    except Exception as ex:
        say("  FAILED:", type(ex).__name__, str(ex)[:150])
    page.close()


def main():
    nebraska()
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(user_agent=UA, viewport={"width": 1400, "height": 900}, ignore_https_errors=True)
        for slug in ("24GENR", "26PRIM", "22GENR"):
            u = f"https://www.elections.alaska.gov/results/{slug}/ENRbyPrecinct.csv"
            say(f"\n==== ALASKA {slug} ENRbyPrecinct.csv ====")
            try:
                r = ctx.request.get(u, timeout=60000)
                body = r.text()
                lines = body.splitlines()
                say(f"  status {r.status}, {len(body):,} chars, {len(lines)} lines")
                for ln in lines[:6]:
                    say("   ", ln[:300])
                dem = [ln for ln in lines if re.search(r"Peltola|Sullivan|Dunleavy|Begich", ln)][:3]
                for ln in dem:
                    say("   [candidate row]", ln[:300])
            except Exception as ex:
                say("  failed:", type(ex).__name__, str(ex)[:150])
        browse(ctx, "MN governor county view", "https://electionresults.sos.mn.gov/Results/Index?ersElectionId=200&scenario=Governor&officeInElectionId=38695",
               file_re=r"county|download|export|media|csv|xlsx|txt|precinct", selects=True, show_text=500)
        browse(ctx, "MN results home", "https://electionresults.sos.mn.gov/200", file_re=r"county|download|export|media|csv|xlsx|txt", show_text=300)
        browse(ctx, "NV Washoe files", "https://www.washoecounty.gov/voters/results/results.php", file_re=r"\.(csv|xlsx|xls|txt|xml|zip|pdf)|results|primary", show_text=200)
        browse(ctx, "NV Clark results TV", "https://elections.clarkcountynv.gov/ElectionResultsTV/", file_re=r"ElectionResultsTV|aspx|csv|xml|json", show_text=200)
        br.close()
    print("\n".join(OUT))


if __name__ == "__main__":
    main()
