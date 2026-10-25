"""
Ranked-choice transfer skew from past results (Maine, Alaska).

Input: one row per past ranked-choice contest, round-1 and final-round votes:
    contest, d_round1, r_round1, other_round1, d_final, r_final
(d/r = the Democratic-side and Republican-side candidates; other = everyone else in round 1.)
Ballots that end up with neither finalist are "exhausted".

The skew is how far the other candidates' ballots lean toward D vs R. Past contests are few
and differ (primaries have different electorates than generals), so the pooled estimate is
pulled toward an even split of the non-exhausted ballots.
"""
from __future__ import annotations

import pandas as pd

REQUIRED = ["contest", "d_round1", "r_round1", "other_round1", "d_final", "r_final"]


def estimate_transfers(df: pd.DataFrame, prior_frac: float = 0.25) -> tuple[pd.DataFrame, dict]:
    miss = [c for c in REQUIRED if c not in df]
    if miss:
        raise ValueError(f"rcv history is missing columns: {miss}")
    d = df.copy()
    d = d[d["other_round1"] > 0].copy()
    d["gain_d"] = d["d_final"] - d["d_round1"]
    d["gain_r"] = d["r_final"] - d["r_round1"]
    d["to_d"] = (d["gain_d"] / d["other_round1"]).clip(0, 1)
    d["to_r"] = (d["gain_r"] / d["other_round1"]).clip(0, 1)
    d["exhausted"] = (1 - d["to_d"] - d["to_r"]).clip(0, 1)
    O = float(d["other_round1"].sum())
    gd, gr = float(d["gain_d"].clip(lower=0).sum()), float(d["gain_r"].clip(lower=0).sum())
    mean = (gd + gr) / (2 * O)                    # even split of the non-exhausted share
    prior = prior_frac * O
    to_d = (gd + prior * mean) / (O + prior)
    to_r = (gr + prior * mean) / (O + prior)
    pooled = {"to_d": round(to_d, 3), "to_r": round(to_r, 3), "exhausted": round(max(1 - to_d - to_r, 0), 3),
              "raw_to_d": round(gd / O, 3), "raw_to_r": round(gr / O, 3),
              "skew_d_minus_r": round(to_d - to_r, 3), "contests": int(len(d)), "other_votes": int(O)}
    return d[["contest", "other_round1", "to_d", "to_r", "exhausted"]].round(3), pooled


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit("usage: python rcv.py rcv_history.csv  (columns: " + ", ".join(REQUIRED) + ")")
    t, p = estimate_transfers(pd.read_csv(sys.argv[1]))
    print(t.to_string(index=False))
    print(p)
