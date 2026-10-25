"""Needle + history charts. Geometry is pure numpy; plotly is imported lazily."""
from __future__ import annotations

import numpy as np

RED, BLUE = "#d6604d", "#4393c3"


def _theta(m, R):
    """Margin -> angle. Left (pi) = -R (GOP), right (0) = +R (Dem)."""
    return np.pi * (1 - (np.clip(m, -R, R) + R) / (2 * R))


def arc_polygon(m_a, m_b, r_in, r_out, R=15.0, n=48):
    ms = np.linspace(m_a, m_b, n)
    th = _theta(ms, R)
    x = np.r_[r_out * np.cos(th), (r_in * np.cos(th))[::-1]]
    y = np.r_[r_out * np.sin(th), (r_in * np.sin(th))[::-1]]
    return x, y


def needle_segment(m, R=15.0, length=0.95):
    th = float(_theta(m, R))
    return np.array([0, length * np.cos(th)]), np.array([0, length * np.sin(th)])


def needle_figure(summary: dict, R: float = 15.0, title: str = "", compact: bool = False):
    """compact=True: phone-sized (no big caption inside the plot; the app shows the headline as text)."""
    import plotly.graph_objects as go

    fig = go.Figure()
    for (a, b, col) in ((-R, 0, RED), (0, R, BLUE)):
        x, y = arc_polygon(a, b, 0.35, 1.0, R)
        fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="none", fillcolor=col,
                                 opacity=0.25, hoverinfo="skip", showlegend=False))
    # 80% range
    x, y = arc_polygon(summary["p10"], summary["p90"], 0.35, 1.0, R)
    fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="none", fillcolor="rgba(40,40,40,0.55)",
                             hoverinfo="skip", showlegend=False))
    # 90% range, lighter
    x, y = arc_polygon(summary["p05"], summary["p95"], 0.35, 1.0, R)
    fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="none", fillcolor="rgba(40,40,40,0.18)",
                             hoverinfo="skip", showlegend=False))
    nx, ny = needle_segment(summary["median"], R)
    fig.add_trace(go.Scatter(x=nx, y=ny, mode="lines", line=dict(color="black", width=5),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers", marker=dict(size=14, color="black"),
                             hoverinfo="skip", showlegend=False))
    lead = summary["median"]
    who = "Dem" if lead > 0 else "GOP"
    if not compact:
        fig.add_annotation(x=0, y=-0.12, showarrow=False, font=dict(size=22),
                           text=f"<b>{who} +{abs(lead):.1f}</b>  ·  Dem win chance {summary['win_prob'] * 100:.0f}%")
    fig.add_annotation(x=-1.0, y=0.02, text="GOP", showarrow=False, font=dict(color=RED, size=14))
    fig.add_annotation(x=1.0, y=0.02, text="Dem", showarrow=False, font=dict(color=BLUE, size=14))
    fig.update_layout(title=title, height=230 if compact else 360,
                      margin=dict(l=4, r=4, t=4 if compact else 40, b=4),
                      xaxis=dict(visible=False, range=[-1.15, 1.15]),
                      yaxis=dict(visible=False, range=[-0.05 if compact else -0.25, 1.05 if compact else 1.1], scaleanchor="x"),
                      plot_bgcolor="rgba(0,0,0,0)")
    return fig


def history_figure(hist, true_margin: float | None = None):
    """hist: list of dicts with pct_in, median, p10, p90."""
    import plotly.graph_objects as go

    x = [h["pct_in"] for h in hist]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=[h["p90"] for h in hist], mode="lines", line=dict(width=0),
                             showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=[h["p10"] for h in hist], mode="lines", line=dict(width=0),
                             fill="tonexty", fillcolor="rgba(100,100,100,0.25)", name="80% range"))
    fig.add_trace(go.Scatter(x=x, y=[h["median"] for h in hist], mode="lines+markers",
                             line=dict(color="black"), name="Projected margin"))
    fig.add_hline(y=0, line_color="gray", line_dash="dot")
    if true_margin is not None:
        fig.add_hline(y=true_margin, line_color="green", line_dash="dash",
                      annotation_text="final (replay only)")
    fig.update_layout(height=260, margin=dict(l=4, r=4, t=10, b=4),
                      xaxis_title="% of expected vote counted", yaxis_title="Margin (D-R, pts)",
                      legend=dict(orientation="h", y=1.15))
    return fig


def poll_figure(pa: dict):
    """Polling-average trend: dots = individual polls (size = weight), line = our average, band = 80% range."""
    import plotly.graph_objects as go

    ser = pa["series"]
    x = [d["date"] for d in ser]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=[d["hi"] for d in ser], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=[d["lo"] for d in ser], mode="lines", line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(100,100,100,0.22)", name="80% range", hoverinfo="skip"))
    pts = pa["points"]
    fig.add_trace(go.Scatter(x=[p["date"] for p in pts], y=[p["margin"] for p in pts], mode="markers", name="Polls",
                             marker=dict(size=[6 + 22 * min(1.0, p["weight"]) for p in pts], color="rgba(60,60,60,0.45)"),
                             text=[f"{p['pollster']} ({p['grade']}) {p['margin']:+.1f}" for p in pts], hoverinfo="text"))
    fig.add_trace(go.Scatter(x=x, y=[d["avg"] for d in ser], mode="lines", line=dict(color="black", width=3), name="Our average"))
    fig.add_hline(y=0, line_color="gray", line_dash="dot")
    fig.update_layout(height=280, margin=dict(l=4, r=4, t=10, b=4), yaxis_title="Margin (D-R, pts)",
                      legend=dict(orientation="h", y=1.15))
    return fig
