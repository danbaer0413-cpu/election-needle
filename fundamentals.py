"""
Fundamentals prior: where a race "should" land from structure alone, before looking at its polls.

    fund_margin = pres2024_margin(state) + k * (generic_ballot - pres2024_national) + approval_adj(state)

* pres2024_margin comes from each state's own history_results.csv (2024 presidential rows).
* k and sd_fund come from the 2018/2022 backtest (backtest() below, data/poll_error_history.csv).
  Out-of-sample error is about 10.5 points, so this is a weak prior: it enters the model as one more
  precision-weighted observation and mostly matters where polls are thin.
* approval_adj: state Trump net approval vs what that state's 2024 lean predicts, scaled by gamma and capped.
  It is a small, unvalidated nudge (no state approval history exists for 2018/2022).
Writes data/fundamentals.csv (id, fund_margin, sd_fund, detail) and returns {race_id: (margin, sd)}.
"""
from __future__ import annotations
import datetime as dt
import glob, json, os
import numpy as np
import pandas as pd


def pres24(state_dir_glob="data/*/history_results.csv"):
    out = {}
    for f in glob.glob(state_dir_glob):
        h = pd.read_csv(f)
        p = h[(h.year == 2024) & h.race.str.contains("Pres", case=False)]
        if len(p):
            out[h.state.iloc[0]] = (p.dem_votes.sum() - p.rep_votes.sum()) / (p.dem_votes.sum() + p.rep_votes.sum()) * 100
    return out


def compute(cfg_path="config/fundamentals.json", inputs="data/fundamentals_inputs.csv", races="config/races.json",
            out="data/fundamentals.csv"):
    cfg = json.load(open(cfg_path))
    base = pres24()
    inp = pd.read_csv(inputs).set_index("state")
    st = [s for s in inp.index if s in base]
    # what approval would be if it only tracked 2024 lean (linear fit across our states)
    x = np.array([-base[s] for s in st]); y = inp.loc[st, "trump_net_approval"].to_numpy(float)
    b, a = np.polyfit(x, y, 1)
    gb = cfg["generic_ballot_margin_dem"] * cfg.get("generic_shrink", 1.0)
    swing_nat = gb - cfg["pres_2024_national_margin_dem"]
    k = cfg["k_pooled"] if abs(swing_nat) < cfg.get("wave_threshold", 99) else 0.5 * (cfg["k_pooled"] + cfg["k_wave"])
    asof = cfg.get("generic_ballot_asof")
    if asof:
        age = (dt.date.today() - dt.date.fromisoformat(asof)).days
        if age > cfg.get("stale_after_days", 14):
            print(f"  WARNING: fundamentals generic ballot is {age} days old ({asof}); update config/fundamentals.json")
    res = {}
    rows = []
    for r in json.load(open(races))["races"]:
        rid, s = r["id"], r["state"]
        if rid in cfg.get("skip_races", []) or s not in base or s not in inp.index:
            continue
        resid = float(inp.loc[s, "trump_net_approval"]) - (a + b * (-base[s]))   # + = Trump better than lean implies
        adj = float(np.clip(-cfg["gamma_approval"] * resid, -cfg["approval_cap"], cfg["approval_cap"]))
        fm = base[s] + k * swing_nat + adj
        res[rid] = (round(fm, 2), cfg["sd_fund"])
        rows.append({"id": rid, "fund_margin": round(fm, 2), "sd_fund": cfg["sd_fund"], "pres24": round(base[s], 1),
                     "national_shift": round(k * swing_nat, 1), "approval_resid": round(resid, 1),
                     "approval_adj": round(adj, 2)})
    if out:
        pd.DataFrame(rows).to_csv(out, index=False)
    return res


def backtest(hist="data/poll_error_history.csv"):
    """Leave-one-year-out test of pres_prior + k*swing on competitive 2018/2022 statewide races."""
    h = pd.read_csv(hist)
    pres = h[h.race == "President"].pivot_table(index="state", columns="year", values="actual_margin")
    nat = {2018: (8.7 - 2.2, 2016), 2022: (-2.8 - 4.5, 2020)}     # House 2p margin minus prior national 2p pres margin
    rows = []
    for y, (sw, py) in nat.items():
        m = h[(h.year == y) & h.race.isin(["Governor", "U.S. Senate", "U.S. Senate (special)"])].copy()
        m = m.join(pres[py].rename("prior"), on="state").dropna(subset=["prior"])
        m = m[m.poll_margin.abs() <= 15]
        m["dev"] = m.actual_margin - m.prior; m["sw"] = sw
        rows.append(m)
    c = pd.concat(rows)
    k = (c.dev * c.sw).sum() / (c.sw ** 2).sum()
    print(f"pooled k={k:.2f}, n={len(c)}")
    for y in (2018, 2022):
        tr, te = c[c.year != y], c[c.year == y]
        kk = (tr.dev * tr.sw).sum() / (tr.sw ** 2).sum(); e = te.dev - kk * te.sw
        print(f"  leave out {y}: k={kk:.2f} rmse={np.sqrt((e ** 2).mean()):.2f}")


if __name__ == "__main__":
    backtest()
    r = compute()
    for k_, v in r.items():
        print(f"{k_}: fundamentals {v[0]:+.1f} (sd {v[1]})")
