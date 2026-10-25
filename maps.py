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
                 f"<br>Dem win {float(s['win_prob']) * 100:.0f}% · {float(s['pct_in']):.0f}% counted")
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


def county_map_figure(summary: dict, state: str, geo, fips: pd.DataFrame, title: str = ""):
    from model import norm_name
    t = pd.DataFrame(summary["table"])
    fx = fips[fips.state == state].set_index("norm")["fips"]
    t["fips"] = t["county"].map(lambda c: fx.get(norm_name(c)))
    t = t.dropna(subset=["fips"])
    t["z"] = t["proj_margin"].clip(-30, 30)
    t["hover"] = t.apply(lambda r: f"<b>{r['county']}</b><br>Projected {'D' if r['proj_margin'] > 0 else 'R'}+{abs(r['proj_margin']):.1f}"
                         f"<br>{r['pct_in']:.0f}% counted · baseline {r['base_margin']:+.1f}", axis=1)
    fig = go.Figure()
    scale = [[0, R3], [0.5, "#f2f2f2"], [1, D3]]
    for flag, op in ((False, 0.4), (True, 1.0)):
        d = t[(t["pct_in"] >= COUNTY_REPORTING_MIN) == flag]
        if d.empty:
            continue
        fig.add_trace(go.Choropleth(geojson=geo, locations=d["fips"], z=d["z"], zmin=-30, zmax=30, colorscale=scale, showscale=False,
                                    text=d["hover"], hoverinfo="text", marker_opacity=op, marker_line_color="white", marker_line_width=0.6))
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=360, paper_bgcolor="rgba(0,0,0,0)", title=dict(text=title, x=0.01) if title else None)
    return fig
