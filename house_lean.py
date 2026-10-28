"""House lean map + seat chart data (no needles).

Start: Cook Political Report ratings (data/house/ratings_2026.csv = the 81 non-safe seats; the other seats are Solid, counts in config/house_totals.json).
Early vote: for states with early ballots by party and a county->district crosswalk (FL, NV, IA, KS, NE), each district's early D-R margin is compared with what its
2024 partisanship predicts (pooled regression, state by state); the gap moves the district's lean a little (capped at +/-2 pts). No party data / no crosswalk = rating only.
Election night: data/house/called.csv (state,district,winner D/R) turns a seat solid. Solid-seat calls go in config/house_totals.json (called_safe_D / called_safe_R).
Writes data/house/lean.json (read by the app's House screen)."""
from __future__ import annotations
import datetime as dt
import json
import os
import numpy as np
import pandas as pd

RATING_M = {"Likely Dem": 9.0, "Leans Dem": 5.0, "Toss-up": 0.0, "Leans Rep": -5.0, "Likely Rep": -9.0}
EARLY_K, EARLY_CAP = 0.12, 2.0
LEVELS = ["Called winners", "Likely winners", "Leaning winners", "Projected (all seats)"]
OUT = "data/house/lean.json"


def bin_for(m: float) -> str:
    if m >= 7: return "Likely D"
    if m >= 3: return "Lean D"
    if m >= 1: return "Tilt D"
    if m > -1: return "Toss-up"
    if m > -3: return "Tilt R"
    if m > -7: return "Lean R"
    return "Likely R"


# how many rating steps out a bin is: used by the slider (0 = always shown with "Likely winners", 1 = adds Lean, 2 = adds Tilt, 3 = adds Toss-up split)
BIN_LEVEL = {"Likely D": 1, "Likely R": 1, "Lean D": 2, "Lean R": 2, "Tilt D": 3, "Tilt R": 3, "Toss-up": 3}


def _dk(d):
    from house_county import dkey
    return dkey(d)


def _load_races():
    return json.load(open("config/races.json"))["races"]


def _state_early(state: str):
    """County early table with party for a state (first race dir that has party columns), or None."""
    for r in _load_races():
        if r.get("state") != state:
            continue
        p = os.path.join(r.get("dir", f"data/{r['id']}"), "early.csv")
        if not os.path.exists(p):
            continue
        e = pd.read_csv(p)
        for c in ("early_returned", "d_reg", "r_reg"):
            if c not in e:
                e[c] = np.nan
            e[c] = pd.to_numeric(e[c], errors="coerce")
        if (e["d_reg"].fillna(0) + e["r_reg"].fillna(0)).sum() > 0:
            return e
    return None


def _crosswalk(state: str):
    """county, district, share (district's share of the county's vote). New-map file for FL/NC/TX, old-lines file otherwise."""
    new = pd.read_csv("data/house/new_map_county_crosswalk.csv", dtype={"district": str})
    if state in set(new.state):
        c = new[new.state == state].copy()
    else:
        c = pd.read_csv("data/house/crosswalk.csv", dtype={"district": str})
        c = c[(c.state == state) & c.county.notna()].copy()
    c["d"] = c.district.map(_dk)
    c["share"] = pd.to_numeric(c.district_share_of_county, errors="coerce")
    n = c.groupby("county")["d"].transform("count")
    c["share"] = c["share"].fillna(1.0 / n)          # a split county with no published share: split equally (rough)
    return c


def _baseline_margin(state: str) -> dict:
    """{district: 2024 D-R two-party margin, points}. New-map states use 2024 presidential results on the new lines; others the 2024 House vote."""
    out = {}
    if state in ("FL", "TX", "OH", "NC"):
        p = pd.read_csv("data/house/new_map_pres2024.csv", dtype={"district": str})
        p = p[p.state == state]
        for r in p.to_dict("records"):
            t = r["pres_harris"] + r["pres_trump"]
            if t > 0:
                out[_dk(r["district"])] = 100 * (r["pres_harris"] - r["pres_trump"]) / t
        return out
    b = pd.read_csv("data/house/house_baselines.csv", dtype={"district": str})
    b = b[(b.state == state) & (b.year == 2024)]
    for r in b.to_dict("records"):
        t = r["dem_votes"] + r["rep_votes"]
        if t > 0:
            out[_dk(r["district"])] = 100 * (r["dem_votes"] - r["rep_votes"]) / t
    return out


def _county_baseline(state: str, cw) -> dict:
    """{district: margin} built from our county baseline table (base_margin, weighted by expected votes x share of county in the district)."""
    from model import norm_name
    for r in _load_races():
        if r.get("state") != state:
            continue
        p = os.path.join(r.get("dir", f"data/{r['id']}"), "counties.csv")
        if not os.path.exists(p):
            continue
        c = pd.read_csv(p)
        c["k"] = c["county"].astype(str).map(norm_name)
        x = cw.assign(k=cw["county"].astype(str).map(norm_name)).merge(c[["k", "base_margin", "exp_votes"]], on="k", how="inner")
        x["w"] = pd.to_numeric(x["exp_votes"], errors="coerce").fillna(0) * x["share"]
        x = x[x.w > 0]
        return {d: float((g.base_margin * g.w).sum() / g.w.sum()) for d, g in x.groupby("d")}
    return {}


def early_adjustments(log=print) -> dict:
    """{(state, district): {'adj': pts, 'early_margin': pts, 'resid': pts}} for districts where early party data exists."""
    per = {}
    for st in ("FL", "NC", "NV", "IA", "KS", "NE"):
        try:
            e = _state_early(st)
            if e is None:
                continue
            cw = _crosswalk(st)
            from house_live import SEATS
            if cw.d.nunique() < 0.8 * SEATS.get(st, 99):             # partial crosswalk (NC new map has 2 districts): don't guess
                log(f"  house early adjust {st} skipped (crosswalk covers {cw.d.nunique()} of {SEATS.get(st)} districts)")
                continue
            base = _baseline_margin(st)
            if len(base) < max(3, len(set(cw.d)) // 2):          # no district-level 2024 numbers on these lines: build from our county baselines
                base = _county_baseline(st, cw)
            from model import norm_name
            e["k"] = e["county"].astype(str).map(norm_name)
            cw["k"] = cw["county"].astype(str).map(norm_name)
            m = cw.merge(e[["k", "d_reg", "r_reg"]], on="k", how="inner")
            m["D"] = m["d_reg"].fillna(0) * m["share"]
            m["R"] = m["r_reg"].fillna(0) * m["share"]
            g = m.groupby("d")[["D", "R"]].sum()
            g = g[(g.D + g.R) > 0]
            rows = {d: 100 * (r.D - r.R) / (r.D + r.R) for d, r in g.iterrows() if d in base}
            if len(rows) >= 3:
                per[st] = {d: (base[d], y) for d, y in rows.items()}
        except Exception as ex:
            log(f"  house early adjust {st} skipped ({str(ex)[:80]})")
    if not per:
        return {}
    xs, ys = [], []
    for st, d in per.items():                       # slope pooled across states, each state demeaned
        x = np.array([v[0] for v in d.values()]); y = np.array([v[1] for v in d.values()])
        xs.append(x - x.mean()); ys.append(y - y.mean())
    X, Y = np.concatenate(xs), np.concatenate(ys)
    slope = float((X * Y).sum() / max((X * X).sum(), 1e-9))
    out = {}
    for st, d in per.items():
        x = np.array([v[0] for v in d.values()]); y = np.array([v[1] for v in d.values()])
        res = (y - y.mean()) - slope * (x - x.mean())
        for (dist, (_, ym)), r in zip(d.items(), res):
            out[(st, dist)] = {"adj": float(np.clip(EARLY_K * r, -EARLY_CAP, EARLY_CAP)), "early_margin": float(ym), "resid": float(r)}
    log(f"  House early-vote adjustment: {len(out)} districts in {sorted(per)} (pooled slope {slope:.2f})")
    return out


def load_called() -> dict:
    p = "data/house/called.csv"
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        return {}
    c = pd.read_csv(p, dtype=str).fillna("")
    out = {}
    for r in c.to_dict("records"):
        w = r.get("winner", "").strip().upper()[:1]
        if w in ("D", "R") and r.get("state"):
            out[(r["state"].strip().upper(), _dk(r["district"]))] = w
    return out


def build(log=print) -> dict:
    tot = json.load(open("config/house_totals.json"))
    rt = pd.read_csv("data/house/ratings_2026.csv", dtype={"district": str})
    adj = early_adjustments(log) if os.environ.get("HOUSE_EARLY", "1") != "0" else {}
    called = load_called()
    rows = []
    for r in rt.to_dict("records"):
        key = (r["state"], _dk(r["district"]))
        m0 = RATING_M[r["rating"]]
        a = adj.get(key, {})
        m = m0 + a.get("adj", 0.0)
        c = called.get(key)
        rows.append({"state": r["state"], "district": str(r["district"]), "rating": r["rating"], "m0": m0, "early_adj": round(a.get("adj", 0.0), 2),
                     "early_margin": None if "early_margin" not in a else round(a["early_margin"], 1),
                     "m": round(m, 2), "bin": bin_for(m), "called": c})
    cs_d, cs_r = int(tot.get("called_safe_D", 0)), int(tot.get("called_safe_R", 0))
    out = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "source": tot.get("source"),
           "districts": rows, "solid_D": int(tot["solid_D"]), "solid_R": int(tot["solid_R"]), "called_safe_D": cs_d, "called_safe_R": cs_r,
           "total": int(tot.get("total_seats", 435)), "majority": int(tot.get("majority", 218)), "early_states": sorted({k[0] for k in adj})}
    return out


def seat_counts(h: dict, level: int) -> dict:
    """Seats by status at a slider level (0-3). Returns D/R/undecided, called D/R and the 218 line."""
    dc = rc = d = r = 0
    for x in h["districts"]:
        if x["called"] == "D": dc += 1
        elif x["called"] == "R": rc += 1
    dc += h["called_safe_D"]; rc += h["called_safe_R"]
    d, r = dc, rc
    if level >= 1:
        d += h["solid_D"] - h["called_safe_D"]; r += h["solid_R"] - h["called_safe_R"]
    for x in h["districts"]:
        if x["called"]:
            continue
        lv = BIN_LEVEL[x["bin"]]
        if lv <= level:
            if x["bin"] == "Toss-up":
                if x["m"] > 0: d += 1
                elif x["m"] < 0: r += 1
            elif x["m"] > 0: d += 1
            else: r += 1
    und = h["total"] - d - r
    return {"D": d, "R": r, "U": und, "called_D": dc, "called_R": rc, "majority": h["majority"],
            "leader": "D" if d > r else "R" if r > d else None, "has_majority": "D" if d >= h["majority"] else "R" if r >= h["majority"] else None}


def seat_list(h: dict, level: int) -> list:
    """Ordered seats for the chart, left (D, strongest first) to right (R, strongest last): [(party|None, strength, called)]."""
    seats = []
    cs_d, cs_r = h["called_safe_D"], h["called_safe_R"]
    ds, rs = [], []
    for x in h["districts"]:
        if x["called"] == "D": ds.append((0, True))
        elif x["called"] == "R": rs.append((0, True))
    ds += [(0, True)] * cs_d; rs += [(0, True)] * cs_r
    if level >= 1:
        ds += [(1, False)] * (h["solid_D"] - cs_d); rs += [(1, False)] * (h["solid_R"] - cs_r)
    und = 0
    for x in h["districts"]:
        if x["called"]:
            continue
        lv = BIN_LEVEL[x["bin"]]
        if lv <= level:
            side = "D" if x["m"] > 0 else "R" if x["m"] < 0 else None
            if side == "D": ds.append((lv + 1, False))
            elif side == "R": rs.append((lv + 1, False))
    ds.sort(key=lambda t: (not t[1], t[0])); rs.sort(key=lambda t: (not t[1], t[0]), reverse=True)
    und = h["total"] - len(ds) - len(rs)
    return [("D", s, c) for s, c in ds] + [(None, 9, False)] * und + [("R", s, c) for s, c in rs]


def parliament_xy(n: int = 435, rows: int = 10):
    """(x, y) of n seats in a half-circle of concentric rows, sorted left to right (by angle), like a parliament chart."""
    radii = np.linspace(0.45, 1.0, rows)
    per = np.round(radii / radii.sum() * n).astype(int)
    per[-1] += n - per.sum()
    pts = []
    for r, k in zip(radii, per):
        ang = np.linspace(np.pi, 0, k) if k > 1 else np.array([np.pi / 2])
        for a in ang:
            pts.append((float(a), float(r)))
    pts.sort(key=lambda t: (-t[0], t[1]))
    return [(r * np.cos(a), r * np.sin(a)) for a, r in pts]


def build_and_save(log=print):
    h = build(log)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    json.dump(h, open(tmp, "w"), indent=1)
    os.replace(tmp, OUT)
    s = seat_counts(h, 3)
    log(f"House lean: {len(h['districts'])} competitive seats; projected D {s['D']} - R {s['R']} (undecided {s['U']}); early-vote adjusted: {h['early_states']}")
    return h


if __name__ == "__main__":
    build_and_save()
