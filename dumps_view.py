"""'Vote dumps' tab: newest batches of counted votes first (reads data/vote_dumps.csv written by dumps.py). Display only."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")


def _m(x):
    try:
        x = float(x)
    except Exception:
        return ""
    return f"D+{x:.0f}" if x > 0.5 else f"R+{-x:.0f}" if x < -0.5 else "Even"


def _needle(x):
    try:
        x = float(x)
    except Exception:
        return "-"
    return f"D+{x:.1f}" if x > 0 else f"R+{-x:.1f}"


def _t(ts):
    try:
        return datetime.fromisoformat(str(ts)).astimezone(ET).strftime("%-I:%M %p")
    except Exception:
        return str(ts)[11:16]


def render(st, ready, label, src: str = ""):
    path = src.strip().replace("latest.json", "vote_dumps.csv") if src.strip() else "data/vote_dumps.csv"

    @st.cache_data(ttl=30)
    def _load(p):
        return pd.read_csv(p)

    @st.cache_data(ttl=600)
    def _names():
        try:
            c = pd.read_csv("config/candidates.csv")
            return {r.id: (str(r.dem), str(r.rep)) for r in c.itertuples()}
        except Exception:
            return {}

    names = _names()
    try:
        d = _load(path)
    except Exception:
        d = pd.DataFrame()
    st.markdown("**Vote dumps** - every batch of counted votes the needle picked up, newest first.")
    if d.empty:
        st.info("No votes counted yet. Batches appear here after polls close, within about 10 minutes of each update.")
        return
    races = ["All races"] + sorted(d["race"].unique(), key=lambda r: label(ready[r]) if r in ready else r)
    c1, c2 = st.columns([3, 2])
    pick = c1.selectbox("Race", races, format_func=lambda r: r if r == "All races" else (label(ready[r]) if r in ready else r), key="dump_race")
    big = c2.selectbox("Batch size", [0, 1000, 5000, 25000], format_func=lambda v: "Any size" if v == 0 else f"{v:,}+ votes", key="dump_min")
    x = d if pick == "All races" else d[d["race"] == pick]
    x = x[(x["kind"] == "correction") | (x["added"].abs() >= big)].iloc[::-1].head(80)
    for r in x.itertuples():
        name = label(ready[r.race]) if r.race in ready else r.race
        if r.kind == "correction":
            line = f"⚠️ **{r.county}** count corrected {int(r.added):,} votes"
        else:
            m = r.batch_margin
            dot = "🟦" if pd.notna(m) and m > 0.5 else "🟥" if pd.notna(m) and m < -0.5 else "⬜"
            where = "statewide total" if r.kind == "statewide" else f"**{r.county}**"
            pin = f" ({r.county_pct_in:.0f}% of county in)" if pd.notna(r.county_pct_in) else ""
            heavy = " 🔥" if r.added >= 50000 else ""
            dn, rn = names.get(r.race, ("Dem", "GOP"))
            dv, rv = getattr(r, "dem_votes", None), getattr(r, "rep_votes", None)
            who = (f" · {dn} {int(dv):,} – {rn} {int(rv):,}" if pd.notna(dv) and pd.notna(rv) else "")
            line = f"{dot} {where} +{int(r.added):,} votes, batch **{_m(m)}**{who}{pin}{heavy}"
        st.markdown(f"`{_t(r.ts_utc)}` {name} · {line} · needle {_needle(r.needle)} at {r.race_pct_in:.0f}% counted")
    st.caption("Batch margin = Dem minus GOP among the new votes; candidate counts are the two main candidates (third-party votes not shown) "
               "and can be off by a few hundred in very large counties. Statewide-total batches are states that only reported a total at that time. "
               "Each update runs about every 10 minutes, so one row can hold several county releases. Not race calls.")
