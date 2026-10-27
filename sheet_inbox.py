"""
Election-night sheet: ONE table you type or paste into; the update run turns it into each race's statewide.csv and reporting.csv.

config/sheet.json   {"url": "<published-to-web CSV link of your Google Sheet, or blank>", "file": "data/election_night.csv", "dir": "data/night"}
Every *.csv in data/night/ is read too: drop each new batch of rows there as its own file (night_2140.csv ...); nothing needs merging.
Both sources are read (the sheet link and the file in the repo); rows from both are used. A fetch that fails is skipped and logged.

Columns (one row per race + place + time you read it):
  race      race id, e.g. MI-senate, WI-governor           (required)
  county    county name; leave blank or write STATE for the statewide total
  dem, rep  vote counts (numbers, commas ok); leave blank if you only know the % counted
  pct_in    % of the expected vote counted (0-100), blank if unknown
  as_of     time you read it, e.g. 2026-11-03 21:40 (Eastern); blank = when the run saw it
  source    free text: NYT screenshot, county site ...  (not used by the model)
  force     yes = these numbers beat scraped ones for `minutes` after as_of (default 60); use to correct a bad scrape
  minutes   optional, only with force

How rows become model inputs:
  statewide row  -> <race folder>/statewide.csv   (the row with the most votes; a forced row within its window wins)
  county rows    -> <race folder>/reporting.csv   (per county: the row with the most votes, or the highest % counted)
A race with no rows in the sheet is left alone. Nothing here changes any code or any scraped feed; statewide_mode.build applies its usual rules.
"""
from __future__ import annotations
import io
import json
import os
import pandas as pd

CFG = "config/sheet.json"
COLS = ["race", "county", "dem", "rep", "pct_in", "as_of", "source", "force", "minutes"]
YES = ("yes", "y", "true", "1")


def _num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.replace("%", "").str.strip().replace({"": None, "nan": None}), errors="coerce")


def read_rows(log=print):
    try:
        cfg = json.load(open(CFG))
    except Exception:
        cfg = {}
    frames = []
    url = (cfg.get("url") or "").strip()
    if url:
        try:
            import feeds
            frames.append(pd.read_csv(io.StringIO(feeds._fetch(url, timeout=30).text), dtype=str))
            log(f"  sheet: read {len(frames[-1])} rows from the sheet link")
        except Exception as ex:
            log(f"  sheet link skipped ({str(ex)[:120]})")
    f = cfg.get("file") or "data/election_night.csv"
    if os.path.exists(f):
        try:
            frames.append(pd.read_csv(f, dtype=str))
            log(f"  sheet: read {len(frames[-1])} rows from {f}")
        except Exception as ex:
            log(f"  {f} skipped ({str(ex)[:120]})")
    import glob
    for g in sorted(glob.glob((cfg.get("dir") or "data/night").rstrip("/") + "/*.csv")):
        if os.path.basename(g).lower().startswith("early_"):
            continue                                        # early-vote batches are read by sync_early
        try:
            frames.append(pd.read_csv(g, dtype=str))
            log(f"  sheet: read {len(frames[-1])} rows from {g}")
        except Exception as ex:
            log(f"  {g} skipped ({str(ex)[:120]})")
    if not frames:
        return pd.DataFrame(columns=COLS)
    d = pd.concat(frames, ignore_index=True)
    d.columns = [str(c).strip().lower() for c in d.columns]
    for c in COLS:
        if c not in d:
            d[c] = ""
    d = d[COLS].fillna("")
    d["race"] = d["race"].astype(str).str.strip()
    d = d[d["race"] != ""].copy()
    d["dem"], d["rep"], d["pct_in"] = _num(d["dem"]), _num(d["rep"]), _num(d["pct_in"])
    d["minutes"] = _num(d["minutes"])
    t = pd.to_datetime(d["as_of"].replace("", None), errors="coerce")
    try:
        t = t.dt.tz_localize("America/New_York", nonexistent="shift_forward", ambiguous="NaT") if t.dt.tz is None else t.dt.tz_convert("America/New_York")
    except Exception:
        t = pd.Series(pd.NaT, index=d.index)
    now = pd.Timestamp.now(tz="UTC")
    d["utc"] = t.dt.tz_convert("UTC").fillna(now)
    d["force"] = d["force"].astype(str).str.strip().str.lower().isin(YES)
    d["_k"] = d["county"].astype(str).str.strip()
    return d


def sync(races: list[dict], log=print):
    """races = config races. Writes statewide.csv / reporting.csv for every race that has sheet rows."""
    d = read_rows(log)
    if d.empty:
        return 0
    ids = {r["id"].lower(): r for r in races}
    n = 0
    for rid_l, g in d.groupby(d["race"].str.lower()):
        r = ids.get(rid_l)
        if not r:
            log(f"  sheet: race '{g['race'].iloc[0]}' is not in config/races.json; rows ignored")
            continue
        folder = r.get("dir", f"data/{r['id']}")
        if not os.path.isdir(folder):
            continue
        st = g[(g["_k"] == "") | (g["_k"].str.upper().isin(["STATE", "STATEWIDE"]))]
        st = st[st["dem"].notna() & st["rep"].notna()]
        if len(st):
            forced = st[st["force"]].sort_values("utc")
            best = forced.iloc[-1] if len(forced) else st.assign(_t=st["dem"] + st["rep"]).sort_values("_t").iloc[-1]
            pd.DataFrame([dict(dem=best["dem"], rep=best["rep"], pct_in=best["pct_in"], as_of=str(best["as_of"]) or "",
                               as_of_utc=best["utc"].strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                               force="yes" if best["force"] else "", force_minutes=(best["minutes"] if best["force"] and pd.notna(best["minutes"]) else (60 if best["force"] else "")))]
                         ).to_csv(os.path.join(folder, "statewide.csv"), index=False)
        ct = g[~g.index.isin(st.index) & (g["_k"] != "") & ~g["_k"].str.upper().isin(["STATE", "STATEWIDE"])]
        ct = ct[ct["pct_in"].notna() | (ct["dem"].notna() & ct["rep"].notna())]
        if len(ct):
            rows = []
            for cty, h in ct.groupby("_k"):
                withv = h[h["dem"].notna() & h["rep"].notna()]
                row = dict(county=cty, pct_in=h["pct_in"].max())
                if len(withv):
                    b = withv.assign(_t=withv["dem"] + withv["rep"]).sort_values("_t").iloc[-1]
                    row.update(dem=b["dem"], rep=b["rep"])
                rows.append(row)
            pd.DataFrame(rows).to_csv(os.path.join(folder, "reporting.csv"), index=False)
        if len(st) or len(ct):
            n += 1
    log(f"  sheet: {n} races updated from the election-night sheet")
    return n


EARLY = ["county", "early_returned", "d_reg", "r_reg", "o_reg"]


def sync_early(races: list[dict], log=print):
    """data/night/early_*.csv  columns: race, county, early_returned, d_reg, r_reg, o_reg  (d/r/o_reg = ballots returned by party registration, optional).
    Merged into <race folder>/early.csv: a county's row is replaced when the new early_returned is at least the old one (returned ballots only go up);
    counties not in the batch are untouched. Rows for races not in config/races.json are ignored."""
    import glob
    try:
        cfg = json.load(open(CFG))
    except Exception:
        cfg = {}
    files = sorted(glob.glob((cfg.get("dir") or "data/night").rstrip("/") + "/early_*.csv"))
    if not files:
        return 0
    ids = {r["id"].lower(): r for r in races}
    from model import norm_name
    frames = []
    for f in files:
        try:
            x = pd.read_csv(f, dtype=str).fillna("")
            x.columns = [str(c).strip().lower() for c in x.columns]
            frames.append(x)
            log(f"  early batch {f}: {len(x)} rows")
        except Exception as ex:
            log(f"  {f} skipped ({str(ex)[:100]})")
    if not frames:
        return 0
    d = pd.concat(frames, ignore_index=True)
    n = 0
    for rid_l, g in d.groupby(d["race"].str.strip().str.lower()):
        r = ids.get(rid_l)
        if not r:
            log(f"  early batch: race '{g['race'].iloc[0]}' is not in config/races.json; ignored")
            continue
        path = os.path.join(r.get("dir", f"data/{r['id']}"), "early.csv")
        old = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame(columns=EARLY)
        for c in EARLY:
            if c not in old:
                old[c] = None
        old = old[EARLY].copy()
        old["_k"] = old["county"].astype(str).map(norm_name)
        cur = {k: i for i, k in zip(old.index, old["_k"])}
        new = g.copy()
        for c in EARLY[1:]:
            new[c] = _num(new[c]) if c in new else None
        new = new[new["early_returned"].notna()]
        changed = 0
        # a STATE row (statewide total only, no county table) is spread over the counties NOT named in this batch,
        # in proportion to their expected early vote (expected votes x expected early share). This carries the statewide volume and party mix, not geography.
        isst = new["county"].astype(str).str.strip().str.upper().isin(["STATE", "STATEWIDE"])
        if isst.any():
            srow = new[isst].iloc[-1]
            new = new[~isst]
            cp = os.path.join(r.get("dir", f"data/{r['id']}"), "counties.csv")
            if os.path.exists(cp):
                cc = pd.read_csv(cp)
                named = {norm_name(str(c)) for c in new["county"]}
                cc = cc[~cc["county"].astype(str).map(norm_name).isin(named)]
                wt = (pd.to_numeric(cc["exp_votes"], errors="coerce").fillna(0) * pd.to_numeric(cc["exp_early_share"], errors="coerce").fillna(0.5)).to_numpy(float)
                if wt.sum() > 0:
                    sh = wt / wt.sum()
                    spread = pd.DataFrame({"county": cc["county"].to_numpy()})
                    for c in EARLY[1:]:
                        spread[c] = (srow[c] * sh) if pd.notna(srow[c]) else None
                    new = pd.concat([new, spread], ignore_index=True)
                    log(f"  early vote: statewide row for {r['id']} spread over {len(cc)} counties")
        for row in new.to_dict("records"):
            k = norm_name(str(row["county"]))
            vals = {c: row.get(c) for c in EARLY[1:]}
            if k in cur:
                i = cur[k]
                o = pd.to_numeric(old.at[i, "early_returned"], errors="coerce")
                if pd.notna(o) and vals["early_returned"] < o:
                    continue
                for c in EARLY[1:]:
                    if pd.notna(vals[c]):
                        old.at[i, c] = vals[c]
            else:
                old = pd.concat([old, pd.DataFrame([dict(county=str(row["county"]).strip(), **vals, _k=k)])], ignore_index=True)
                cur[k] = old.index[-1]
            changed += 1
        old.drop(columns="_k").to_csv(path, index=False)
        log(f"  early vote: {changed} counties updated for {r['id']}")
        n += 1
    return n
