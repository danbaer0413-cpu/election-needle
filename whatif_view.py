"""What-if: move the national environment and re-run the simulation (instant, runs in the app).

Every race's middle estimate is shifted by (chosen - current environment) points, but only for the share of the vote not yet counted.
The same 20,000-draw simulation as the 'All races together' chart (control.py) is then re-run, with the same shared error. This is a
scenario, not a forecast: it shows what the model's races would do if the national vote landed there. It does NOT refit the model.
"""
from __future__ import annotations

import json
import math

import control

SEAT_CFG = "config/senate_seats.json"
# How much of a national move reaches a race's final margin. The full model absorbs part of it (state polls and the 2024 baseline pull the other
# way): a full re-run at D+9 (+2.6 pts) moved expected Senate seats +1.7, versus +2.2 for a straight shift, so 1.7/2.2 = about 0.75.
BETA = 0.75


def _dr(v, d=1):
    return f"{'D' if v >= 0 else 'R'}+{abs(v):.{d}f}"


def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _seat_stats(c):
    cfg = json.load(open(SEAT_CFG))
    base = int(cfg["holdover_D"]) + int(cfg["safe_D"])
    need = int(cfg.get("majority_D", 51))
    dist = [float(x) for x in c["dist"]]
    p_ctl = sum(p for w, p in enumerate(dist) if base + w >= need)
    exp = base + float(c["expected_dem_wins"])
    top = max(range(len(dist)), key=lambda i: dist[i])
    return dict(base=base, need=need, p_ctl=p_ctl, exp=exp, top=base + top, dist=dist)


def render(st, ready, label, rating_text, national=None):
    try:
        import plotly.graph_objects as go
        from charts import BLUE, RED, fmt_range  # noqa: F401
        if not national or "median" not in national:
            import national_env
            national = national_env.estimate({})
        base_env = float(national["median"])
        st.markdown("**What if the national environment is different?** Move the slider and the simulation re-runs on the spot.")
        base_pt = round(base_env, 1)
        opts = sorted({round(x * 0.5, 1) for x in range(-8, 31)} | {base_pt})     # R+4 ... D+15 in half points, plus the model's own value
        start = base_pt
        pick = st.select_slider("National environment (Dem minus GOP)", options=opts, value=start,
                                format_func=lambda v: _dr(v), key="whatif_env")
        delta = float(pick) - base_pt
        eff = BETA * delta                                           # what actually reaches the races
        c0 = control.simulate(ready, shift=0.0)
        c1 = control.simulate(ready, shift=eff)
        if "senate" not in c1:
            st.info("No Senate races to simulate yet.")
            return
        a, b = _seat_stats(c0["senate"]), _seat_stats(c1["senate"])
        if abs(delta) < 0.05:
            st.caption(f"This is the model's current environment ({_dr(base_pt)}). Slide it to see a scenario.")
        else:
            st.markdown(f"**{_dr(pick)}** instead of the model's {_dr(base_pt)}: races still to be counted move "
                        f"about **{abs(eff):.1f} pts toward {'Democrats' if delta > 0 else 'Republicans'}**.")
        m1, m2, m3 = st.columns(3)
        m1.metric("Dem chance of Senate control (51+)", f"{b['p_ctl'] * 100:.0f}%", f"{(b['p_ctl'] - a['p_ctl']) * 100:+.0f} pts vs model" if abs(delta) >= 0.05 else None)
        m2.metric("Expected Dem seats", f"{b['exp']:.1f}", f"{b['exp'] - a['exp']:+.1f}" if abs(delta) >= 0.05 else None)
        m3.metric("Most likely Dem seats", f"{b['top']}")
        xs = [b["base"] + i for i in range(len(b["dist"]))]
        cols = [BLUE if x >= b["need"] else RED for x in xs]
        fig = go.Figure(go.Bar(x=xs, y=[d * 100 for d in b["dist"]], marker_color=cols, name="This scenario"))
        if abs(delta) >= 0.05:
            fig.add_trace(go.Scatter(x=[b["base"] + i for i in range(len(a["dist"]))], y=[d * 100 for d in a["dist"]], mode="lines",
                                     line=dict(color="white", width=2, dash="dot"), name="Model now"))
        fig.update_layout(height=230, margin=dict(l=4, r=4, t=4, b=4), xaxis_title="Democratic Senate seats (51 = control)",
                          yaxis_title="% chance", dragmode=False, legend=dict(orientation="h", y=1.12),
                          xaxis=dict(fixedrange=True), yaxis=dict(fixedrange=True))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False})
        # races whose rating word changes
        rows = []
        for rid in c1["senate"]["races"]:
            s = ready[rid]["summary"]
            sd = max((float(s["p90"]) - float(s["p10"])) / (2 * control.Z80), 0.05)
            sh = eff * (1.0 - min(max(float(s.get("pct_in") or 0), 0.0), 100.0) / 100.0)
            p0, p1 = _phi(float(s["median"]) / sd) * 100, _phi((float(s["median"]) + sh) / sd) * 100
            w0, w1 = rating_text(p0), rating_text(p1)
            if w0 != w1:
                rows.append(f"- {label(ready[rid])}: {w0} → **{w1}**")
        if rows and abs(delta) >= 0.05:
            st.markdown("**Races that change rating:**\n" + "\n".join(rows))
        elif abs(delta) >= 0.05:
            st.caption("No Senate race changes its rating word at this setting.")
        g0, g1 = c0.get("governor"), c1.get("governor")
        if g0 and g1 and abs(delta) >= 0.05:
            st.caption(f"Governors: Democrats expected to win {g1['expected_dem_wins']:.1f} of {g1['n']} (model now {g0['expected_dem_wins']:.1f}).")
        st.caption("A scenario, not a forecast. About 75% of a national move reaches each race (checked against a full model re-run at D+9), "
                   "the same simulation is re-run with the same shared error, and the polls are not refit. Counted votes do not move.")
    except Exception as ex:
        import traceback
        st.info(f"The what-if tool is not available yet ({type(ex).__name__}: {str(ex)[:140]}).")
        st.code(traceback.format_exc()[-900:])
