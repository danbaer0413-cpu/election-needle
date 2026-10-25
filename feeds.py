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


def _read_any(url, fmt, sheet=None, records=None, explode=None, timeout=20):
    """URL or local file path -> DataFrame. fmt: csv | json | xml | xlsx."""
    import json as _json, os
    if str(url).startswith("http"):
        import requests
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "election-needle/0.2"})
        r.raise_for_status()
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


def load_feed(row: dict) -> pd.DataFrame:
    """row keys (all optional except url): url, fmt, sheet, json_records, json_explode, county_col, dem_col, rep_col,
    pct_col, cand_col, votes_col, party_col, dem_name, rep_name. Blank columns are auto-detected."""
    g = lambda k: (str(row.get(k)).strip() if row.get(k) is not None and str(row.get(k)).strip() not in ("", "nan") else None)
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
