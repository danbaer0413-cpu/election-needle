"""
Maps that fill in as results arrive (plotly). Two views:
  us_map_figure     - the states we model, colored by who is likely to win; solid once votes are counted, pale before.
  county_map_figure - one race, counties colored by projected margin; solid once the county reports, pale before.
Colors come from the model's win probability / projected margin. They are projections, not race calls.
"""
from __future__ import annotations
import json
import os
import pandas as pd
import plotly.graph_objects as go

D3, D2, D1 = "#1f5fae", "#6fa0dc", "#bcd4f2"
R3, R2, R1 = "#b3261e", "#e0706a", "#f4c1bd"
TOSS = "#c9c9d1"
BINS = [(3, "Likely D", D3), (2, "Lean D", D2), (1, "Tilt D", D1), (0, "Toss-up", TOSS), (-1, "Tilt R", R1), (-2, "Lean R", R2), (-3, "Likely R", R3)]
LEGEND = [(label, color) for _, label, color in BINS]
REPORTING_MIN = 1.0          # % of the state counted before a state turns solid
COUNTY_REPORTING_MIN = 5.0   # % of a county counted before it turns solid


def bin_of(p: float) -> int:
    return 3 if p >= .95 else 2 if p >= .75 else 1 if p >= .55 else -3 if p <= .05 else -2 if p <= .25 else -1 if p <= .45 else 0


def _label(z: int) -> str:
    return next(l for k, l, _ in BINS if k == z)


def _scale():
    cols = [c for _, _, c in sorted(BINS, key=lambda b: b[0])]            # z = -3 ... 3
    n = len(cols); stops = []
    for i, c in enumerate(cols):
        stops += [[i / n, c], [(i + 1) / n, c]]
    return stops


def _fmt_n(x: float) -> str:
    x = float(x)
    return f"{x / 1e6:.2f}M" if x >= 1e6 else f"{x / 1e3:.0f}K" if x >= 1e4 else f"{x:,.0f}"


def _votes_line(counted, early, remaining) -> str:
    """Hover line: votes counted, early ballots already returned, and votes still to count."""
    out = f"<br>{_fmt_n(counted)} counted"
    if early and float(early) > 0:
        out += f" · {_fmt_n(early)} early ballots returned"
    return out + f"<br>about {_fmt_n(remaining)} votes left to count"


def _perf_line(counted, cm, ve, vs) -> str:
    """Hover line: how the counted vote compares with expectations (only once votes are in)."""
    try:
        if float(counted) <= 0 or cm != cm or ve != ve:
            return ""
        side = lambda x: f"{'D' if x > 0 else 'R'}+{abs(x):.1f}"
        out = f"<br>Counted so far: {side(cm)}; {'more Democratic' if ve > 0 else 'more Republican'} than expected by {abs(ve):.1f}"
        if vs == vs:
            out += f"<br>vs rest of state: {'bluer' if vs > 0 else 'redder'} by {abs(vs):.1f}"
        return out
    except Exception:
        return ""


def _state_votes(s: dict) -> tuple[float, float, float]:
    """(counted, remaining, early ballots returned) votes statewide from the unit table."""
    t = s.get("table")
    if t is None:
        return 0.0, 0.0, 0.0
    t = pd.DataFrame(t)
    if "remaining" not in t or "counted" not in t:
        return 0.0, 0.0, 0.0
    return float(t["counted"].sum()), float(t["remaining"].sum()), float(t["early_returned"].sum()) if "early_returned" in t else 0.0


def _centers(geo: dict, fips_set: set) -> dict:
    """fips -> (lon, lat): middle of the bounding box of each county's largest outline piece."""
    out = {}
    for f in geo.get("features", []):
        fid = str(f.get("id"))
        if fid not in fips_set:
            continue
        g = f.get("geometry") or {}
        polys = g.get("coordinates") or []
        if g.get("type") == "Polygon":
            polys = [polys]
        best = None
        for poly in polys:
            ring = poly[0] if poly else []
            if not ring:
                continue
            xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
            area = (max(xs) - min(xs)) * (max(ys) - min(ys))
            if best is None or area > best[0]:
                best = (area, (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        if best:
            out[fid] = (best[1], best[2])
    return out


def bubble_sizes(rem, max_px: float = 34.0, min_px: float = 4.0):
    """Marker diameters so that bubble AREA is proportional to votes left."""
    import numpy as np
    r = np.asarray(rem, dtype=float).clip(min=0)
    mx = r.max() if len(r) else 0.0
    if mx <= 0:
        return np.zeros(len(r))
    return np.where(r > 0, min_px + (max_px - min_px) * np.sqrt(r / mx), 0.0)


def us_map_figure(races: dict, kind: str, cand: dict | None = None, state_names: dict | None = None):
    """races: {race_id: {'meta':{...}, 'summary':{...}}} from latest.json. kind: 'senate' or 'governor'."""
    cand = cand or {}
    rows = []
    for rid, it in races.items():
        s = it.get("summary")
        if not s or not rid.endswith("-" + kind):
            continue
        st = rid.split("-")[0]
        z = bin_of(float(s["win_prob"]))
        lead = float(s["median"]); c = cand.get(rid, ("Dem", "GOP"))
        nm = (state_names or {}).get(st, st)
        hover = (f"<b>{nm} {kind.title()}</b><br>{c[0]} (D) vs {c[1]} (R)<br>{_label(z)} · {'D' if lead > 0 else 'R'}+{abs(lead):.1f}"
                 f"<br>Dem win {float(s['win_prob']) * 100:.0f}% · {float(s['pct_in']):.0f}% counted"
                 + (lambda cr: _votes_line(cr[0], cr[2], cr[1]) if cr[1] > 0 else "")(_state_votes(s)))
        rows.append(dict(st=st, z=z, hover=hover, rep=float(s["pct_in"]) >= REPORTING_MIN))
    df = pd.DataFrame(rows, columns=["st", "z", "hover", "rep"])
    fig = go.Figure()
    for flag, op, name in ((False, 0.42, "Forecast (not counting yet)"), (True, 1.0, "Counting")):
        d = df[df.rep == flag]
        if d.empty:
            continue
        fig.add_trace(go.Choropleth(locations=d.st, locationmode="USA-states", z=d.z, zmin=-3.5, zmax=3.5, colorscale=_scale(),
                                    showscale=False, text=d.hover, hoverinfo="text", marker_opacity=op, marker_line_color="white",
                                    marker_line_width=1, name=name))
    fig.update_layout(geo=dict(scope="usa", showlakes=False, bgcolor="rgba(0,0,0,0)", landcolor="#e9e9ee", subunitcolor="white"),
                      margin=dict(l=0, r=0, t=0, b=0), height=330, paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
    return fig


def load_geo(folder="data/geo"):
    p = os.path.join(folder, "counties.json"); q = os.path.join(folder, "county_fips.csv")
    if not (os.path.exists(p) and os.path.exists(q)):
        return None, None
    return json.load(open(p)), pd.read_csv(q, dtype={"fips": str})


def county_map_figure(summary: dict, state: str, geo, fips: pd.DataFrame, title: str = "", bubbles: bool = True, bubble_by: str = "remaining", color_by: str = "margin"):
    from model import norm_name
    t = pd.DataFrame(summary["table"])
    for _c in ("proj_margin", "pct_in", "base_margin", "counted", "remaining", "early_returned"):
        if _c in t:
            t[_c] = pd.to_numeric(t[_c], errors="coerce").fillna(0.0)
    fx = fips[fips.state == state].drop_duplicates("norm").set_index("norm")["fips"]
    t["fips"] = [fx.get(norm_name(c)) for c in t["county"]]
    t = t.dropna(subset=["fips"]).copy()
    if t.empty:
        return go.Figure()
    if color_by == "perf" and "vs_state" in t:
        # over/under-performance: how each county is running against expectations (grey until it has votes counted)
        # x3 so a 5-pt miss shows as a clear color; a county with only a sliver counted is faded in (full strength at 15% in) so a few early precincts cannot flash it dark
        t["z"] = (t["vs_expected"].where(t["counted"] > 0, 0.0) * 3 * (t["pct_in"] / 15.0).clip(0, 1)).clip(-30, 30)
    else:
        t["z"] = t["proj_margin"].clip(-30, 30)
    _er = t["early_returned"] if "early_returned" in t else pd.Series(0.0, index=t.index)
    _nan = pd.Series(float("nan"), index=t.index)
    _cm, _ve, _vs = (t[c] if c in t else _nan for c in ("counted_margin", "vs_expected", "vs_state"))
    t["hover"] = [f"<b>{c}</b><br>Projected {'D' if pm > 0 else 'R'}+{abs(pm):.1f}<br>{pi:.0f}% counted · baseline {'D' if bm > 0 else 'R'}+{abs(bm):.1f}" + _votes_line(cn, er, rm) + _perf_line(cn, a, b_, c_)
                  for c, pm, pi, bm, cn, er, rm, a, b_, c_ in zip(t["county"], t["proj_margin"], t["pct_in"], t["base_margin"], t["counted"], _er, t["remaining"], _cm, _ve, _vs)]
    fig = go.Figure()
    scale = [[0, R3], [0.5, "#f2f2f2"], [1, D3]]
    for flag, op in ((False, 0.4), (True, 1.0)):
        d = t[(t["pct_in"] >= COUNTY_REPORTING_MIN) == flag]
        if d.empty:
            continue
        fig.add_trace(go.Choropleth(geojson=geo, locations=d["fips"], z=d["z"], zmin=-30, zmax=30, colorscale=scale, showscale=False,
                                    text=d["hover"], hoverinfo="text", marker_opacity=op, marker_line_color="white", marker_line_width=0.6))
    _col = bubble_by if (bubble_by in t and float(t[bubble_by].sum()) > 0) else "remaining"
    if bubbles and "remaining" in t:         # bubble area = votes still to count (the same idea as VoteHub's ballots-cast bubbles)
        cen = _centers(geo, set(t["fips"].astype(str)))
        b = t[t["fips"].astype(str).isin(cen) & (t[_col] > 0)]
        if len(b):
            sz = bubble_sizes(b[_col].to_numpy())
            fig.add_trace(go.Scattergeo(lon=[cen[str(f)][0] for f in b["fips"]], lat=[cen[str(f)][1] for f in b["fips"]], mode="markers",
                                        marker=dict(size=sz, color="rgba(240,190,60,0.55)", line=dict(color="rgba(110,80,0,0.9)", width=0.8)),
                                        text=b["hover"], hoverinfo="text", showlegend=False))
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=360, paper_bgcolor="rgba(0,0,0,0)", title=dict(text=title, x=0.01) if title else None)
    return fig


def load_ak_geo(folder="data/geo"):
    p = os.path.join(folder, "ak_districts.json")
    return json.load(open(p)) if os.path.exists(p) else None


def _albers_ak(lon, lat):
    """Alaska Albers (equal-area conic, parallels 55 and 65, origin 50N 154W) on a unit sphere. Returns (x, y). Longitudes below -180 are fine."""
    import math
    p1, p2, p0, l0 = (math.radians(v) for v in (55.0, 65.0, 50.0, -154.0))
    n = (math.sin(p1) + math.sin(p2)) / 2
    C = math.cos(p1) ** 2 + 2 * n * math.sin(p1)
    r0 = math.sqrt(C - 2 * n * math.sin(p0)) / n
    r = math.sqrt(C - 2 * n * math.sin(math.radians(lat))) / n
    th = n * (math.radians(lon) - l0)
    return r * math.sin(th), r0 - r * math.cos(th)


def _blend(a: str, b: str, t: float) -> tuple:
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return tuple(round(x + (y - x) * t) for x, y in zip(pa, pb))


def _margin_rgb(z: float) -> tuple:
    """Projected margin (clipped to +-30) -> the red / grey / blue scale used on the county maps."""
    t = max(-30.0, min(30.0, z)) / 30.0
    return _blend("#f2f2f2", D3, t) if t >= 0 else _blend("#f2f2f2", R3, -t)


def district_map_figure(summary: dict, geo: dict, title: str = "", bubbles: bool = True, bubble_by: str = "remaining"):
    """Alaska: one shape per state House election district (our units are 'District 01'...'District 40').
    Drawn as plain filled shapes in Alaska Albers coordinates (not plotly's map layer, which struggles with the Aleutians)."""
    import re
    t = pd.DataFrame(summary["table"])
    t["loc"] = t["county"].map(lambda c: (lambda m: f"District {int(m.group(1)):02d}" if m else None)(re.search(r"(\d+)", str(c))))
    feats = {str(f.get("id")): f for f in geo.get("features", [])}
    t = t[t["loc"].isin(feats)].copy()
    for _c in ("proj_margin", "pct_in", "base_margin", "counted", "remaining", "early_returned"):
        if _c in t:
            t[_c] = pd.to_numeric(t[_c], errors="coerce").fillna(0.0)
    fig = go.Figure()
    centers = {}
    for r in t.itertuples():
        g = feats[r.loc].get("geometry") or {}
        polys = g.get("coordinates") or []
        if g.get("type") == "Polygon":
            polys = [polys]
        xs, ys, best = [], [], None
        for poly in polys:
            if not poly or not poly[0]:
                continue
            pr = [_albers_ak(x, y) for x, y in poly[0]]
            xs += [p[0] for p in pr] + [None]
            ys += [p[1] for p in pr] + [None]
            bx = [p[0] for p in pr]; by = [p[1] for p in pr]
            area = (max(bx) - min(bx)) * (max(by) - min(by))
            if best is None or area > best[0]:
                best = (area, (min(bx) + max(bx)) / 2, (min(by) + max(by)) / 2)
        if not xs:
            continue
        if best:
            centers[r.loc] = (best[1], best[2])
        z = float(r.proj_margin)
        op = 1.0 if float(r.pct_in) >= COUNTY_REPORTING_MIN else 0.4
        rgb = _margin_rgb(z)
        hover = (f"<b>{r.county}</b><br>Projected {'D' if z > 0 else 'R'}+{abs(z):.1f}"
                 f"<br>{float(r.pct_in):.0f}% counted · baseline {'D' if float(r.base_margin) > 0 else 'R'}+{abs(float(r.base_margin)):.1f}"
                 + _votes_line(r.counted, getattr(r, "early_returned", 0), r.remaining))
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", fill="toself", fillcolor=f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{op})",
                                 line=dict(color="white", width=0.6), hoveron="fills", text=hover, hoverinfo="text", showlegend=False))
        t.loc[t["loc"] == r.loc, "hover"] = hover
    _col = bubble_by if (bubble_by in t and float(t[bubble_by].sum()) > 0) else "remaining"
    if bubbles and "remaining" in t and "hover" in t:
        b = t[t["loc"].isin(centers) & (t[_col] > 0)]
        if len(b):
            fig.add_trace(go.Scatter(x=[centers[f][0] for f in b["loc"]], y=[centers[f][1] for f in b["loc"]], mode="markers",
                                     marker=dict(size=bubble_sizes(b[_col].to_numpy()), color="rgba(240,190,60,0.55)",
                                                 line=dict(color="rgba(110,80,0,0.9)", width=0.8)),
                                     text=b["hover"], hoverinfo="text", showlegend=False))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=360, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x"), hovermode="closest",
                      title=dict(text=title, x=0.01) if title else None)
    return fig
