"""
Pull live results from a state feed and turn them into the `results` table the model wants.

Every state publishes differently and URLs change each cycle, so you write a small
mapping per state rather than one universal scraper. Build and test yours against last
cycle's feed before Election Night. These helpers have NOT been run against any live
state feed.

Output columns: county, dem, rep, final
"""
from __future__ import annotations

import io

import pandas as pd


def fetch_table(url: str, fmt: str = "csv", timeout: int = 20, sheet=None) -> pd.DataFrame:
    import requests  # imported lazily

    r = requests.get(url, timeout=timeout, headers={"User-Agent": "election-needle/0.1"})
    r.raise_for_status()
    if fmt == "csv":
        return pd.read_csv(io.StringIO(r.text))
    if fmt == "json":
        return pd.json_normalize(r.json())
    if fmt == "xlsx":  # needs openpyxl; `sheet` is a tab name or index
        return pd.read_excel(io.BytesIO(r.content), sheet_name=sheet or 0)
    raise ValueError("fmt must be 'csv', 'json' or 'xlsx'")


def to_results(raw: pd.DataFrame, county_col: str, dem_col: str, rep_col: str,
               pct_col: str | None = None, long_format: dict | None = None) -> pd.DataFrame:
    """Map a raw feed to model columns.

    Wide feed (one row per county): pass county_col / dem_col / rep_col.
    Long feed (one row per county x candidate): pass long_format =
        {"candidate_col": "name", "votes_col": "votes", "dem": "Smith", "rep": "Jones"}
        and set dem_col/rep_col to anything (ignored).
    pct_col, if given, is "percent reporting"; >= 100 marks the county final.
    """
    if long_format:
        c, v = long_format["candidate_col"], long_format["votes_col"]
        keep = raw[raw[c].isin([long_format["dem"], long_format["rep"]])]
        wide = keep.pivot_table(index=county_col, columns=c, values=v, aggfunc="sum").reset_index()
        out = pd.DataFrame({"county": wide[county_col].astype(str),
                            "dem": wide[long_format["dem"]], "rep": wide[long_format["rep"]]})
        if pct_col:
            pct = raw.groupby(county_col)[pct_col].max().reindex(wide[county_col]).to_numpy()
            out["final"] = pct >= 100
    else:
        out = pd.DataFrame({"county": raw[county_col].astype(str),
                            "dem": pd.to_numeric(raw[dem_col], errors="coerce"),
                            "rep": pd.to_numeric(raw[rep_col], errors="coerce")})
        if pct_col:
            out["final"] = pd.to_numeric(raw[pct_col], errors="coerce") >= 100
    if "final" not in out:
        out["final"] = False
    out["county"] = out["county"].str.strip().str.replace(r"\s+County$", "", regex=True)
    return out.fillna({"dem": 0, "rep": 0})


# ---------------------------------------------------------------------------------------------
# Plug-and-play layer: one row per race in config/feeds.csv (see ELECTION_NIGHT.md)
# ---------------------------------------------------------------------------------------------
COUNTY_NAMES = ["county", "county_name", "countyname", "jurisdiction", "reporting_unit", "region", "name", "area"]
CAND_NAMES = ["candidate", "candidate_name", "ballot_name", "choice", "choice_name", "name"]
VOTE_NAMES = ["votes", "vote_count", "total_votes", "candidatevotes", "total", "count"]
PARTY_NAMES = ["party", "party_code", "party_abbr", "party_name", "partysimplified"]


def _pick(cols, names):
    low = {str(c).lower().replace(" ", "_"): c for c in cols}
    for n in names:
        if n in low:
            return low[n]
    tail = {k.rsplit(".", 1)[-1]: c for k, c in low.items()}     # nested json: "cands.votes" -> "votes"
    for n in names:
        if n in tail:
            return tail[n]
    return None


BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml,application/xml,application/json,text/csv;q=0.9,*/*;q=0.8"}


def _fetch(url, timeout=20, tries=3):
    """GET with browser-like headers. Retries politely (waits 4 s, then 12 s) when a state site answers 403/429/5xx or times out, because
    those are often momentary; a block that persists is reported, never worked around. One retry without certificate checks if a state
    site has a broken certificate chain (public, read-only results pages)."""
    import requests, time
    last = None
    for i in range(tries):
        try:
            try:
                r = requests.get(url, timeout=timeout, headers=BROWSER)
            except requests.exceptions.SSLError:
                requests.packages.urllib3.disable_warnings()
                r = requests.get(url, timeout=timeout, headers=BROWSER, verify=False)
            if r.status_code in (403, 429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(4 * (3 ** i))
                continue
            r.raise_for_status()
            return r
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as ex:
            last = ex
            if i < tries - 1:
                time.sleep(4 * (3 ** i))
                continue
            raise
    raise last


def _read_any(url, fmt, sheet=None, records=None, explode=None, timeout=20):
    """URL or local file path -> DataFrame. fmt: csv | json | xml | xlsx."""
    import json as _json, os
    if str(url).startswith("http"):
        r = _fetch(url, timeout)
        text, content = r.text, r.content
    else:
        content = open(url, "rb").read()
        text = content.decode("utf-8", "replace")
    fmt = (fmt or "csv").lower()
    if fmt == "csv":
        return pd.read_csv(io.StringIO(text))
    if fmt == "xlsx":
        return pd.read_excel(io.BytesIO(content), sheet_name=sheet or 0)
    if fmt == "xml":
        return pd.read_xml(io.StringIO(text))
    if fmt == "json":
        data = _json.loads(text)
        for key in [k for k in str(records or "").split(".") if k]:
            data = data[int(key)] if isinstance(data, list) else data[key]
        df = pd.json_normalize(data)
        if explode and explode in df:                # one row per county x candidate from a nested list
            df = df.explode(explode).reset_index(drop=True)
            inner = pd.json_normalize(df[explode].tolist()).add_prefix(explode + ".")
            df = pd.concat([df.drop(columns=[explode]), inner], axis=1)
        return df
    raise ValueError("fmt must be csv, json, xml or xlsx")


BLOCKED_PAGE = r"verify you are not a bot|security verification|Just a moment|Access Denied|you are a bot|captcha|unusual traffic"


def _render(url, click=None, wait_ms=7000):
    """Open a page in headless Chromium (as a visitor would), let its scripts draw the numbers, and return the page HTML.
    `click` = text of a tab/link to press first (for example a race name). Raises a clear message if the site shows a bot check."""
    import re
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(user_agent=BROWSER["User-Agent"], viewport={"width": 1400, "height": 1000}, ignore_https_errors=True)
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(wait_ms)
        if click:
            try:
                page.get_by_text(re.compile(click, re.I)).first.click(timeout=6000)
                page.wait_for_timeout(wait_ms)
            except Exception:
                pass
        html = page.content()
        body = re.sub(r"\s+", " ", page.inner_text("body"))[:600]
        br.close()
    if re.search(BLOCKED_PAGE, body, re.I):
        raise ValueError(f"{url} showed a bot check, so it can't be read automatically: paste this race instead")
    return html


def _html_results(row: dict) -> pd.DataFrame:
    """fmt=html: a results web page with a county table. Finds the table whose first column best matches our baseline counties,
    then picks the Democrat's and Republican's vote columns by candidate surname (headers like 'Brown', 'Brown Votes',
    'Candidate / Brown / Votes'). Handles percent columns, commas, a Total row, and tables printed sideways."""
    import json as _json, os, re
    from model import norm_name
    rid = str(row.get("id", ""))
    clean = lambda v: "" if v is None or str(v).strip().lower() in ("", "nan", "none") else str(v).strip()
    dem, rep = clean(row.get("dem_name")), clean(row.get("rep_name"))
    if not (dem and rep):
        c = pd.read_csv("config/candidates.csv", dtype=str).set_index("id")
        dem, rep = c.loc[rid, "dem"], c.loc[rid, "rep"]
    dem_k, rep_k = dem.lower().split()[-1], rep.lower().split()[-1]
    base = set()
    try:
        races = {r["id"]: r for r in _json.load(open("config/races.json"))["races"]}
        base = {norm_name(x) for x in pd.read_csv(os.path.join(races[rid].get("dir", f"data/{rid}"), "counties.csv"))["county"]}
    except Exception:
        pass
    url = str(row.get("url"))
    if str(row.get("fmt") or "").strip().lower() == "browser":
        text = _render(url, click=clean(row.get("sheet")) or None)      # fmt=browser: let the page's scripts run first
    else:
        text = _fetch(url).text if url.startswith("http") else open(url, encoding="utf-8", errors="replace").read()
    tables = pd.read_html(io.StringIO(text))

    def flat(cols):
        return [" ".join(str(p) for p in (c if isinstance(c, tuple) else (c,)) if not str(p).startswith("Unnamed")).strip() for c in cols]

    def num(s):
        return pd.to_numeric(s.astype(str).str.replace(r"[,\s]", "", regex=True), errors="coerce")

    def votecol(cols, key):
        hits = [c for c in cols if key in str(c).lower()]
        good = [c for c in hits if "%" not in str(c) and "percent" not in str(c).lower() and "pct" not in str(c).lower()]
        return (good or hits or [None])[0]

    best = None
    for t in tables:
        for cand, sideways in ((t, False), (t.T.reset_index(), True)):          # also try the table turned sideways
            d = cand.copy()
            if not d.columns.is_unique and not isinstance(d.columns, pd.MultiIndex):
                continue
            d.columns = flat(d.columns) if isinstance(d.columns, pd.MultiIndex) else [str(c) for c in d.columns]
            if sideways and len(d) > 1:                                         # sideways: first row holds the headers
                d.columns = [str(x) for x in d.iloc[0]]
                d = d.iloc[1:].reset_index(drop=True)
            dc, rc = votecol(list(d.columns), dem_k), votecol(list(d.columns), rep_k)
            if dc is None or rc is None or dc == rc:
                continue
            ccol, score = None, -1
            for c in d.columns:
                s = d[c].astype(str).map(norm_name).isin(base).sum() if base else d[c].astype(str).str.contains(r"[A-Za-z]").sum()
                if s > score:
                    ccol, score = c, s
            if best is None or score > best[0]:
                out = pd.DataFrame({"county": d[ccol].astype(str).str.strip(), "dem": num(d[dc]), "rep": num(d[rc])})
                out = out[~out["county"].str.lower().str.contains(r"^(?:total|statewide|state total|grand total|all counties)")]
                out = out.dropna(subset=["dem", "rep"])
                best = (score, out)
    if best is None or len(best[1]) == 0:
        raise ValueError(f"no table with columns for {dem_k!r} and {rep_k!r} found on {url} (tables seen: {len(tables)})")
    out = best[1].copy()
    out["final"] = False
    out["county"] = out["county"].str.replace(r"\s+County$", "", regex=True)
    return out.reset_index(drop=True)


def _find_tx_election(ec, year="2026"):
    """Texas election id for the November general: electionInfo[year]['G'], else any record with Y==year, ET=='G'."""
    g = (ec.get("electionInfo", {}).get(year, {}) or {}).get("G") or {}
    if g:
        return str(sorted(g)[-1])
    found = []

    def walk(x, key=None):
        if isinstance(x, dict):
            if str(x.get("Y")) == year and x.get("ET") == "G" and key is not None:
                found.append(str(key))
            for k, v in x.items():
                walk(v, k)
        elif isinstance(x, list):
            for v in x:
                walk(v, key)
    walk(ec)
    return found[-1] if found else None


def _texas_results(row: dict) -> pd.DataFrame:
    """Texas SOS results site (static JSON files). feeds.csv row: fmt=texas; cand_col = regex of the race name
    (default by id: senate -> 'U\\. ?S\\. SENATOR', governor -> '^GOVERNOR'); sheet = election id (blank = find the 2026 general)."""
    import re
    B = (str(row.get("url") or "").strip().rstrip("/") or "https://results.texas-election.com") + "/static/data/"
    g = lambda k: (str(row.get(k)).strip() if row.get(k) is not None and str(row.get(k)).strip() not in ("", "nan") else None)
    rid = str(row.get("id", "")).lower()
    pat = g("cand_col") or (r"U\. ?S\. SENATOR" if "senate" in rid else r"^GOVERNOR")
    eid = g("sheet")
    if not eid:
        v = _fetch(B + "Version.json").json()["___versionNo"]
        ec = _fetch(f"{B}ElectionConstants_{v}.json").json()
        eid = _find_tx_election(ec)
        if not eid:
            raise ValueError("Texas has not listed the 2026 general election yet")
    ver = _fetch(f"{B}election/{eid}/Version.json").json()["___versionNo"]
    base = f"{B}election/{eid}/{ver}/"
    race = _fetch(base + "Race.json").json()
    ids = [r["id"] for ot in race["OfficeTypes"] for r in ot["Races"] if re.search(pat, str(r["N"]).strip(), re.I)]
    if not ids:
        raise ValueError(f"no Texas race matches /{pat}/")
    oid = str(ids[0])
    cj = _fetch(base + "County.json").json()
    rows = []
    for fips, c in cj.items():
        rc = (c.get("Races") or {}).get(oid)
        if not rc or not isinstance(rc.get("C"), dict):
            continue
        d = sum(x.get("V", 0) for x in rc["C"].values() if str(x.get("P", "")).upper().startswith("DEM"))
        r_ = sum(x.get("V", 0) for x in rc["C"].values() if str(x.get("P", "")).upper().startswith("REP"))
        tpr = rc.get("TPR") or 0
        rows.append({"county": str(c.get("N", fips)).title(), "dem": d, "rep": r_,
                     "final": bool(tpr and (rc.get("PR") or 0) >= tpr)})
    if not rows:
        raise ValueError("Texas County.json has no results for this race yet")
    return pd.DataFrame(rows)


def _ohio_results(row: dict) -> pd.DataFrame:
    """Ohio SOS live results API. feeds.csv row: fmt=ohio; cand_col = regex of the contest name (default by id:
    senate -> 'senat' (not state/district races), governor -> 'governor')."""
    import re
    base = (str(row.get("url") or "").strip().rstrip("/") or "https://liveresults.ohiosos.gov") + "/Api/v1/Contest/"
    g = lambda k: (str(row.get(k)).strip() if row.get(k) is not None and str(row.get(k)).strip() not in ("", "nan") else None)
    rid = str(row.get("id", "")).lower()
    pat = g("cand_col") or ("senat" if "senate" in rid else "governor")
    lst = _fetch(base + "getContestList").json()
    found = [(c["contestName"], c["contestObjectId"]) for grp in lst for c in grp.get("contestGroupings", [])
             if re.search(pat, c["contestName"], re.I)]
    if "senate" in rid:
        found = [f for f in found if not re.search(r"\bstate senat|district|house|representative", f[0], re.I)] or found
    if not found:
        raise ValueError(f"no Ohio contest matches /{pat}/")
    name, oid = found[0]
    import requests
    r = requests.get(base + "GetContestDetailsObject", headers=BROWSER, timeout=40,
                     params={"contestName": name, "contestObjectId": oid, "resultsLevel": "County", "countyId": ""})
    r.raise_for_status()
    rows = []
    for c in r.json().get("contestList", []):
        d = rp = 0.0
        for k in c.get("candidatesRunning", []):
            v = k.get("vCount")
            if v is None:
                v = pd.to_numeric(str(k.get("voteCount", "0")).replace(",", ""), errors="coerce")
            v = 0.0 if pd.isna(v) else float(v)
            party = str(k.get("candidateParty", "")).lower()
            if party.startswith("dem"):
                d += v
            elif party.startswith("rep"):
                rp += v
        tot = c.get("totalPrecincts") or 0
        rows.append({"county": str(c.get("name", "")).strip(), "dem": d, "rep": rp,
                     "final": bool(tot and (c.get("reportedPrecincts") or 0) >= tot)})
    if not rows:
        raise ValueError("Ohio returned no county rows for this contest")
    return pd.DataFrame(rows)


def _cell(row, k):
    v = row.get(k)
    return None if v is None or str(v).strip() in ("", "nan", "None") else str(v).strip()


def _party_side(p):
    p = str(p or "").strip().lower()
    return "dem" if p.startswith("dem") or p == "d" else ("rep" if p.startswith("rep") or p == "r" else None)


def _georgia_results(row: dict) -> pd.DataFrame:
    """Georgia SOS results (Enhanced Voting). feeds.csv row: fmt=georgia; cand_col = regex of the contest name (default by id:
    senate -> '^US Senate', governor -> '^Governor$'); sheet = election slug (blank = 11032026GeneralAndSpecialElection)."""
    import re
    root = (_cell(row, "url") or "https://results.sos.ga.gov").rstrip("/")
    slug = _cell(row, "sheet") or "11032026GeneralAndSpecialElection"
    B = f"{root}/results/public/api/elections/Georgia/{slug}/data"
    rid = str(row.get("id", "")).lower()
    pat = _cell(row, "cand_col") or (r"^US Senate" if "senate" in rid else r"^Governor$")
    items = _fetch(B).json().get("ballotItems", [])
    hit = [x for x in items if re.search(pat, (x.get("name") or [{}])[0].get("text", ""), re.I)]
    if not hit:
        raise ValueError(f"no Georgia contest matches /{pat}/")
    d = _fetch(f"{B}/ballot-item/{hit[0]['id']}").json().get("ballotItemWithBreakdown") or {}
    rows = []
    for b in d.get("breakdownResults", []):
        votes = {"dem": 0.0, "rep": 0.0}
        for o in b.get("ballotOptions", []):
            side = _party_side((o.get("party") or {}).get("abbreviation"))
            if side:
                votes[side] += float(o.get("voteCount") or 0)
        st = b.get("precinctReportingStatus") or {}
        tot = st.get("totalUnits") or 0
        rows.append({"county": re.sub(r"\s+County$", "", b["locality"]["name"][0]["text"]).strip(),
                     "dem": votes["dem"], "rep": votes["rep"], "final": bool(tot and (st.get("reportingUnits") or 0) >= tot)})
    if not rows:
        raise ValueError("Georgia returned no county rows for this contest")
    return pd.DataFrame(rows)


def _soe_browser(base, eid=None, year="2026"):
    """SOE Software sites (Iowa, South Carolina) put an invisible check in front of their files. Open the election page in a
    normal headless browser, as a visitor would, and read the data files the page itself loads. Returns (elections, sum, details)."""
    import json as _j, re
    from playwright.sync_api import sync_playwright
    got = {}
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(user_agent=BROWSER["User-Agent"], ignore_https_errors=True)
        page = ctx.new_page()

        def on_resp(r):
            m = re.search(r"/(elections|sum|details)\.json", r.url)
            if m and r.status == 200:
                try:
                    got[m.group(1)] = _j.loads(r.body())
                except Exception:
                    pass

        page.on("response", on_resp)
        if not eid:
            page.goto(base + "/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(8000)
            eid = _soe_pick_election(got.get("elections") or [], year)
        page.goto(f"{base}/{eid}/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(12000)
        br.close()
    if "sum" not in got or "details" not in got:
        raise ValueError(f"{base}: the results files did not load (election {eid}); paste this race instead")
    return got.get("elections"), got["sum"], got["details"]


def _soe_pick_election(elections, year="2026"):
    gen = [e for e in elections if "general" in str(e.get("ElectionName", "")).lower() and year in str(e.get("Date", "")) + str(e.get("ElectionName", ""))]
    if not gen:
        raise ValueError(f"no {year} general election is listed yet")
    return str(gen[-1]["EID"])


def _soe_results(row: dict) -> pd.DataFrame:
    """SOE Software election-night sites (Iowa electionresults.iowa.gov/IA, South Carolina enr-scvotes.org/SC).
    feeds.csv row: fmt=soe; url = site base incl. state code; cand_col = regex of the contest name (default by id:
    senate -> 'United States Senator', governor -> '^Governor'); sheet = election id (blank = find the 2026 general)."""
    import re
    base = (_cell(row, "url") or "").rstrip("/")
    eid = _cell(row, "sheet")
    year = "2026"
    if eid and eid.lower().startswith("year:"):          # rehearsal: sheet = year:2024 reads that year's general election
        year, eid = eid.split(":", 1)[1].strip(), None
    rid = str(row.get("id", "")).lower()
    pat = _cell(row, "cand_col") or ("United States Senator" if "senate" in rid else r"^Governor")
    try:
        if not eid:
            eid = _soe_pick_election(_fetch(base + "/elections.json").json(), year)
        ver = _fetch(f"{base}/{eid}/current_ver.txt").text.strip()
        if not ver.isdigit():
            raise ValueError("not a version number")
        sm = _fetch(f"{base}/{eid}/{ver}/json/sum.json").json()
        dt = _fetch(f"{base}/{eid}/{ver}/json/details.json").json()
    except Exception as ex:
        if "general election is listed yet" in str(ex):
            raise
        _, sm, dt = _soe_browser(base, eid, year)
    cs = [c for c in sm.get("Contests", []) if re.search(pat, str(c.get("C", "")), re.I)]
    if not cs:
        raise ValueError(f"no contest matches /{pat}/")
    c = cs[0]
    sides = [_party_side(x) for x in c.get("P", [])]
    d = next((x for x in dt.get("Contests", []) if str(x.get("K")) == str(c.get("K"))), None)
    if d is None:
        raise ValueError("no county detail for this contest yet")
    done = bool(c.get("TP") and (c.get("PR") or 0) >= c.get("TP"))
    rows = []
    for name, v in zip(d.get("P", []), d.get("V", [])):
        dem = sum(x for x, sd in zip(v, sides) if sd == "dem")
        rep = sum(x for x, sd in zip(v, sides) if sd == "rep")
        rows.append({"county": str(name).strip(), "dem": float(dem), "rep": float(rep), "final": done})
    if not rows:
        raise ValueError("no county rows yet")
    return pd.DataFrame(rows)


def _florida_results(row: dict) -> pd.DataFrame:
    """Florida Election Watch. feeds.csv row: fmt=florida; url = the race page (…/FederalOffices/USSenator or …/StateOffices/Governor).
    Follows that page's ContestResultsByCounty links and reads the first county table that holds both candidates."""
    import re
    url = _cell(row, "url")
    html = _fetch(url).text
    root = re.match(r"https?://[^/]+", url).group(0)
    links = list(dict.fromkeys(re.findall(r"href=[\"'](/ContestResultsByCounty/\d+)", html)))
    if not links:
        raise ValueError("no county-results links on the race page yet")
    last = None
    for ln in links:
        try:
            return _html_results({**row, "url": root + ln, "fmt": "html"})
        except Exception as ex:
            last = ex
    raise ValueError(f"no Florida county table held both candidates: {last}")


def _file_party(v):
    p = str(v).strip().upper()
    if p.startswith("DEM") or p == "D":
        return "dem"
    if p.startswith("REP") or p in ("R", "GOP"):
        return "rep"
    return None


def _pick_col(cols, *needles):
    low = {str(c).strip().lower().replace("_", " "): c for c in cols}
    for n in needles:
        for k, c in low.items():
            if n in k:
                return c
    return None


def _file_totals(df, contest_col, contest_re, county_col, party_col, votes_col, name_col=None, row=None):
    """Keep rows whose contest matches, map party to dem/rep, add up by county."""
    import re
    d = df[df[contest_col].astype(str).str.contains(contest_re, case=False, regex=True)].copy()
    if not len(d):
        raise ValueError(f"no contest matches /{contest_re}/ in the file yet")
    d["_side"] = d[party_col].map(_file_party)
    if name_col is not None and d["_side"].isna().all():
        for side, key in (("dem", "dem_name"), ("rep", "rep_name")):
            nm = _cell(row or {}, key)
            if nm:
                d.loc[d[name_col].astype(str).str.contains(nm, case=False), "_side"] = side
    d = d[d["_side"].notna()]
    d["_v"] = pd.to_numeric(d[votes_col].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
    w = d.pivot_table(index=county_col, columns="_side", values="_v", aggfunc="sum").reset_index()
    for c in ("dem", "rep"):
        if c not in w:
            w[c] = 0.0
    out = pd.DataFrame({"county": w[county_col].astype(str).str.strip().str.replace(r"\s+County$", "", regex=True),
                        "dem": w["dem"], "rep": w["rep"], "final": False})
    if not len(out) or (out.dem.sum() + out.rep.sum()) <= 0:
        raise ValueError("matched the contest but found no Dem/Rep votes yet")
    return out


def _ncsbe_results(row: dict) -> pd.DataFrame:
    """North Carolina State Board of Elections election-night file (tab-delimited precinct results, zipped).
    feeds.csv row: fmt=ncsbe; url = base (default https://s3.amazonaws.com/dl.ncsbe.gov/ENRS); sheet = election folder date
    like 2026_11_03 (default); cand_col = contest regex (default ^US SENATE). Adds precincts up to counties, all vote types."""
    import io
    import zipfile
    base = (_cell(row, "url") or "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS").rstrip("/")
    folder = _cell(row, "sheet") or "2026_11_03"
    ymd = folder.replace("_", "")
    url = f"{base}/{folder}/results_pct_{ymd}.zip"
    raw = _fetch(url, timeout=60).content
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = next(n for n in z.namelist() if n.lower().endswith((".txt", ".csv", ".tsv")))
    df = pd.read_csv(z.open(name), sep="\t", dtype=str, encoding="latin-1")
    cc = _pick_col(df.columns, "contest name", "contest")
    cty = _pick_col(df.columns, "county")
    pty = _pick_col(df.columns, "choice party", "party")
    vot = _pick_col(df.columns, "total votes", "votes")
    if not all((cc, cty, pty, vot)):
        raise ValueError(f"unexpected NC file columns: {list(df.columns)[:14]}")
    pat = _cell(row, "cand_col") or (r"^US SENATE" if "senate" in str(row.get("id", "")).lower() else r"GOVERNOR")
    return _file_totals(df, cc, pat, cty, pty, vot)


def _flfile_results(row: dict) -> pd.DataFrame:
    """Florida Division of Elections election-night file (one tab-delimited text file, all counties).
    feeds.csv row: fmt=flfile; url = full file URL (default https://flelectionfiles.floridados.gov/enightfilespublic/20261103_ElecResultsFL.txt);
    sheet = YYYYMMDD to use the default pattern for another date; cand_col = contest regex (senate: United States Senator, governor: Governor)."""
    import io
    url = _cell(row, "url")
    if not url or not url.lower().endswith(".txt"):
        ymd = _cell(row, "sheet") or "20261103"
        url = f"https://flelectionfiles.floridados.gov/enightfilespublic/{ymd}_ElecResultsFL.txt"
    txt = _fetch(url, timeout=90).content.decode("latin-1")
    df = pd.read_csv(io.StringIO(txt), sep="\t", dtype=str)
    cc = _pick_col(df.columns, "racename", "officedesc", "contestname", "office")
    cty = _pick_col(df.columns, "countyname", "county")
    pty = _pick_col(df.columns, "partycode", "partyname", "party")
    vot = _pick_col(df.columns, "canvotes", "votes")
    if not all((cc, cty, pty, vot)):
        raise ValueError(f"unexpected Florida file columns: {list(df.columns)[:14]}")
    pat = _cell(row, "cand_col") or (r"United States Senator|U\.?S\.? Senat" if "senate" in str(row.get("id", "")).lower() else r"^Governor")
    return _file_totals(df, cc, pat, cty, pty, vot)


def _alaska_results(row: dict) -> pd.DataFrame:
    """Alaska Division of Elections precinct file: results/<slug>/ENRbyPrecinct.csv, added up to House districts ('District 01'...).
    feeds.csv row: fmt=alaska; url = site root (blank = https://www.elections.alaska.gov); sheet = results folder (blank = 26GENR);
    cand_col = regex of the contest title (default by id: senate -> 'U.?S.? Senat', governor -> '^Governor'). First-choice votes."""
    import io, re
    root = (_cell(row, "url") or "https://www.elections.alaska.gov").rstrip("/")
    slug = _cell(row, "sheet") or "26GENR"
    url = f"{root}/results/{slug}/ENRbyPrecinct.csv"
    rid = str(row.get("id", "")).lower()
    pat = _cell(row, "cand_col") or (r"U\.?\s?S\.?\s+Senat" if "senate" in rid else r"^Governor")
    try:
        text = _fetch(url, timeout=60).text
    except Exception:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            br = p.chromium.launch()
            ctx = br.new_context(user_agent=BROWSER["User-Agent"], ignore_https_errors=True)   # same policy as _fetch: public read-only file, incomplete certificate chain
            r = ctx.request.get(url, timeout=90000)
            if r.status != 200:
                br.close()
                raise ValueError(f"Alaska results file not posted yet ({url}: HTTP {r.status})")
            text = r.text()
            br.close()
    df = pd.read_csv(io.StringIO(text.lstrip("\ufeff")), dtype=str)
    df.columns = [c.strip() for c in df.columns]
    need = {"Pct_Id", "Contest_title", "candidate_name", "Party_Code", "total_votes"}
    if not need <= set(df.columns):
        raise ValueError(f"Alaska file layout changed; columns now {list(df.columns)[:12]}")
    d = df[df["Contest_title"].astype(str).str.contains(pat, case=False, regex=True)].copy()
    if d.empty:
        raise ValueError(f"no Alaska contest matches /{pat}/ yet")
    titles = d["Contest_title"].unique()
    d = d[d["Contest_title"] == titles[0]]
    d["votes"] = pd.to_numeric(d["total_votes"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
    d["side"] = d["Party_Code"].map(_party_side)
    if not (d["side"] == "dem").any() or not (d["side"] == "rep").any():       # party codes missing: use surnames from candidates.csv
        c = pd.read_csv("config/candidates.csv", dtype=str).set_index("id")
        rid0 = str(row.get("id", ""))
        dk, rk = c.loc[rid0, "dem"].lower().split()[-1], c.loc[rid0, "rep"].lower().split()[-1]
        nm = d["candidate_name"].astype(str).str.lower()
        d.loc[nm.str.contains(dk, regex=False), "side"] = "dem"
        d.loc[nm.str.contains(rk, regex=False), "side"] = "rep"
    def dist(p):
        m = re.match(r"\s*(\d{1,2})\b", str(p))
        return f"District {int(m.group(1)):02d}" if m else "Other"
    d["county"] = d["Pct_Id"].map(dist)
    w = d[d["side"].notna()].pivot_table(index="county", columns="side", values="votes", aggfunc="sum").reset_index()
    for k in ("dem", "rep"):
        if k not in w:
            w[k] = 0.0
    w["final"] = False
    return w[["county", "dem", "rep", "final"]].fillna(0)


def load_feed(row: dict) -> pd.DataFrame:
    """row keys (all optional except url): url, fmt, sheet, json_records, json_explode, county_col, dem_col, rep_col,
    pct_col, cand_col, votes_col, party_col, dem_name, rep_name. Blank columns are auto-detected."""
    g = lambda k: (str(row.get(k)).strip() if row.get(k) is not None and str(row.get(k)).strip() not in ("", "nan") else None)
    if (g("fmt") or "").lower() in ("html", "browser"):
        return _html_results(row)
    if (g("fmt") or "").lower() == "texas":
        return _texas_results(row)
    if (g("fmt") or "").lower() == "ohio":
        return _ohio_results(row)
    if (g("fmt") or "").lower() == "georgia":
        return _georgia_results(row)
    if (g("fmt") or "").lower() == "soe":
        return _soe_results(row)
    if (g("fmt") or "").lower() == "ncsbe":
        return _ncsbe_results(row)
    if (g("fmt") or "").lower() == "flfile":
        return _flfile_results(row)
    if (g("fmt") or "").lower() == "alaska":
        return _alaska_results(row)
    if (g("fmt") or "").lower() == "florida":
        return _florida_results(row)
    raw = _read_any(g("url"), g("fmt"), g("sheet"), g("json_records"), g("json_explode"))
    county = g("county_col") or _pick(raw.columns, COUNTY_NAMES)
    if county is None:
        raise ValueError(f"cannot find the county column in {list(raw.columns)[:12]}")
    pct = g("pct_col")
    dem_col, rep_col = g("dem_col"), g("rep_col")
    if dem_col and rep_col:                                   # wide feed
        return to_results(raw, county, dem_col, rep_col, pct)
    cand = g("cand_col") or _pick(raw.columns, CAND_NAMES)
    votes = g("votes_col") or _pick(raw.columns, VOTE_NAMES)
    party = g("party_col") or _pick(raw.columns, PARTY_NAMES)
    if cand and votes and (party or (g("dem_name") and g("rep_name"))):       # long feed
        df = raw.copy()
        df[votes] = pd.to_numeric(df[votes].astype(str).str.replace(",", ""), errors="coerce")
        if g("dem_name") and g("rep_name"):
            side = df[cand].map({g("dem_name"): "dem", g("rep_name"): "rep"})
        else:
            p = df[party].astype(str).str.upper().str.strip()
            side = p.map(lambda x: "dem" if x[:3] in ("DEM", "D") or x == "D" else ("rep" if x[:3] in ("REP", "GOP", "R") or x == "R" else None))
        df["_side"] = side
        df = df[df["_side"].notna()]
        w = df.pivot_table(index=county, columns="_side", values=votes, aggfunc="sum").reset_index()
        for c in ("dem", "rep"):
            if c not in w: w[c] = 0
        out = pd.DataFrame({"county": w[county].astype(str), "dem": w["dem"], "rep": w["rep"]})
        out["final"] = False
        if pct:
            m = pd.to_numeric(raw.groupby(county)[pct].max(), errors="coerce").reindex(w[county]).to_numpy()
            out["final"] = m >= 100
        out["county"] = out["county"].str.strip().str.replace(r"\s+County$", "", regex=True)
        return out.fillna({"dem": 0, "rep": 0})
    # wide feed with auto-detected columns
    dc = next((c for c in raw.columns if "dem" in str(c).lower()), None)
    rc = next((c for c in raw.columns if "rep" in str(c).lower() or "gop" in str(c).lower()), None)
    if dc and rc:
        return to_results(raw, county, dc, rc, pct)
    raise ValueError(f"cannot tell D/R columns; set them in feeds.csv. Columns: {list(raw.columns)[:15]}")
