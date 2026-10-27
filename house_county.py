"""District % counted -> county % counted, using data/house/crosswalk.csv (shared by house_pct.py and house_live.py)."""
import os
import pandas as pd
from model import norm_name

REFUSE = {"OH"}          # crosswalk is on old lines
_CW = None


def _cw():
    global _CW
    if _CW is None:
        c = pd.read_csv("data/house/crosswalk.csv", dtype={"district": str})
        c = c[c.county.notna()].copy()
        c["d"] = c.district.astype(str).str.strip().str.lstrip("0").replace("", "0")
        c["share"] = pd.to_numeric(c.district_share_of_county, errors="coerce")
        _CW = c
    return _CW


def dkey(d):
    s = str(d).strip().upper()
    s = "AL" if s in ("AL", "AT-LARGE", "AT LARGE") else s.lstrip("0") or "0"
    return "1" if s == "AL" else s            # Alaska's one seat is district 1 in the files


def county_pct(state, pcts, county_names):
    """pcts {district: % counted} -> {normalized county: % counted}. A county needs >= half its vote covered by the districts given."""
    if state in REFUSE or not pcts:
        return {}
    pcts = {dkey(k): float(v) for k, v in pcts.items()}
    cw = _cw()
    cw = cw[cw.state == state]
    names = {norm_name(c) for c in county_names}
    out = {}
    for cty, g in cw.groupby("county"):
        k = norm_name(str(cty))
        if k not in names:
            continue
        g = g.copy()
        if g.share.isna().all():
            g["share"] = 1.0 / len(g)
        g["share"] = g.share.fillna(g.share.mean())
        have = g[g.d.isin(pcts)]
        if not len(have) or have.share.sum() / g.share.sum() < 0.5:
            continue
        out[k] = round(sum(r.share * pcts[r.d] for r in have.itertuples()) / have.share.sum(), 1)
    return out
