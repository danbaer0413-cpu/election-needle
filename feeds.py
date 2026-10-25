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
