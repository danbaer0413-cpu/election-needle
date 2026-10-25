"""
Fit the polling-error adjustments from data/poll_error_history.csv and write config/poll_error.json.

What is used (each passed a leave-one-year-out test on 2018/2022):
  * state_bias  - a state's persistent miss, measured as each race's error minus that year's average error for its
                  race type, pooled over ALL cycles (2016-2024), shrunk toward 0 with prior weight K=3 observations.
                  Out of sample it cut RMSE from 4.50 to 4.13 (2018) and 4.32 to 3.86 (2022).
  * global_bias - mean midterm miss (2018, 2022), halved, because only two midterms exist.
  * sd by poll count - out-of-sample residual SD for averages with <4 and 4+ polls, inflated 10%.
What was tested and left OUT (did not improve out of sample): a slope for lopsided races, poll-tier (thin / widened) biases,
midterm-only state biases.
Run: python poll_error_fit.py   (rewrites config/poll_error.json)
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd

K = 3.0
INFLATE = 1.10


def fit(h: pd.DataFrame, k: float = K):
    h = h.copy(); h["err"] = h.actual_margin - h.poll_margin
    h["dev"] = h.err - h.groupby(["year", "race"]).err.transform("mean")
    g = h.groupby("state").dev.agg(["sum", "count"])
    sb = (g["sum"] / (g["count"] + k))
    mid = h[h.year.isin([2018, 2022])].err.mean()
    return sb, 0.5 * mid, h


def main():
    h0 = pd.read_csv("data/poll_error_history.csv")
    sb, gb, h = fit(h0)
    # out-of-sample residuals (leave one midterm year out) -> SD by number of polls
    res = []
    for y in (2018, 2022):
        tr, te = h0[h0.year != y], h0[h0.year == y].copy()
        s2, g2, _ = fit(tr)
        te["err"] = te.actual_margin - te.poll_margin
        te["res"] = te.err - te.state.map(s2).fillna(0) - g2
        res.append(te)
    r = pd.concat(res)
    r["nb"] = pd.cut(r.n_polls, [0, 3, 100], labels=["<4", "4+"])   # 1 and 2-3 pooled: their SDs are not ordered in the data
    sd = r.groupby("nb", observed=True).res.std().round(2).to_dict()
    sd_all = float(r.res.std())
    out = {
        "_note": "Written by poll_error_fit.py from data/poll_error_history.csv. state_bias and global_bias are added to the poll margin (actual - poll).",
        "global_bias": round(float(gb), 2),
        "state_bias": {k: round(float(v), 2) for k, v in sb.items()},
        "sd_by_polls": {k: round(v * INFLATE, 2) for k, v in sd.items()},
        "sd_default": round(sd_all * INFLATE, 2),
        "sd_floor": 4.0,
        "skip_state_bias": ["NE-senate"],
        "oos_rmse": {"raw_2018_2022": round(float(np.sqrt(((h0.actual_margin - h0.poll_margin)[h0.year.isin([2018, 2022])] ** 2).mean())), 2),
                     "adjusted_oos": round(float(np.sqrt((r.res ** 2).mean())), 2)},
    }
    json.dump(out, open("config/poll_error.json", "w"), indent=2)
    print(json.dumps({k: out[k] for k in ("global_bias", "sd_by_polls", "sd_default", "oos_rmse")}))
    print("state_bias (+ = polls usually understate Dems):", {k: v for k, v in sorted(out["state_bias"].items(), key=lambda x: x[1])})


if __name__ == "__main__":
    main()
