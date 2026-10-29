"""Election Needle - simple, phone-friendly app. Pick a race, read the needle.
Run:  streamlit run app.py        (all model controls, replay demo and your own CSVs: streamlit run app_advanced.py)"""
import json
import time
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

from charts import BLUE, RED, history_figure, needle_figure, poll_figure, fmt_range
from maps import LEGEND, county_map_figure, load_geo, us_map_figure
try:                                     # newer maps.py only; an older copy must not take the whole app down
    from maps import district_map_figure, load_ak_geo
except ImportError:
    district_map_figure = None

    def load_ak_geo():
        return None
from explain import behind_lines, performance_line, drivers_lines, firewall_lines, inputs_lines, outcome_lines
import changes
from publish import from_json_summary, read_log
from states import STATES

st.set_page_config(page_title="Election Needle", page_icon="🗳️", layout="centered", initial_sidebar_state="collapsed")

st.markdown(f"""
<style>
.block-container {{ padding: 0.8rem 0.9rem 3rem; max-width: 720px; }}
[data-testid="stSidebar"], [data-testid="collapsedControl"] {{ display: none; }}
h1 {{ font-size: 1.5rem !important; padding: 0 0 .3rem; }}
.card {{ border: 1px solid rgba(128,128,128,.35); border-radius: 14px; padding: .9rem 1rem; margin: .4rem 0 .6rem; }}
.card .race {{ font-size: .95rem; opacity: .75; }}
.card .lead {{ font-size: 1.55rem; font-weight: 700; line-height: 1.25; margin: .15rem 0 .5rem; }}
.bar {{ display: flex; height: 34px; border-radius: 9px; overflow: hidden; font-weight: 700; color: #fff; font-size: .95rem; }}
.bar div {{ display: flex; align-items: center; padding: 0 .6rem; white-space: nowrap; }}
.chips {{ display: flex; gap: .4rem; flex-wrap: wrap; margin-top: .6rem; }}
.chip {{ font-size: .8rem; padding: .15rem .55rem; border-radius: 999px; border: 1px solid rgba(128,128,128,.4); opacity: .9; }}
div[data-testid="stSelectbox"] label p {{ font-weight: 600; }}
</style>""", unsafe_allow_html=True)

st.title("🗳️ Election Needle")
st.caption("Unofficial, experimental model. Statistical projections, not results or race calls. "
           "Check official state sites and news organizations for calls.")


@st.cache_data(ttl=30)
def load_latest(url: str):
    if url:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    with open("data/latest.json") as fh:
        return json.load(fh)


def state_name(code):
    return STATES.get(code, (code,))[0]


def label(item):
    m = item["meta"]
    kind = "Governor" if "overnor" in str(m.get("race")) else "Senate"
    special = " (special)" if "special" in str(m.get("race")).lower() else ""
    return f"{state_name(m.get('state'))} · {kind}{special}"


def ago(ts):
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        mins = int((datetime.now(timezone.utc) - t).total_seconds() // 60)
        return "just now" if mins < 1 else f"{mins} min ago" if mins < 90 else f"{mins // 60} hr ago" if mins < 2880 else f"{mins // 1440} days ago"
    except Exception:
        return str(ts)


# settings live at the bottom, collapsed; read them first from session state
src = st.session_state.get("src", "")
auto = st.session_state.get("auto", True)
every = int(st.session_state.get("every", 60))

try:
    data = load_latest(src.strip())
except Exception as ex:
    st.warning(f"No published data yet ({ex}). It appears after the first GitHub update run.")
    st.stop()
ready = {k: v for k, v in data["races"].items() if v.get("summary")}
if not ready:
    st.warning("Nothing to show yet - the first update has not produced any needles.")
    st.stop()


# ---------------------------------------------------------------- "what changed" screen (once per visit)
log_src = src.strip().replace("latest.json", "needle_log.csv") if src.strip() else "data/needle_log.csv"
if st.session_state.get("flash_on", True) and not st.session_state.get("flash_done"):
    st.markdown("### What's changed")
    _win = st.radio("Compare with", list(changes.WINDOWS), horizontal=True, key="flash_win", label_visibility="collapsed")
    try:
        chg, ref = changes.compute(changes.read(log_src), ready, changes.WINDOWS[_win])
    except Exception:
        chg, ref = changes.compute(pd.DataFrame(), ready)
    st.session_state["prev_medians"] = {} if chg.empty else dict(zip(chg["id"], chg["prev_median"]))
    if chg.empty:
        st.info("Nothing to compare yet. This is the first update.")
    else:
        moved = chg[chg["d_median"].abs() >= 0.05]
        st.caption(f"Compared with the update from {ago(ref.isoformat())}. Margins are Dem minus GOP; the needle is the middle estimate.")
        if moved.empty:
            st.info("No race has moved since then.")
        for r in moved.head(8).itertuples():
            col = "blue" if r.d_median > 0 else "red"
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{label(ready[r.id])}**  \n:{col}[{changes.arrow(r.d_median)} {abs(r.d_median):.1f} pts] · "
                        f"{changes.margin_text(r.prev_median)} → {changes.margin_text(r.median)} · "
                        f"{changes.rating_text(r.prev_win)} → {changes.rating_text(r.win)}")
            if c2.button("See needle", key=f"fl_{r.id}"):
                st.session_state["flash_done"] = True
                st.query_params["race"] = r.id
                st.rerun()
        if len(moved) > 8:
            st.caption(f"{len(moved) - 8} more races moved by less. Pick any race after you continue.")
        if len(chg) > len(moved):
            st.caption(f"{len(chg) - len(moved)} races did not move.")
    if st.button("Continue", type="primary"):
        st.session_state["flash_done"] = True
        st.rerun()
    st.stop()

# ---------------------------------------------------------------- map view
view = st.radio("View", ["Race", "Map", "Senate", "House"], horizontal=True, label_visibility="collapsed", key="view")
if view == "Senate":
    try:
        import senate_view
        senate_view.render(st, ready, label, changes.rating_text)
    except Exception as _ex:
        st.info(f"The Senate view is not available yet ({str(_ex)[:160]}).")
    st.stop()
if view == "House":
    try:
        import house_view
        house_view.render(st)
    except Exception as _ex:
        st.info(f"The House view is not available yet ({str(_ex)[:120]}).")
    st.stop()
if view == "Map":
    try:
        cdf = pd.read_csv("config/candidates.csv")
        cand = {r.id: (r.dem, r.rep) for r in cdf.itertuples()}
    except Exception:
        cand = {}
    kind = st.radio("Race type", ["Senate", "Governor"], horizontal=True, key="mapkind")
    names = {k: v[0] for k, v in STATES.items()}
    try:
        st.plotly_chart(us_map_figure(ready, kind.lower(), cand, names), use_container_width=True, config={"displayModeBar": False})
    except Exception as _e:
        import traceback
        st.warning(f"US map could not be drawn: {type(_e).__name__}: {_e}")
        st.code(traceback.format_exc()[-1500:])
    st.markdown("".join(f'<span class="chip" style="border-left:12px solid {c}">{l}</span> ' for l, c in LEGEND), unsafe_allow_html=True)
    st.caption("Colors are the model's projection, not race calls. Pale = nothing counted yet (pre-election forecast); solid = votes are in. "
               "Tap a state for details.")
    kind_ids = [k for k in ready if k.endswith("-" + kind.lower())]
    if kind_ids:
        pick = st.selectbox("County map for", sorted(kind_ids, key=lambda k: state_name(ready[k]["meta"].get("state"))),
                            format_func=lambda k: label(ready[k]), key="mapraces")
        geo, fx = load_geo()
        st_code = pick.split("-")[0]
        if geo is None:
            st.info("County outlines are not built yet. Run the build-geo workflow on GitHub once.")
        elif st_code == "AK":
            _ak = load_ak_geo()
            if district_map_figure is None:
                st.info("The Alaska district map needs the newest maps.py. Upload it and reload.")
            elif _ak is None:
                st.info("Alaska reports by state House election district. Run the build-ak-geo workflow on GitHub once to draw them.")
            else:
                _bub = st.toggle("Show bubbles", value=True, key="bubbles_ak")
                _by = st.radio("Bubble size", ["Votes left to count", "Early ballots returned"], horizontal=True, key="bubble_by_ak",
                               label_visibility="collapsed") if _bub else "Votes left to count"
                _bcol = "early_returned" if _by.startswith("Early") else "remaining"
                try:
                    st.plotly_chart(district_map_figure(ready[pick]["summary"], _ak, bubbles=_bub, bubble_by=_bcol), use_container_width=True,
                                    config={"displayModeBar": False})
                except Exception as _e:
                    st.warning(f"Alaska map could not be drawn: {type(_e).__name__}: {_e}")
                st.caption("Alaska reports by state House election district. Districts are colored by projected final margin; pale ones have under 5% counted. "
                           "Bubble area = votes still to count. Hover or tap a district for votes counted and left.")
        else:
            _bub = st.toggle("Show bubbles", value=True, key="bubbles")
            _by = st.radio("Bubble size", ["Votes left to count", "Early ballots returned"], horizontal=True, key="bubble_by",
                           label_visibility="collapsed") if _bub else "Votes left to count"
            _bcol = "early_returned" if _by.startswith("Early") else "remaining"
            _color_by = st.radio("Color counties by", ["Projected margin", "Over/under-performance"], horizontal=True, key="color_by",
                                 help="Over/under-performance: blue = the count there is running more Democratic than expected, red = more Republican. Grey until votes are in.")
            try:
                st.plotly_chart(county_map_figure(ready[pick]["summary"], st_code, geo, fx, bubbles=_bub, bubble_by=_bcol,
                                                  color_by="perf" if _color_by.startswith("Over") else "margin"), use_container_width=True,
                                config={"displayModeBar": False})
            except Exception as _e:
                import traceback
                st.warning(f"County map could not be drawn: {type(_e).__name__}: {_e}")
                st.code(traceback.format_exc()[-1500:])
            _tb = pd.DataFrame(ready[pick]["summary"]["table"])
            _big = float(_tb["remaining"].max()) if "remaining" in _tb and len(_tb) else 0.0
            st.caption("Counties are colored by projected final margin. Pale counties have under 5% counted. "
                       + (f"Bubble area = {'early ballots returned' if _bcol == 'early_returned' else 'votes still to count'}. " if _bub and _big > 0 else "")
                       + "Hover or tap a county or bubble for votes counted and left.")
    st.stop()

order = sorted(ready, key=lambda k: (state_name(ready[k]["meta"].get("state")), label(ready[k])))
want = st.query_params.get("race")
idx = order.index(want) if want in order else 0
rid = st.selectbox("Choose a race", order, index=idx, format_func=lambda k: label(ready[k]))
if st.query_params.get("race") != rid:
    st.query_params["race"] = rid               # bookmark / share a link straight to this race
item = ready[rid]
s = from_json_summary(item["summary"])

# ---------------------------------------------------------------- headline card
dem = float(s["win_prob"]) * 100
gop = 100 - dem
lead = float(s["median"])
who = "Democrat" if lead > 0 else "Republican"
verdict = changes.rating_text(dem)
counted = float(s["pct_in"])
chips = [f"{counted:.0f}% of vote counted" if counted > 0 else "Polls open Nov 3 - pre-election estimate",
         f"Likely range (80%): {fmt_range(float(s['p10']), float(s['p90']))}",
         f"Middle estimate {'D' if lead > 0 else 'R'}+{abs(lead):.1f}",
         f"Updated {ago(item.get('as_of') or item.get('checked'))}"]
_pm = st.session_state.get("prev_medians", {}).get(rid)
if _pm is not None and abs(lead - _pm) >= 0.05:
    chips.insert(0, f"{'▲' if lead > _pm else '▼'} {abs(lead - _pm):.1f} pts toward {'Dem' if lead > _pm else 'GOP'} since the last update")
st.markdown(f"""
<div class="card">
  <div class="race">{label(item)}</div>
  <div class="lead">{verdict}</div>
  <div style="font-size:1.35rem;font-weight:700;margin:.15rem 0 .4rem 0">{fmt_range(float(s['p10']), float(s['p90']))}
    <span style="font-size:.8rem;font-weight:400;opacity:.7">likely range (80%)</span></div>
  <div class="bar">
    <div style="background:{BLUE};width:{max(dem, 8):.1f}%">Dem</div>
    <div style="background:{RED};width:{max(gop, 8):.1f}%;justify-content:flex-end">GOP</div>
  </div>
  <div class="chips">{''.join(f'<span class="chip">{c}</span>' for c in chips)}</div>
</div>""", unsafe_allow_html=True)
if item.get("status") != "ok":
    st.warning("The latest refresh for this race failed, so these are the last good numbers.")

# ---------------------------------------------------------------- needle
wiggle = st.toggle("Show the needle moving through its range", value=False,
                   help="Replays the needle at random points inside today's range, the way a live needle jitters. It is not live data.")
_ph = st.empty()
_shown = st.session_state.setdefault("shown", {})
_start = _shown.get(rid, st.session_state.get("prev_medians", {}).get(rid))
_end = float(s["median"])
if st.session_state.get("anim_on", True) and not wiggle and _start is not None and abs(_start - _end) >= 0.05:
    try:        # sweep from where the needle was to where it is now
        for _i, _v in enumerate(changes.sweep(float(_start), _end)):
            _ph.plotly_chart(needle_figure({**s, "median": _v}, compact=True), use_container_width=True,
                             config={"displayModeBar": False}, key=f"needle_{rid}_{_i}")
            time.sleep(0.05)
    except Exception:
        pass        # the sweep is cosmetic
_shown[rid] = _end
_ph.plotly_chart(needle_figure(s, compact=True, wiggle=wiggle), use_container_width=True, config={"displayModeBar": False}, key=f"needle_{rid}_final")
st.caption("Needle = middle estimate. Dark band: 80% range (the headline range). Light band: 90% range. Margins are Dem minus GOP. "
           "As votes are counted the bands narrow and the needle moves to where the model now expects the race to land.")
_perf = performance_line(s)
if _perf:
    st.info(_perf)
for line in outcome_lines(s)[:2]:
    st.info(line)


# ---------------------------------------------------------------- all races together
_ctl = (data or {}).get("control") or {}
if _ctl:
    with st.expander("All races together (Senate and governor counts)", expanded=False):
        import plotly.graph_objects as go
        for key, title in (("senate", "Senate races on this site"), ("governor", "Governor races on this site")):
            c_ = _ctl.get(key)
            if not c_:
                continue
            st.markdown(f"**{title}** ({c_['n']} races): Democrats expected to win **{c_['expected_dem_wins']:.1f}**; "
                        f"chance of winning more than half **{c_['p_dem_majority'] * 100:.0f}%**, Republicans **{c_['p_rep_majority'] * 100:.0f}%**.")
            fig_ = go.Figure(go.Bar(x=list(range(c_["n"] + 1)), y=[d * 100 for d in c_["dist"]],
                                    marker_color=[BLUE if i > c_["n"] / 2 else RED if i < c_["n"] / 2 else "gray" for i in range(c_["n"] + 1)]))
            fig_.update_layout(height=200, margin=dict(l=4, r=4, t=4, b=4), xaxis_title="Democratic wins", yaxis_title="% chance")
            st.plotly_chart(fig_, use_container_width=True, config={"displayModeBar": False})
        st.caption("Races share part of their error, so a miss in one place tends to hit everywhere. Counts only the races listed here, "
                   "not full chamber control (no holdover seats or races outside these 16 states).")

# ---------------------------------------------------------------- detail panels (collapsed by default)
try:
    with open("data/poll_average.json") as _fh:
        _pa0 = json.load(_fh).get(rid)
except Exception:
    _pa0 = None
_pa_avg = _pa0.get("avg") if _pa0 else None
with st.expander("What's behind this number", expanded=True):
    for line in behind_lines(s, pa_avg=_pa_avg):
        st.markdown(line)
with st.expander("What's moving the needle", expanded=False):
    for line in drivers_lines(s):
        st.markdown(line)
    st.markdown("**Which counties decide it**")
    for line in firewall_lines(s):
        st.markdown(line)
try:
    with open("data/poll_average.json") as fh:
        pa = json.load(fh).get(rid)
except Exception:
    pa = None
if pa and pa.get("points"):
    with st.expander(f"Polling average: {'D' if pa['avg'] > 0 else 'R'}+{abs(pa['avg']):.1f}  ({pa['n_polls']} polls)"):
        st.plotly_chart(poll_figure(pa), use_container_width=True, config={"displayModeBar": False})
        if len(pa["series"]) < 2:
            st.caption("Too few polls for a trend line yet - showing the individual polls only.")
        st.caption(f"Our own average of every poll we collect: weighted by pollster grade, sample size and recency, "
                   f"adjusted for pollsters' usual lean. Dots are single polls (bigger = more weight). "
                   f"80% range {fmt_range(float(pa['lo']), float(pa['hi']))}. D+ = Democratic lead, R+ = Republican lead.")
        rec = sorted(pa["points"], key=lambda p: p["date"], reverse=True)[:10]
        st.dataframe(pd.DataFrame(rec)[["date", "pollster", "grade", "margin"]], use_container_width=True, hide_index=True)
with st.expander("What's been inputted"):
    for line in inputs_lines(s):
        st.markdown(line)
hist = read_log(log_src, rid)
if len(hist) > 1:
    with st.expander("How the projection has moved"):
        st.plotly_chart(history_figure(hist), use_container_width=True, config={"displayModeBar": False})
with st.expander("County / unit table"):
    t = s["table"].sort_values("remaining", ascending=False).copy()
    _dr = lambda x: "-" if x != x else ("Even" if abs(x) < 0.05 else f"{'D' if x > 0 else 'R'}+{abs(x):.1f}")
    _has = t["counted"] > 0 if "counted" in t else None
    for _c in ("proj_margin", "base_margin"):
        if _c in t:
            t[_c] = t[_c].astype(float).map(_dr)
    for _c in ("counted_margin", "vs_expected", "vs_state"):
        if _c in t:
            t[_c] = [(_dr(v) if h else "-") for v, h in zip(t[_c].astype(float), _has)]
    t = t.rename(columns={"proj_margin": "Projected final", "base_margin": "Baseline", "counted_margin": "Counted so far",
                          "vs_expected": "vs expected", "vs_state": "vs rest of state"})
    st.dataframe(t, use_container_width=True, hide_index=True,
                 column_config={"pct_in": st.column_config.ProgressColumn("% in", min_value=0, max_value=100, format="%.0f%%")})
    st.caption("Margins read D+ for a Democratic lead and R+ for a Republican lead. 'vs expected' and 'vs rest of state' show how far a county is running "
               "from what the model expected (D+ = bluer, R+ = redder), once it has votes counted.")

# ---------------------------------------------------------------- tucked-away settings
with st.expander("Settings"):
    st.checkbox("Auto-refresh", value=auto, key="auto")
    st.checkbox("Show the 'what changed' screen when the app opens", value=True, key="flash_on")
    st.checkbox("Sweep the needle from its previous position", value=True, key="anim_on")
    st.number_input("Refresh every (seconds)", 30, 600, every, key="every")
    st.text_input("Data URL (leave blank for the built-in data)", src, key="src",
                  help="Raw URL of latest.json on GitHub, if the app is hosted away from the repo.")
    waiting = {k: v for k, v in data["races"].items() if not v.get("summary")}
    if waiting:
        st.caption("No needle yet: " + "; ".join(f"{k} ({v.get('status') or 'no data'})" for k, v in waiting.items()))
    st.caption("Want every model control, a practice replay, or your own CSVs? Run `streamlit run app_advanced.py`.")

if auto:
    time.sleep(every)
    st.rerun()
