"""House screen for the app: a lean map (one square per competitive district, filled by lean), a parliament-style seat chart and a slider.
Reads data/house/lean.json (written by house_lean.py during the update run)."""
from __future__ import annotations
import json
import os
import house_lean as hl

D_COL = ["#0a3a8c", "#2b6cd9", "#4f86e0", "#8fb0ec", "#c3d5f6"]      # called, solid, likely, lean, tilt
R_COL = ["#8c1111", "#d63a3a", "#de5c5c", "#ec9a9a", "#f6c9c9"]
NEUTRAL = "#d9d9d9"
BIN_COL = {"Likely D": "#4f86e0", "Lean D": "#8fb0ec", "Tilt D": "#c3d5f6", "Toss-up": "#e6e1d3",
           "Tilt R": "#f6c9c9", "Lean R": "#ec9a9a", "Likely R": "#de5c5c"}
# NPR-style US tile grid: state -> (col, row)
GRID = {"AK": (0, 0), "ME": (10, 0), "VT": (9, 1), "NH": (10, 1),
        "WA": (0, 2), "ID": (1, 2), "MT": (2, 2), "ND": (3, 2), "MN": (4, 2), "IL": (5, 2), "WI": (6, 2), "MI": (7, 2), "NY": (8, 2), "RI": (9, 2), "MA": (10, 2),
        "OR": (0, 3), "NV": (1, 3), "WY": (2, 3), "SD": (3, 3), "IA": (4, 3), "IN": (5, 3), "OH": (6, 3), "PA": (7, 3), "NJ": (8, 3), "CT": (9, 3),
        "CA": (0, 4), "UT": (1, 4), "CO": (2, 4), "NE": (3, 4), "MO": (4, 4), "KY": (5, 4), "WV": (6, 4), "VA": (7, 4), "MD": (8, 4), "DE": (9, 4),
        "AZ": (1, 5), "NM": (2, 5), "KS": (3, 5), "AR": (4, 5), "TN": (5, 5), "NC": (6, 5), "SC": (7, 5), "DC": (8, 5),
        "OK": (3, 6), "LA": (4, 6), "MS": (5, 6), "AL": (6, 6), "GA": (7, 6), "HI": (0, 7), "TX": (3, 7), "FL": (8, 7)}


def load(path: str = hl.OUT):
    if not os.path.exists(path):
        return None
    return json.load(open(path))


def tile_positions(h: dict) -> list:
    """[(x, y, district_dict)] - district squares packed inside each state's tile (3 across, 4 for states with 10+ seats shown)."""
    by = {}
    for d in h["districts"]:
        by.setdefault(d["state"], []).append(d)
    out = []
    for st, ds in by.items():
        if st not in GRID:
            continue
        cx, cy = GRID[st]
        ds = sorted(ds, key=lambda x: (x["m"], x["district"]))          # most Democratic first
        cols = 3 if len(ds) <= 9 else 4
        rows = (len(ds) + cols - 1) // cols
        for i, d in enumerate(ds):
            r, c = divmod(i, cols)
            x = cx * 1.35 + (c - (cols - 1) / 2) * 0.27
            y = -(cy * 1.35) - (r - (rows - 1) / 2) * 0.27
            out.append((x, y, d))
    return out


def district_color(d: dict) -> str:
    if d.get("called") == "D": return D_COL[0]
    if d.get("called") == "R": return R_COL[0]
    return BIN_COL[d["bin"]]


def hover(d: dict) -> str:
    code = f"{d['state']}-{d['district']}"
    if d.get("called"):
        return f"<b>{code}</b><br>Called: {'Democrat' if d['called'] == 'D' else 'Republican'}"
    t = f"<b>{code}</b><br>{d['bin']}<br>Cook: {d['rating']}"
    if d.get("early_margin") is not None:
        t += f"<br>Early vote (party reg.): {'D' if d['early_margin'] >= 0 else 'R'}+{abs(d['early_margin']):.0f}"
        t += f"<br>Early-vote adjustment: {d['early_adj']:+.1f} pts"
    else:
        t += "<br>Rating only (no district early-vote data)"
    return t


def lean_map_figure(h: dict):
    import plotly.graph_objects as go
    pts = tile_positions(h)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="markers",
                             marker=dict(symbol="square", size=17, color=[district_color(p[2]) for p in pts], line=dict(width=1, color="#555")),
                             text=[hover(p[2]) for p in pts], hoverinfo="text", showlegend=False))
    for st, (cx, cy) in GRID.items():
        if any(d["state"] == st for d in h["districts"]):
            fig.add_annotation(x=cx * 1.35, y=-(cy * 1.35) - 0.62, text=st, showarrow=False, font=dict(size=10, color="#888"))
    fig.update_xaxes(visible=False, range=[-0.9, 14.6]); fig.update_yaxes(visible=False, range=[-10.8, 0.9], scaleanchor="x")
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def seat_figure(h: dict, level: int):
    import plotly.graph_objects as go
    seats = hl.seat_list(h, level)
    xy = hl.parliament_xy(len(seats))
    cols = [(D_COL if p == "D" else R_COL)[0 if c else min(s, 4)] if p else NEUTRAL for p, s, c in seats]
    cnt = hl.seat_counts(h, level)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[a for a, _ in xy], y=[b for _, b in xy], mode="markers", hoverinfo="skip",
                             marker=dict(size=9, color=cols, line=dict(width=0.6, color="#777" if True else "#fff")), showlegend=False))
    fig.add_shape(type="line", x0=0, x1=0, y0=0, y1=1.08, line=dict(color="#888", width=1, dash="dot"))
    fig.add_annotation(x=0, y=1.14, text=f"{cnt['majority']} for majority", showarrow=False, font=dict(size=11, color="#888"))
    fig.add_annotation(x=0, y=0.12, text=f"<b>D {cnt['D']} – R {cnt['R']}</b>", showarrow=False, font=dict(size=22))
    fig.add_annotation(x=0, y=-0.02, text=f"{cnt['U']} undecided", showarrow=False, font=dict(size=12, color="#888"))
    fig.update_xaxes(visible=False, range=[-1.1, 1.1]); fig.update_yaxes(visible=False, range=[-0.12, 1.22], scaleanchor="x")
    fig.update_layout(height=380, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def headline(cnt: dict, level: int) -> str:
    who = {"D": "Democrats", "R": "Republicans"}
    if cnt["has_majority"]:
        need = cnt["majority"]
        return f"{who[cnt['has_majority']]} have {cnt['D' if cnt['has_majority'] == 'D' else 'R']} seats, past the {need} needed for a majority."
    if cnt["leader"]:
        lead = cnt["leader"]
        short = cnt["majority"] - cnt[lead]
        return f"{who[lead]} lead with {cnt[lead]} seats, {short} short of the {cnt['majority']} needed; {cnt['U']} seats undecided."
    return f"No seats shown yet at this setting; {cnt['U']} undecided."


def render(st):
    h = load()
    if not h:
        st.info("The House view appears after the next update run (it needs data/house/lean.json).")
        return
    called = sum(1 for d in h["districts"] if d.get("called")) + h["called_safe_D"] + h["called_safe_R"]
    st.subheader("House of Representatives")
    level_name = st.select_slider("Show", options=hl.LEVELS, value=hl.LEVELS[0] if called else hl.LEVELS[3], key="house_level",
                                  help="Called winners: only seats called on election night. Likely winners: adds Solid and Likely seats. "
                                       "Leaning winners: adds Lean seats. Projected: adds Tilt seats and any Toss-up our early-vote signal tips.")
    level = hl.LEVELS.index(level_name)
    cnt = hl.seat_counts(h, level)
    st.markdown(f"**{headline(cnt, level)}**")
    st.plotly_chart(seat_figure(h, level), use_container_width=True, config={"displayModeBar": False})
    c1, c2, c3 = st.columns(3)
    c1.metric("Democrats", cnt["D"]); c2.metric("Republicans", cnt["R"]); c3.metric("Undecided", cnt["U"])
    st.markdown("**Competitive seats**")
    st.plotly_chart(lean_map_figure(h), use_container_width=True, config={"displayModeBar": False})
    st.caption("One square per competitive district, grouped by state and colored by lean (blue = Democratic, red = Republican, cream = Toss-up). "
               "Called seats turn solid dark blue or red. Hover a square for the rating and early-vote signal.")
    adj_states = ", ".join(h.get("early_states") or []) or "none yet"
    st.caption(f"Start: Cook Political Report ratings ({h.get('source')}). Early vote moves a district's lean by at most 2 points, and only where the state reports "
               f"early ballots by party and we have a county-to-district map (currently: {adj_states}). Everywhere else it is the rating alone. "
               "On election night a seat turns solid when it is called. There are no needles for House races because district polling is too thin.")
    with st.expander("District list"):
        import pandas as pd
        t = pd.DataFrame([{"District": f"{d['state']}-{d['district']}", "Lean": d["bin"], "Cook": d["rating"], "Early-vote adj. (pts)": d["early_adj"],
                           "Called": d.get("called") or ""} for d in h["districts"]]).sort_values("Lean")
        st.dataframe(t, use_container_width=True, hide_index=True)
