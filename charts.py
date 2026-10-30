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


def fmt_range(lo: float, hi: float) -> str:
    """'D+0.2 to D+5.1' when both ends are on one side, 'R+2.1 to D+5.1' when the range crosses zero."""
    f = lambda v: f"{'D' if v >= 0 else 'R'}+{abs(v):.1f}"
    return f"{f(lo)} to {f(hi)}"


def needle_figure(summary: dict, R: float = 15.0, title: str = "", compact: bool = False, wiggle: bool = False):
    """compact=True: phone-sized (no big caption inside the plot; the app shows the headline as text)."""
    import plotly.graph_objects as go

    fig = go.Figure()
    PANEL, INK = "#171c26", "#e8ecf3"          # dark dial face: readable in light and dark app themes
    for (a, b, col) in ((-R, 0, RED), (0, R, BLUE)):
        x, y = arc_polygon(a, b, 0.5, 1.0, R)
        fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="none", fillcolor=col,
                                 opacity=0.38, hoverinfo="skip", showlegend=False))
    # 90% range, lighter
    x, y = arc_polygon(summary["p05"], summary["p95"], 0.5, 1.0, R)
    fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="none", fillcolor="rgba(255,255,255,0.18)",
                             hoverinfo="skip", showlegend=False))
    # 80% range, brighter
    x, y = arc_polygon(summary["p10"], summary["p90"], 0.5, 1.0, R)
    fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="none", fillcolor="rgba(255,255,255,0.5)",
                             hoverinfo="skip", showlegend=False))
    # tick marks every 5 points, longer at the centre (toss-up line)
    for tv in (-10, -5, 0, 5, 10):
        th = float(_theta(tv, R))
        r0 = 0.5 if tv == 0 else 0.93
        fig.add_trace(go.Scatter(x=[r0 * np.cos(th), 1.04 * np.cos(th)], y=[r0 * np.sin(th), 1.04 * np.sin(th)], mode="lines",
                                 line=dict(color="#8a93a6", width=1.5 if tv == 0 else 1), hoverinfo="skip", showlegend=False))
        if tv != 0:
            fig.add_annotation(x=1.14 * np.cos(th), y=1.14 * np.sin(th), showarrow=False, font=dict(color="#8a93a6", size=10),
                               text=f"{'D' if tv > 0 else 'R'}{abs(tv)}")
    nx, ny = needle_segment(summary["median"], R, length=0.97)
    fig.add_trace(go.Scatter(x=nx, y=ny, mode="lines", line=dict(color="#ffffff", width=5),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers", marker=dict(size=15, color="#ffffff", line=dict(color=PANEL, width=3)),
                             hoverinfo="skip", showlegend=False))
    lead = summary["median"]
    who = "Dem" if lead > 0 else "GOP"
    if not compact:
        fig.add_annotation(x=0, y=-0.12, showarrow=False, font=dict(size=22, color=INK),
                           text=f"<b>{who} +{abs(lead):.1f}</b>  ·  Dem win chance {summary['win_prob'] * 100:.0f}%")
    if wiggle:
      try:
        rng = np.random.default_rng(int(abs(summary["median"]) * 1000) % 2**31)
        sd = max((summary["p90"] - summary["p10"]) / 2.563, 0.05)
        frames = []
        for i in range(40):
            v = float(np.clip(summary["median"] + sd * rng.standard_normal(), -R, R))
            wx, wy = needle_segment(v, R)
            frames.append(go.Frame(name=str(i), data=[go.Scatter(x=wx, y=wy)], traces=[len(fig.data) - 2]))
        fig.frames = frames
        fig.update_layout(updatemenus=[dict(type="buttons", showactive=False, x=0.5, xanchor="center", y=-0.02, yanchor="top",
                                            buttons=[dict(label="▶ Play", method="animate",
                                                          args=[None, dict(frame=dict(duration=350, redraw=True), transition=dict(duration=250),
                                                                           fromcurrent=True, mode="immediate")])])])
      except Exception:
        pass   # the wiggle is cosmetic; never break the needle over it
    fig.add_annotation(x=-0.75, y=-0.1 if compact else 0.02, text="GOP", showarrow=False, font=dict(color="#f08a78", size=14))
    fig.add_annotation(x=0.75, y=-0.1 if compact else 0.02, text="Dem", showarrow=False, font=dict(color="#6fb3e8", size=14))
    fig.update_layout(title=title, height=230 if compact else 360,
                      margin=dict(l=4, r=4, t=4 if compact else 40, b=4),
                      dragmode=False, xaxis=dict(visible=False, range=[-1.3, 1.3], fixedrange=True),
                      yaxis=dict(visible=False, range=[-0.2 if compact else -0.25, 1.2 if compact else 1.25], scaleanchor="x", fixedrange=True),
                      plot_bgcolor=PANEL, paper_bgcolor=PANEL)
    return fig


def dr(v: float, d: int = 1) -> str:
    """Margin as D+x / R+x ('Even' at zero). The model keeps the signed number; this is display only."""
    return "Even" if abs(v) < 0.5 * 10 ** -d else f"{'D' if v > 0 else 'R'}+{abs(v):.{d}f}"


def dr_axis(fig, ys) -> None:
    """Label the y axis D+/R+ instead of positive/negative numbers."""
    import math
    ys = [float(v) for v in ys if v is not None and v == v]
    if not ys:
        return
    lo, hi = min(ys + [0.0]), max(ys + [0.0])
    step = 2 if hi - lo <= 14 else 5 if hi - lo <= 40 else 10
    a, b = math.floor(lo / step) * step, math.ceil(hi / step) * step
    vals = list(range(int(a), int(b) + 1, step))
    fig.update_yaxes(tickvals=vals, ticktext=["Even" if v == 0 else f"{'D' if v > 0 else 'R'}{abs(v)}" for v in vals])


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
                      xaxis_title="% of expected vote counted", yaxis_title="Margin (pts)",
                      legend=dict(orientation="h", y=1.15))
    dr_axis(fig, [h["p90"] for h in hist] + [h["p10"] for h in hist] + [h["median"] for h in hist] + ([true_margin] if true_margin is not None else []))
    return fig


def poll_figure(pa: dict):
    """Polling-average trend: dots = individual polls (size = weight), line = our average, band = 80% range."""
    import plotly.graph_objects as go

    ser = pa["series"]
    x = [d["date"] for d in ser]
    fig = go.Figure()
    if ser:
        fig.add_trace(go.Scatter(x=x, y=[d["hi"] for d in ser], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x, y=[d["lo"] for d in ser], mode="lines", line=dict(width=0), fill="tonexty",
                                 fillcolor="rgba(100,100,100,0.22)", name="80% range", hoverinfo="skip"))
    pts = pa["points"]
    fig.add_trace(go.Scatter(x=[p["date"] for p in pts], y=[p["margin"] for p in pts], mode="markers", name="Polls",
                             marker=dict(size=[6 + 22 * min(1.0, p["weight"]) for p in pts], color="rgba(60,60,60,0.45)"),
                             text=[f"{p['pollster']} ({p['grade']}) {dr(p['margin'])}" for p in pts], hoverinfo="text"))
    if ser:
        fig.add_trace(go.Scatter(x=x, y=[d["avg"] for d in ser], mode="lines", line=dict(color="black", width=3), name="Our average"))
    fig.add_hline(y=0, line_color="gray", line_dash="dot")
    fig.update_layout(height=280, margin=dict(l=4, r=4, t=10, b=4), yaxis_title="Margin (pts)",
                      legend=dict(orientation="h", y=1.15))
    dr_axis(fig, [d["hi"] for d in ser] + [d["lo"] for d in ser] + [p["margin"] for p in pts])
    return fig
