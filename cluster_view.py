"""All-needles view: every race's needle in one dashboard, laid out like an instrument cluster.

One plotly figure, one coordinate system: gauge i sits at (col * CW, -row * CH). Reads the same summary dicts as the
single-race needle (median, p05, p10, p90, p95, win_prob, pct_in), so nothing new is modelled here.
"""
from __future__ import annotations

import math

import numpy as np

from charts import BLUE, RED, arc_polygon, fmt_range, needle_segment

CW, CH = 2.5, 2.05          # cell width / height in gauge units (gauge radius = 1)
R = 15.0                    # margin shown at the ends of the dial, same as the single-race needle
BG, PANEL, INK = "#0e1117", "#171c26", "#e8ecf3"


def _kind(item) -> str:
    return "Governor" if "overnor" in str(item["meta"].get("race")) else "Senate"


def _rating_color(dem_pct: float) -> str:
    if dem_pct >= 55:
        return "#6fb3e8"
    if dem_pct <= 45:
        return "#f08a78"
    return "#cfd5df"


def build_figure(items, label, rating_text, ncols=3):
    """items: list of (race_id, race_dict). Returns a plotly Figure (or raises if plotly is missing)."""
    import plotly.graph_objects as go

    fig = go.Figure()
    nrows = max(1, math.ceil(len(items) / ncols))
    hx, hy, ht = [], [], []
    for i, (rid, item) in enumerate(items):
        s = item["summary"]
        r, c = divmod(i, ncols)
        ox, oy = c * CW, -r * CH
        dem = float(s["win_prob"]) * 100
        med = float(s["median"])

        def add(x, y, **kw):
            fig.add_trace(go.Scatter(x=np.asarray(x) + ox, y=np.asarray(y) + oy, hoverinfo="skip", showlegend=False, **kw))

        # card background
        fig.add_shape(type="rect", x0=ox - CW / 2 + 0.06, x1=ox + CW / 2 - 0.06, y0=oy - 0.78, y1=oy + 1.12,
                      fillcolor=PANEL, line=dict(color="#262d3b", width=1), layer="below")
        for a, b, col in ((-R, 0, RED), (0, R, BLUE)):
            x, y = arc_polygon(a, b, 0.62, 1.0, R, n=36)
            add(x, y, fill="toself", mode="none", fillcolor=col, opacity=0.35)
        x, y = arc_polygon(float(s["p05"]), float(s["p95"]), 0.62, 1.0, R, n=36)
        add(x, y, fill="toself", mode="none", fillcolor="rgba(255,255,255,0.16)")
        x, y = arc_polygon(float(s["p10"]), float(s["p90"]), 0.62, 1.0, R, n=36)
        add(x, y, fill="toself", mode="none", fillcolor="rgba(255,255,255,0.45)")
        # centre tick (toss-up line)
        add([0, 0], [0.62, 1.04], mode="lines", line=dict(color="#8a93a6", width=1))
        nx, ny = needle_segment(med, R, length=0.97)
        add(nx, ny, mode="lines", line=dict(color="#ffffff", width=4))
        add([0], [0], mode="markers", marker=dict(size=10, color="#ffffff", line=dict(color=BG, width=2)))

        word = rating_text(dem)
        lead = f"{'D' if med >= 0 else 'R'}+{abs(med):.1f}"
        counted = float(s.get("pct_in") or 0)
        fig.add_annotation(x=ox, y=oy - 0.17, text=f"<b>{label(item)}</b>", showarrow=False,
                           font=dict(color=INK, size=11))
        fig.add_annotation(x=ox, y=oy - 0.43, text=f"<b>{word}</b>  ·  {lead}", showarrow=False,
                           font=dict(color=_rating_color(dem), size=11))
        fig.add_annotation(x=ox, y=oy - 0.66, showarrow=False, font=dict(color="#8a93a6", size=9),
                           text=(f"{counted:.0f}% counted" if counted > 0 else f"80% range {fmt_range(float(s['p10']), float(s['p90']))}"))
        # one big invisible hover target per gauge
        hx.append(ox)
        hy.append(oy + 0.45)
        ht.append(f"<b>{label(item)}</b><br>{word} ({dem:.0f}% Dem win chance)<br>Middle estimate {lead}<br>"
                  f"Likely range (80%): {fmt_range(float(s['p10']), float(s['p90']))}<br>"
                  f"{counted:.0f}% of vote counted" if counted > 0 else
                  f"<b>{label(item)}</b><br>{word} ({dem:.0f}% Dem win chance)<br>Middle estimate {lead}<br>"
                  f"Likely range (80%): {fmt_range(float(s['p10']), float(s['p90']))}<br>Pre-election estimate")
    fig.add_trace(go.Scatter(x=hx, y=hy, mode="markers", marker=dict(size=70, opacity=0.0), text=ht,
                             hoverinfo="text", showlegend=False, hoverlabel=dict(bgcolor=PANEL, font=dict(color=INK))))
    width_units = ncols * CW
    height_units = nrows * CH
    fig.update_layout(
        height=int(max(240, height_units / width_units * 900)),
        margin=dict(l=2, r=2, t=2, b=2),
        paper_bgcolor=BG, plot_bgcolor=BG, dragmode=False,
        xaxis=dict(visible=False, range=[-CW / 2, width_units - CW / 2], fixedrange=True),
        yaxis=dict(visible=False, range=[-height_units + CH - 0.82, 1.16], scaleanchor="x", fixedrange=True),
    )
    return fig


NR = 12.0   # national dial runs R+12 to D+12


def national_figure(nat):
    """One big dial: the national environment the model assumes (and, once votes are in, what the count implies)."""
    import plotly.graph_objects as go
    from charts import _theta

    fig = go.Figure()

    def add(x, y, **kw):
        fig.add_trace(go.Scatter(x=x, y=y, hoverinfo="skip", showlegend=False, **kw))

    for a, b, col in ((-NR, 0, RED), (0, NR, BLUE)):
        x, y = arc_polygon(a, b, 0.5, 1.0, NR, n=48)
        add(x, y, fill="toself", mode="none", fillcolor=col, opacity=0.38)
    x, y = arc_polygon(nat["p05"], nat["p95"], 0.5, 1.0, NR, n=48)
    add(x, y, fill="toself", mode="none", fillcolor="rgba(255,255,255,0.18)")
    x, y = arc_polygon(nat["p10"], nat["p90"], 0.5, 1.0, NR, n=48)
    add(x, y, fill="toself", mode="none", fillcolor="rgba(255,255,255,0.5)")
    for tv in (-8, -4, 0, 4, 8):
        th = float(_theta(tv, NR))
        r0 = 0.5 if tv == 0 else 0.93
        add([r0 * np.cos(th), 1.04 * np.cos(th)], [r0 * np.sin(th), 1.04 * np.sin(th)], mode="lines",
            line=dict(color="#8a93a6", width=1.5 if tv == 0 else 1))
        if tv:
            fig.add_annotation(x=1.14 * np.cos(th), y=1.14 * np.sin(th), showarrow=False, font=dict(color="#8a93a6", size=10),
                               text=f"{'D' if tv > 0 else 'R'}{abs(tv)}")
    # hollow marker: where the generic-ballot polls sit before the model shrinks them
    th = float(_theta(nat["generic_raw"], NR))
    add([1.03 * np.cos(th)], [1.03 * np.sin(th)], mode="markers", marker=dict(size=9, symbol="diamond", color="#f2c14e"))
    fig.add_annotation(x=1.2 * np.cos(th), y=1.2 * np.sin(th), showarrow=False, font=dict(color="#f2c14e", size=9), text="polls")
    # thin ghost needle where the model started, so you can see how far the count has moved it
    if abs(nat["shift"]) >= 0.05:
        gx, gy = needle_segment(nat["prior"], NR, 0.97)
        add(gx, gy, mode="lines", line=dict(color="rgba(255,255,255,0.35)", width=2, dash="dot"))
    nx, ny = needle_segment(nat["median"], NR, 0.97)
    add(nx, ny, mode="lines", line=dict(color="#ffffff", width=5))
    add([0], [0], mode="markers", marker=dict(size=15, color="#ffffff", line=dict(color=PANEL, width=3)))
    fig.add_annotation(x=-0.75, y=-0.1, text="GOP", showarrow=False, font=dict(color="#f08a78", size=14))
    fig.add_annotation(x=0.75, y=-0.1, text="Dem", showarrow=False, font=dict(color="#6fb3e8", size=14))
    fig.update_layout(height=260, margin=dict(l=4, r=4, t=4, b=4), dragmode=False, paper_bgcolor=PANEL, plot_bgcolor=PANEL,
                      xaxis=dict(visible=False, range=[-1.35, 1.35], fixedrange=True),
                      yaxis=dict(visible=False, range=[-0.2, 1.25], scaleanchor="x", fixedrange=True))
    return fig


def render_national(st, nat):
    """nat: the 'national' block from latest.json, or None (then the model's own assumption is shown)."""
    try:
        if not nat or "median" not in nat:
            import national_env
            nat = national_env.estimate({})
        m = float(nat["median"])
        lead = f"{'D' if m >= 0 else 'R'}+{abs(m):.1f}"
        rng = f"{'D' if nat['p10'] >= 0 else 'R'}+{abs(nat['p10']):.1f} to {'D' if nat['p90'] >= 0 else 'R'}+{abs(nat['p90']):.1f}"
        st.markdown("**National environment** - the overall national lean (Dem minus GOP) the model is built on, and what the count says it is.")
        st.plotly_chart(national_figure(nat), use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
        if nat.get("races_counted", 0) > 0:
            moved = float(nat["shift"])
            st.markdown(f"**{lead}** implied so far (80% range {rng}) - {abs(moved):.1f} pts "
                        f"{'more Democratic' if moved > 0 else 'more Republican'} than the model assumed "
                        f"(D+{nat['prior']:.1f}), from {nat['races_counted']} races with votes counted.")
        else:
            st.markdown(f"**{lead}** - the model's assumption before any votes (80% range {rng}). "
                        f"The generic-ballot polls say D+{nat['generic_raw']:.1f} (yellow marker); the model uses less of that on purpose. "
                        "After polls close the needle moves to what the counted vote implies, and the range narrows.")
        st.caption("Dotted needle = where the model started. The count only moves this once a race has 20% counted; races with more of their vote counted count for more. "
                   "Senate and governor races in the same state are not independent, so treat the range as a little too tight.")
    except Exception as ex:
        st.info(f"The national needle is not available yet ({type(ex).__name__}: {str(ex)[:120]}).")


def render(st, ready, label, rating_text, national=None):
    render_national(st, national)
    st.divider()
    st.markdown("**All needles** - every race in one place. Hover a dial for the numbers. "
                "Red left = Republican, blue right = Democrat; the white band is the likely (80%) range.")
    c1, c2, c3 = st.columns([1.1, 1.2, 1])
    kinds = c1.radio("Races", ["All", "Senate", "Governor"], horizontal=True, key="cl_kind")
    order = c2.radio("Order", ["Closest first", "By state", "Most Dem first"], horizontal=True, key="cl_order")
    ncols = c3.radio("Per row", [2, 3, 4], index=1, horizontal=True, key="cl_cols")

    items = [(k, v) for k, v in ready.items() if kinds == "All" or _kind(v) == kinds]
    if not items:
        st.info("No races to show for that filter yet.")
        return
    if order == "Closest first":
        items.sort(key=lambda kv: abs(float(kv[1]["summary"]["win_prob"]) - 0.5))
    elif order == "Most Dem first":
        items.sort(key=lambda kv: -float(kv[1]["summary"]["median"]))
    else:
        items.sort(key=lambda kv: label(kv[1]))
    fig = build_figure(items, label, rating_text, ncols=int(ncols))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
    st.caption(f"{len(items)} races. Each dial is the same needle you see on the Race tab, scaled to D+15 / R+15 at the ends.")
