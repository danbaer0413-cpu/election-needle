"""Senate screen: a parliament-style seat chart (blue left, red right, grey undecided) and a slider, like the House screen.
66 seats are not in play at all (holdover or safe); the 15 races we model fill in by win chance and, on election night, by calls typed into data/senate_called.csv.
Everything comes from the race summaries already loaded by the app plus config/senate_seats.json."""
from __future__ import annotations
import csv
import json
import os
import house_lean as hl
from house_view import D_COL, R_COL, NEUTRAL

LEVELS = ["Called winners", "Likely winners", "Leaning winners", "Projected (all seats)"]
THRESH = [None, 0.80, 0.65, 0.55]          # win chance needed to show a race at each slider level
CFG = "config/senate_seats.json"
CALLED = "data/senate_called.csv"


def load_cfg(path: str = CFG) -> dict:
    return json.load(open(path))


def load_called(path: str = CALLED) -> dict:
    out = {}
    if os.path.exists(path):
        for r in csv.DictReader(open(path, newline="")):
            w = (r.get("winner") or "").strip().upper()[:1]
            if r.get("race") and w in ("D", "R"):
                out[r["race"].strip()] = w
    if os.path.exists("data/auto_calls.csv"):                 # automated calls (two sources agreed); typed calls above always win
        for r in csv.DictReader(open("data/auto_calls.csv", newline="")):
            if r.get("kind") == "senate" and r.get("winner") in ("D", "R"):
                out.setdefault(r["race"].strip(), r["winner"])
    return out


def strength(p: float) -> int:
    """1 solid .. 4 tilt, from the winner's win chance."""
    return 1 if p >= 0.95 else 2 if p >= 0.80 else 3 if p >= 0.65 else 4


def build(ready: dict, level: int, cfg: dict | None = None, called: dict | None = None) -> dict:
    cfg = cfg or load_cfg()
    called = load_called() if called is None else called
    ds = [(0, True)] * (cfg["holdover_D"] + cfg["safe_D"])
    rs = [(0, True)] * (cfg["holdover_R"] + cfg["safe_R"])
    und, races = 0, []
    for rid in cfg["contested"]:
        item = ready.get(rid)
        p = float(item["summary"]["win_prob"]) if item else 0.5
        med = float(item["summary"]["median"]) if item else 0.0
        w = called.get(rid)
        shown = None
        if w:
            shown = (w, 0, True)
        elif level >= 1 and item and max(p, 1 - p) >= THRESH[level]:
            shown = ("D" if p > 0.5 else "R", strength(max(p, 1 - p)), False)
        races.append({"id": rid, "p": p, "median": med, "shown": shown[0] if shown else None, "called": bool(w)})
        if shown is None:
            und += 1
        elif shown[0] == "D":
            ds.append((shown[1], shown[2]))
        else:
            rs.append((shown[1], shown[2]))
    ds.sort(key=lambda t: (not t[1], t[0]))
    rs.sort(key=lambda t: (not t[1], t[0]), reverse=True)
    d, r = len(ds), len(rs)
    ctrl = "D" if d >= cfg["majority_D"] else "R" if r >= cfg["majority_R"] else None
    return {"D": d, "R": r, "U": und, "ds": ds, "rs": rs, "races": races, "control": ctrl,
            "maj_D": cfg["majority_D"], "maj_R": cfg["majority_R"]}


def headline(b: dict) -> str:
    if b["control"] == "D":
        return f"Democrats have {b['D']} seats, enough for control ({b['maj_D']} needed)."
    if b["control"] == "R":
        return f"Republicans have {b['R']} seats, enough for control ({b['maj_R']} needed, since the Vice President breaks ties)."
    need_d = b["maj_D"] - b["D"]
    need_r = b["maj_R"] - b["R"]
    return (f"Democrats {b['D']}, Republicans {b['R']}, {b['U']} undecided. Democrats need {need_d} more for control; "
            f"Republicans need {need_r} more.")


def seat_figure(b: dict):
    import plotly.graph_objects as go
    seats = ([(D_COL[0 if c else min(s, 4)]) for s, c in b["ds"]] + [NEUTRAL] * b["U"]
             + [(R_COL[0 if c else min(s, 4)]) for s, c in b["rs"]])
    xy = hl.parliament_xy(len(seats), rows=5)
    fig = go.Figure(go.Scatter(x=[a for a, _ in xy], y=[c for _, c in xy], mode="markers", hoverinfo="skip", showlegend=False,
                               marker=dict(size=15, color=seats, line=dict(width=0.6, color="#777"))))
    fig.add_shape(type="line", x0=0, x1=0, y0=0, y1=1.08, line=dict(color="#888", width=1, dash="dot"))
    fig.add_annotation(x=0, y=1.14, text="Control: D 51 · R 50 (VP breaks ties)", showarrow=False, font=dict(size=11, color="#888"))
    fig.add_annotation(x=0, y=0.12, text=f"<b>D {b['D']} – R {b['R']}</b>", showarrow=False, font=dict(size=22))
    fig.add_annotation(x=0, y=-0.02, text=f"{b['U']} undecided", showarrow=False, font=dict(size=12, color="#888"))
    fig.update_xaxes(visible=False, range=[-1.1, 1.1]); fig.update_yaxes(visible=False, range=[-0.12, 1.22], scaleanchor="x")
    fig.update_layout(height=340, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def render(st, ready: dict, label_fn, rating_fn):
    try:
        cfg = load_cfg()
    except Exception:
        st.info("The Senate view needs config/senate_seats.json.")
        return
    called = load_called()
    st.subheader("U.S. Senate")
    name = st.select_slider("Show", options=LEVELS, value=LEVELS[0] if called else LEVELS[3], key="senate_level",
                            help="Called winners: only races you typed into data/senate_called.csv. Likely: 80%+ win chance. "
                                 "Leaning: 65%+. Projected: 55%+. Anything closer stays grey.")
    b = build(ready, LEVELS.index(name), cfg, called)
    st.markdown(f"**{headline(b)}**")
    st.plotly_chart(seat_figure(b), use_container_width=True, config={"displayModeBar": False})
    c1, c2, c3 = st.columns(3)
    c1.metric("Democrats", b["D"]); c2.metric("Republicans", b["R"]); c3.metric("Undecided", b["U"])
    import pandas as pd
    rows = []
    for r in b["races"]:
        it = ready.get(r["id"])
        if not it:
            continue
        rows.append({"Race": label_fn(it), "Rating": rating_fn(r["p"] * 100), "Middle estimate": f"{'D' if r['median'] > 0 else 'R'}+{abs(r['median']):.1f}",
                     "Called": r["called"] and (called.get(r["id"]) or "") or ""})
    with st.expander("The 15 races in play", expanded=True):
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"{cfg['holdover_D'] + cfg['holdover_R']} seats are not up this year and {cfg['safe_D'] + cfg['safe_R']} are up but not in play "
               f"(safe D: {cfg['safe_D_states']}; safe R: {cfg['safe_R_states']}), so they show as solid. The 15 races we model fill in by win chance, "
               "and turn solid when you add a call to data/senate_called.csv. Nebraska shows as Democratic if independent Dan Osborn wins, though he has not committed to a caucus. "
               "Democrats' 47 includes independents Sanders and King.")
