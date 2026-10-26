"""
Several sources per race, merged into one picture for the model.

config/sources.csv   one row per source (many rows may share a race id):
    id, name, scope, url, fmt, sheet, + any feeds.csv column (county_col, dem_col, cand_col ...)
    scope = counties        the page/feed has a county table             (fmt as in feeds.csv: html, browser, soe, ...)
            statewide       the page shows the state's total D and R     (fmt=text)
            county:<Name>   the page shows ONE county's total D and R    (fmt=text), e.g. county:Dane
    fmt=text reads D and R totals from the page text: the Dem and Rep surnames (config/candidates.csv) followed by
    the first number of 1,000 or more. Set sheet=browser to draw the page in a headless browser first.

Rules (so a bad source can never hurt the count):
  - a source that fails or shows a bot check is skipped and logged; nothing is bypassed.
  - for each county the source with the most votes wins (counts only go up during the night, so a stale source loses).
  - the statewide total from the source with the most votes wins.
  - the result then goes to statewide_mode.build, which fills in whatever counties are still missing.
"""
from __future__ import annotations

import os
import re

import pandas as pd

from model import norm_name

NUM = re.compile(r"\d{1,3}(?:,\d{3})+|\d{4,}")
LICENSED = re.compile(r"associated press|\bAP\b|edison|decision desk|\bDDHQ\b|licensed|NBC|CNN|Fox News", re.I)


def switch_on(name, path="config/switches.json"):
    """config/switches.json: {"electiontracker": false}. A source row with a `switch` value only runs when that switch is true."""
    try:
        import json
        return bool(json.load(open(path)).get(name, False))
    except Exception:
        return False


def _text(url, browser=False):
    import feeds
    if browser:
        html = feeds._render(url)
    else:
        html = feeds._fetch(url).text
    if isinstance(html, bytes):
        html = html.decode("utf-8", "ignore")
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _surnames(rid):
    try:
        c = pd.read_csv("config/candidates.csv", dtype=str).set_index("id")
        return c.loc[rid, "dem"], c.loc[rid, "rep"]
    except Exception:
        return None, None


def read_totals(row: dict, text: str | None = None):
    """(dem, rep) totals found in page text."""
    rid = str(row.get("id"))
    d_name, r_name = _surnames(rid)
    if not d_name:
        raise ValueError(f"{rid} is not in config/candidates.csv")
    if text is None:
        text = _text(str(row["url"]), str(row.get("sheet", "")).lower() == "browser")
    try:
        min_votes = float(row.get("min_votes") or 0)
    except ValueError:
        min_votes = 0.0
    guard = str(row.get("guard", "")).strip().lower() == "licensed"
    out = []
    for nm in (d_name, r_name):
        found = None
        for m in re.finditer(re.escape(nm) + r".{0,160}?(" + NUM.pattern + ")", text, re.I):
            val = float(m.group(1).replace(",", ""))
            if val < min_votes:
                continue
            if guard:
                ctx = text[max(0, m.start() - 400): m.end() + 400]
                if LICENSED.search(ctx):
                    raise ValueError("the numbers on this page are attributed to a licensed or media source; skipped")
            found = val
            break
        if found is None:
            raise ValueError(f"could not find {nm}'s vote total on the page yet")
        out.append(found)
    return out[0], out[1]


def load_race(rid: str, path="config/sources.csv", log=print):
    """-> (county_df or None, statewide dict or None)."""
    if not os.path.exists(path):
        return None, None
    s = pd.read_csv(path, dtype=str).fillna("")
    s = s[(s["id"] == rid) & (s["url"].str.strip() != "")]
    if not len(s):
        return None, None
    from feeds import load_feed
    parts, sw = [], None
    for row in s.to_dict("records"):
        scope = (row.get("scope") or "counties").strip()
        sw_name = (row.get("switch") or "").strip()
        if sw_name and not switch_on(sw_name):
            continue                                       # switched off in config/switches.json
        tag = f"{rid} source '{row.get('name') or row['url'][:40]}'"
        try:
            if scope == "counties":
                df = load_feed(row)
                if df is not None and len(df):
                    parts.append(df[["county", "dem", "rep"] + (["final"] if "final" in df else [])])
                    log(f"  {tag}: {len(df)} counties")
            else:
                d, r = read_totals(row)
                if scope == "statewide":
                    if sw is None or d + r > sw["dem"] + sw["rep"]:
                        sw = dict(dem=d, rep=r)
                    log(f"  {tag}: statewide D {d:,.0f} R {r:,.0f}")
                elif scope.lower().startswith("county:"):
                    parts.append(pd.DataFrame([dict(county=scope.split(":", 1)[1].strip(), dem=d, rep=r, final=False)]))
                    log(f"  {tag}: {scope} D {d:,.0f} R {r:,.0f}")
                else:
                    log(f"  {tag}: unknown scope '{scope}'")
        except Exception as ex:
            log(f"  {tag} skipped ({str(ex)[:140]})")
    if not parts:
        return None, sw
    df = pd.concat(parts, ignore_index=True)
    df["_k"] = df["county"].astype(str).map(norm_name)
    df["_t"] = pd.to_numeric(df["dem"], errors="coerce").fillna(0) + pd.to_numeric(df["rep"], errors="coerce").fillna(0)
    df = df.sort_values("_t", ascending=False).drop_duplicates("_k")
    if "final" not in df:
        df["final"] = False
    df["final"] = df["final"].fillna(False).astype(bool)
    return df[["county", "dem", "rep", "final"]].reset_index(drop=True), sw


def merge_results(results, extra):
    """County rows: the larger count wins per county."""
    if extra is None or not len(extra):
        return results
    if results is None or not len(results):
        return extra
    a = pd.concat([results[["county", "dem", "rep"] + (["final"] if "final" in results else [])], extra], ignore_index=True)
    a["_k"] = a["county"].astype(str).map(norm_name)
    a["_t"] = pd.to_numeric(a["dem"], errors="coerce").fillna(0) + pd.to_numeric(a["rep"], errors="coerce").fillna(0)
    if "final" not in a:
        a["final"] = False
    a["final"] = a["final"].fillna(False).astype(bool)
    return a.sort_values("_t", ascending=False).drop_duplicates("_k")[["county", "dem", "rep", "final"]].reset_index(drop=True)
