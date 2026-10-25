"""Election Needle - simple, phone-friendly app. Pick a race, read the needle.
Run:  streamlit run app.py        (all model controls, replay demo and your own CSVs: streamlit run app_advanced.py)"""
import json
import time
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

from charts import BLUE, RED, history_figure, needle_figure, poll_figure
from explain import drivers_lines, firewall_lines, inputs_lines, outcome_lines
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
edge = abs(dem - 50)
verdict = "Toss-up" if edge <= 5 else f"{'Leans' if edge <= 20 else 'Likely' if edge <= 40 else 'Solid'} {who}"
counted = float(s["pct_in"])
chips = [f"{counted:.0f}% of vote counted" if counted > 0 else "Polls open Nov 3 - pre-election estimate",
         f"Projected margin {'D' if lead > 0 else 'R'}+{abs(lead):.1f}",
         f"Updated {ago(item.get('as_of') or item.get('checked'))}"]
st.markdown(f"""
<div class="card">
  <div class="race">{label(item)}</div>
  <div class="lead">{verdict}</div>
  <div class="bar">
    <div style="background:{BLUE};width:{max(dem, 8):.1f}%">Dem {dem:.0f}%</div>
    <div style="background:{RED};width:{max(gop, 8):.1f}%;justify-content:flex-end">GOP {gop:.0f}%</div>
  </div>
  <div class="chips">{''.join(f'<span class="chip">{c}</span>' for c in chips)}</div>
</div>""", unsafe_allow_html=True)
if item.get("status") != "ok":
    st.warning("The latest refresh for this race failed, so these are the last good numbers.")

# ---------------------------------------------------------------- needle
st.plotly_chart(needle_figure(s, compact=True), use_container_width=True, config={"displayModeBar": False})
st.caption("Needle = projected margin. Dark band: 80% range. Light band: 90% range. Margins are Dem minus GOP.")
for line in outcome_lines(s)[:2]:
    st.info(line)

# ---------------------------------------------------------------- detail panels (collapsed by default)
with st.expander("What's moving the needle", expanded=True):
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
if pa and len(pa["series"]) > 1:
    with st.expander(f"Polling average: {'D' if pa['avg'] > 0 else 'R'}+{abs(pa['avg']):.1f}  ({pa['n_polls']} polls)"):
        st.plotly_chart(poll_figure(pa), use_container_width=True, config={"displayModeBar": False})
        st.caption(f"Our own average of every poll we collect: weighted by pollster grade, sample size and recency, "
                   f"adjusted for pollsters' usual lean. Dots are single polls (bigger = more weight). "
                   f"80% range {pa['lo']:+.1f} to {pa['hi']:+.1f}. Margins are Dem minus GOP.")
        rec = sorted(pa["points"], key=lambda p: p["date"], reverse=True)[:10]
        st.dataframe(pd.DataFrame(rec)[["date", "pollster", "grade", "margin"]], use_container_width=True, hide_index=True)
with st.expander("What's been inputted"):
    for line in inputs_lines(s):
        st.markdown(line)
log_src = src.strip().replace("latest.json", "needle_log.csv") if src.strip() else "data/needle_log.csv"
hist = read_log(log_src, rid)
if len(hist) > 1:
    with st.expander("How the projection has moved"):
        st.plotly_chart(history_figure(hist), use_container_width=True, config={"displayModeBar": False})
with st.expander("County / unit table"):
    t = s["table"].sort_values("remaining", ascending=False)
    st.dataframe(t, use_container_width=True, hide_index=True,
                 column_config={"pct_in": st.column_config.ProgressColumn("% in", min_value=0, max_value=100, format="%.0f%%")})

# ---------------------------------------------------------------- tucked-away settings
with st.expander("Settings"):
    st.checkbox("Auto-refresh", value=auto, key="auto")
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
