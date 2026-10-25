"""Election needle - Streamlit app.   Run:  streamlit run app.py"""
import os
import time

import pandas as pd
import streamlit as st

from charts import history_figure, needle_figure
from feeds import fetch_table, to_results
from model import Params, project
from poll_error import estimate, params_for
from explain import drivers_lines, firewall_lines, inputs_lines, outcome_lines
from rcv import estimate_transfers
from states import LEVELS, PRESETS, RULES, STATES, race_dir, races_for
from synthetic import make_scenario

st.set_page_config(page_title="Election Needle", layout="wide")

# ---------------------------------------------------------------- race picker
st.sidebar.subheader("Race")
abbr = st.sidebar.selectbox("State", list(STATES), format_func=lambda a: f"{STATES[a][0]} ({a})")
level = st.sidebar.radio("Level", LEVELS, horizontal=True)
race = st.sidebar.selectbox("Race", races_for(abbr, level), format_func=lambda r: r["name"])
preset = PRESETS[race["kind"]]
state_name, has_party_reg = STATES[abbr]
folder = race_dir(abbr, race["name"])

st.title(f"Election Needle - {state_name}")
st.subheader(f"{level}: {race['name']}")
st.caption(f"{race['scope']}. Early-vote prior first, then counted returns. Win chance comes from a "
           "Monte Carlo, not a call. Margins are Dem minus GOP, two-party points.")
if has_party_reg:
    st.sidebar.caption("This state records party registration, so early/mail files may carry party.")
else:
    st.sidebar.caption("No party registration here: the early-vote signal uses geography only.")

mode = st.sidebar.radio("Data", ["Latest published (GitHub)", "Replay demo (synthetic)",
                                 "My data (CSV)", "Live feed"])

# ---------------------------------------------------------------- model settings
st.sidebar.subheader("Model settings")
k = race["kind"]  # widget keys change with race kind so presets re-apply
use_poll = st.sidebar.checkbox("Use a polling prior", value=preset["use_poll"], key=f"up_{k}")
poll_in = st.sidebar.number_input("Polling-average margin (D-R)", value=0.0, step=0.5,
                                  disabled=not use_poll, key=f"pm_{k}")
sd_poll = st.sidebar.slider("Polling-error spread (pts)", 1.0, 8.0, preset["sd_poll"], 0.5, key=f"sp_{k}")
poll_bias, poll_skew, sd_poll_eff = 0.0, 0.0, sd_poll
with st.sidebar.expander("Historical poll error"):
    hist_path = "data/poll_error_history.csv"
    hdf = pd.read_csv(hist_path) if os.path.exists(hist_path) else None
    up = st.file_uploader("poll_error_history.csv", type="csv", key="peh")
    if up is not None:
        hdf = pd.read_csv(up)
    if hdf is None:
        st.caption("Columns: state, year, race, poll_margin, actual_margin (D-R, final poll average vs "
                   "result). Put it at data/poll_error_history.csv to auto-load.")
    else:
        try:
            races_all = sorted(hdf["race"].astype(str).unique())
            pick = st.multiselect("Races to include", races_all, default=races_all)
            years_all = sorted(hdf["year"].astype(int).unique())
            yr_pick = st.multiselect("Years to include", years_all, default=years_all,
                                     help="Try midterm years only (2018, 2022, and 2006 if loaded) to see "
                                          "how the midterm electorate polled.")
            sub = hdf[hdf["race"].astype(str).isin(pick) & hdf["year"].astype(int).isin(yr_pick)].copy()
            sub["state"] = sub["state"].astype(str).replace({v[0]: k for k, v in STATES.items()})
            tbl, pooled = estimate(sub)
            pp = params_for(abbr, tbl, pooled)
            row = tbl[tbl["state"] == abbr]
            n_state = int(row["n"].iloc[0]) if len(row) else 0
            apply_hist = st.checkbox("Apply to needle", value=True)
            st.write(f"**{state_name}**: {n_state} past races, shrunk bias {pp['poll_bias']:+.1f} "
                     f"(error = actual - poll; + means polls underestimated Dems), "
                     f"spread {pp['sd_poll']:.1f}")
            st.caption(f"Pooled across states: common-year spread {pooled['sd_cycle']}, "
                       f"skew shape {pooled['alpha']}, {pooled['n_obs']} obs, {pooled['n_cycles']} cycles.")
            if n_state:
                e = sub[sub["state"] == abbr].assign(err=lambda x: x["actual_margin"] - x["poll_margin"])
                st.bar_chart(e.set_index(e["year"].astype(str) + " " + e["race"].astype(str))["err"])
            if apply_hist:
                poll_bias, poll_skew, sd_poll_eff = pp["poll_bias"], pp["poll_skew"], pp["sd_poll"]
        except Exception as ex:
            st.error(f"Could not use history: {ex}")

early_pct_in = st.sidebar.slider("Share of FINAL early/mail vote already returned", 0.3, 1.0, 0.85, 0.01)
early_gap = st.sidebar.slider("Early minus Election Day margin (pts)", 0.0, 20.0, 8.0, 0.5,
                              help="How much more Dem the early/mail vote is than Election Day. "
                                   "Calibrate from the same race last cycle.")
early_first = st.sidebar.checkbox("Reports early/mail votes first", value=True)
loyalty = st.sidebar.slider("Party-reg loyalty", 0.80, 0.98, 0.92, 0.01, disabled=not has_party_reg)
party_bias = st.sidebar.number_input("Early party-signal bias (pts)", value=0.0, step=0.5,
                                     disabled=not has_party_reg,
                                     help="Calibrate on a past cycle so the signal reads ~0 when "
                                          "nothing changed.")
with st.sidebar.expander("Unit noise (advanced)"):
    tau_county = st.slider("County/unit spread (pts)", 1.0, 8.0, preset["tau_county"], 0.5, key=f"tc_{k}")
    tau_region = st.slider("Region spread (pts)", 0.5, 6.0, preset["tau_region"], 0.5, key=f"tr_{k}")
    sigma_nonrep = st.slider("Early-count unrepresentativeness (pts)", 4.0, 25.0, preset["sigma_nonrep"],
                             1.0, key=f"sn_{k}")


rules = RULES.get(abbr, {})
rcv_defaults = (0.5, 0.5)
with st.sidebar.expander("Ballot rules (runoff / ranked-choice)", expanded=bool(rules)):
    runoff_rule = st.checkbox("Majority required (runoff possible)", value=rules.get("runoff_rule", False),
                              key=f"ro_{abbr}")
    runoff_shift = st.slider("Runoff shift toward Dems (pts)", -6.0, 6.0, 0.0, 0.5,
                             disabled=not runoff_rule, key=f"rs_{abbr}")
    runoff_sd = st.slider("Extra runoff uncertainty (pts)", 0.0, 8.0, 3.0, 0.5,
                          disabled=not runoff_rule, key=f"rsd_{abbr}")
    rcv = st.checkbox("Ranked-choice voting", value=rules.get("rcv", False), key=f"rcv_{abbr}")
    third_share = st.slider("Other candidates' share of first-round ballots", 0.0, 0.25,
                            float(rules.get("third_share", 0.0)), 0.005,
                            disabled=not (runoff_rule or rcv), key=f"ts_{abbr}")
    rcv_hist = pd.read_csv("data/rcv_history.csv") if os.path.exists("data/rcv_history.csv") else None
    up_rcv = st.file_uploader("Past ranked-choice contests (CSV)", type="csv", key="rcvh", disabled=not rcv)
    if up_rcv is not None:
        rcv_hist = pd.read_csv(up_rcv)
    if rcv and rcv_hist is not None:
        try:
            _, pr = estimate_transfers(rcv_hist)
            rcv_defaults = (pr["to_d"], pr["to_r"])
            st.caption(f"From {pr['contests']} past contests: {pr['to_d'] * 100:.0f}% of other ballots to D, "
                       f"{pr['to_r'] * 100:.0f}% to R, {pr['exhausted'] * 100:.0f}% exhausted (shrunk toward even).")
        except Exception as ex:
            st.error(f"Could not use ranked-choice history: {ex}")
    rcv_to_d = st.slider("Other ballots ending with D", 0.0, 1.0, float(rcv_defaults[0]), 0.01,
                         disabled=not rcv, key=f"td_{abbr}_{rcv_defaults[0]}")
    rcv_to_r = st.slider("Other ballots ending with R", 0.0, 1.0, float(rcv_defaults[1]), 0.01,
                         disabled=not rcv, key=f"tr_{abbr}_{rcv_defaults[1]}")
    if rcv and rcv_to_d + rcv_to_r > 1.0:
        st.warning("D and R shares add to more than 100%.")


def make_params(poll):
    return Params(poll_margin=poll if use_poll else None, sd_poll=sd_poll_eff, poll_bias=poll_bias,
                  poll_skew=poll_skew, third_share=third_share, rcv=rcv, rcv_to_d=rcv_to_d,
                  rcv_to_r=rcv_to_r, runoff_rule=runoff_rule, runoff_shift=runoff_shift,
                  runoff_sd=runoff_sd, early_gap=early_gap,
                  early_first=early_first, early_final_pct_in=early_pct_in, reg_loyalty=loyalty,
                  party_bias=party_bias, tau_county=tau_county, tau_region=tau_region,
                  sigma_nonrep=sigma_nonrep)


def load_csv(name):
    path = os.path.join(folder, name)
    if os.path.exists(path):
        df = pd.read_csv(path)
        if len(df):
            return df
    return None


def show(summary, hist, true_margin=None):
    c1, c2 = st.columns([3, 2])
    with c1:
        st.plotly_chart(needle_figure(summary), use_container_width=True)
        st.caption("Dark band = 80% range, light band = 90% range.")
    with c2:
        st.metric("Counted so far", f"{summary['pct_in']:.1f}% of expected vote")
        st.metric("Baseline margin", f"{summary['baseline_margin']:+.1f}")
        st.metric("Estimated swing vs baseline", f"{summary['swing']:+.1f}  (±{summary['swing_sd']:.1f})")
        sig = summary["signals"]
        rows = {"Polls": sig["poll_swing"], "Early party reg": sig["early_party"],
                "Early geography": sig["early_geo"]}
        st.write("**Early signals (swing, pts)**")
        st.table(pd.DataFrame({"signal": list(rows), "swing": [None if v is None else round(v, 2)
                                                               for v in rows.values()]}))
    for line in outcome_lines(summary):
        st.info(line)
    with st.expander("What's moving the needle", expanded=True):
        for line in drivers_lines(summary):
            st.markdown(line)
        st.markdown("**Firewall: net votes by how each unit is projected to finish**")
        for line in firewall_lines(summary):
            st.markdown(line)
    with st.expander("What's been inputted"):
        for line in inputs_lines(summary):
            st.markdown(line)
    if len(hist) > 1:
        st.plotly_chart(history_figure(hist, true_margin), use_container_width=True)
    t = summary["table"].sort_values("remaining", ascending=False)
    st.subheader(preset["units"] + "s" if not preset["units"].endswith("s") else preset["units"])
    st.dataframe(t, use_container_width=True, hide_index=True,
                 column_config={"pct_in": st.column_config.ProgressColumn("% in", min_value=0, max_value=100,
                                                                       format="%.0f%%")})


def snap(summary):
    return {k_: summary[k_] for k_ in ("pct_in", "median", "p10", "p90")}


# ---------------------------------------------------------------- replay demo
if mode.startswith("Replay"):
    st.sidebar.subheader("Replay")
    seed = st.sidebar.number_input("Scenario seed", 0, 9999, 7)
    swing = st.sidebar.slider("Hidden true swing (pts)", -6.0, 6.0, 2.0, 0.5)
    gap_true = st.sidebar.slider("Hidden true early gap (pts)", 4.0, 14.0, 10.0, 0.5)
    sc = make_scenario(int(seed), swing, gap_true, early_pct_in=0.85)
    st.info(f"Demo only: a synthetic state with a hidden true result, not real {state_name} data. "
            "Step 0 = before Election Day, early/mail only. Use it to learn the model and tune "
            "settings; switch Data to 'My data' or 'Live feed' for the real race.")
    t = st.slider("Time step", 0, sc.steps - 1, 0)
    play = st.button("▶ Play from step 0")
    slot = st.empty()

    def render_step(step):
        hist = []
        for j in range(step + 1):
            res = sc.results_at(j) if j > 0 else None
            s = project(sc.counties, sc.early, res, make_params(sc.poll_margin))
            hist.append(snap(s))
        with slot.container():
            show(s, hist, sc.true_margin)

    if play:
        for j in range(sc.steps):
            render_step(j)
            time.sleep(0.6)
    else:
        render_step(t)
    st.caption(f"Poll used in demo: {sc.poll_margin:+.1f}. Final margin shown only as the green line.")

# ---------------------------------------------------------------- latest published
elif mode.startswith("Latest"):
    import json

    import requests

    from publish import from_json_summary, read_log

    st.sidebar.caption("Reads what the scheduled GitHub job publishes. The race picker above doesn't "
                       "apply here; choose the race below.")
    src = st.sidebar.text_input("Raw URL of latest.json (blank = local data/latest.json)", "")
    every = st.sidebar.number_input("Page refresh seconds", 30, 600, 60)
    auto = st.sidebar.checkbox("Auto-refresh", value=True)

    @st.cache_data(ttl=30)
    def load_latest(url):
        if url:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            return r.json()
        with open("data/latest.json") as fh:
            return json.load(fh)

    try:
        data = load_latest(src.strip())
    except Exception as ex:
        st.warning(f"No published data yet ({ex}). Run `python run_update.py` or wait for the "
                   "GitHub job, then refresh.")
        st.stop()
    ready = {k: v for k, v in data["races"].items() if v.get("summary")}
    if not ready:
        st.warning("latest.json has no race summaries yet. Statuses: " +
                   "; ".join(f"{k}: {v.get('status')}" for k, v in data["races"].items()))
        st.stop()
    rid = st.sidebar.selectbox("Race", list(ready),
                               format_func=lambda k: f"{ready[k]['meta'].get('state')} - {ready[k]['meta'].get('race')}")
    item = ready[rid]
    st.subheader(f"{item['meta'].get('state')}: {item['meta'].get('race')}")
    st.caption(f"Numbers as of {item.get('as_of')} UTC; last check {item.get('checked')} UTC. "
               f"Status: {item.get('status')}")
    if item.get("status") != "ok":
        st.warning("The latest pull for this race failed, so these are the last good numbers.")
    log_src = src.strip().replace("latest.json", "needle_log.csv") if src.strip() else "data/needle_log.csv"
    show(from_json_summary(item["summary"]), read_log(log_src, rid))
    if auto:
        time.sleep(int(every))
        st.rerun()

# ---------------------------------------------------------------- my data / live
else:
    st.sidebar.subheader("Your data")
    demo = make_scenario(7)
    with st.sidebar.expander("Download CSV templates"):
        st.download_button("counties.csv", demo.counties.to_csv(index=False), "counties.csv")
        st.download_button("early.csv", demo.early.to_csv(index=False), "early.csv")
        st.download_button("results.csv", demo.results_at(10).to_csv(index=False), "results.csv")
    st.sidebar.caption(f"Auto-loads from `{folder}/` if present (create with "
                       f"`python new_race.py {abbr} \"{race['name']}\"`).")

    counties = load_csv("counties.csv")
    early = load_csv("early.csv")
    if counties is None:
        f_c = st.sidebar.file_uploader("counties.csv (required)", type="csv")
        counties = pd.read_csv(f_c) if f_c else None
    if early is None:
        f_e = st.sidebar.file_uploader("early.csv (optional)", type="csv")
        early = pd.read_csv(f_e) if f_e else None
    if counties is None:
        st.warning("Add counties.csv for this race to begin: county, region, base_margin, exp_votes, "
                   "exp_early_share. See NOTES.md in the race folder for where each column comes from.")
        st.stop()
    poll = poll_in

    if mode.startswith("My data"):
        results = load_csv("results.csv")
        if results is None:
            f_r = st.sidebar.file_uploader("results.csv (add when counting starts)", type="csv")
            results = pd.read_csv(f_r) if f_r else None
        show(project(counties, early, results, make_params(poll)), [])
    else:
        url = st.sidebar.text_input("Results feed URL")
        fmt = st.sidebar.selectbox("Format", ["csv", "json"])
        county_col = st.sidebar.text_input("Unit column", "county")
        dem_col = st.sidebar.text_input("Dem votes column", "dem")
        rep_col = st.sidebar.text_input("GOP votes column", "rep")
        pct_col = st.sidebar.text_input("Percent-reporting column (optional)", "")
        every = st.sidebar.number_input("Refresh seconds", 30, 600, 120)
        auto = st.sidebar.checkbox("Auto-refresh", value=False)
        hist_key = f"live_hist_{abbr}_{race['name']}"
        if hist_key not in st.session_state:
            st.session_state[hist_key] = []
        results = None
        if url:
            try:
                raw = fetch_table(url, fmt)
                results = to_results(raw, county_col, dem_col, rep_col, pct_col or None)
            except Exception as ex:  # keep the needle alive on a bad fetch
                st.error(f"Feed error: {ex}")
        s = project(counties, early, results, make_params(poll))
        if results is not None:
            st.session_state[hist_key].append(snap(s))
        show(s, st.session_state[hist_key])
        if auto:
            time.sleep(int(every))
            st.rerun()
