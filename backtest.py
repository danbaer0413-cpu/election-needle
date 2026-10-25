"""Replay many synthetic elections and score the model at each step.

Usage: python backtest.py [n_seeds]
Checks internal consistency (is the 80% band really ~80%? does it converge?), not
real-world accuracy. Real validation needs timestamped county results from past races.
"""
import sys

import numpy as np
import pandas as pd

from model import Params, project
from synthetic import make_scenario


def run(n_seeds=60, steps=(0, 2, 4, 6, 8, 10, 12, 16, 20), use_early=True, use_poll=True):
    rows = []
    for s in range(n_seeds):
        rng = np.random.default_rng(1000 + s)
        sc = make_scenario(seed=s, true_swing=float(rng.normal(0, 3)), gap_true=float(rng.uniform(6, 13)))
        for t in steps:
            p = Params(poll_margin=sc.poll_margin if use_poll else None, seed=s)
            early = sc.early if use_early else None
            res = sc.results_at(t) if t > 0 else None
            out = project(sc.counties, early, res, p)
            rows.append(dict(seed=s, t=t, pct_in=out["pct_in"], err=out["median"] - sc.true_margin,
                             inside=out["p10"] <= sc.true_margin <= out["p90"],
                             width=out["p90"] - out["p10"], win_prob=out["win_prob"],
                             dem_won=sc.true_margin > 0))
    d = pd.DataFrame(rows)
    d["brier"] = (d.win_prob - d.dem_won.astype(float)) ** 2
    g = d.groupby("t").agg(pct_in=("pct_in", "mean"), mae=("err", lambda x: np.abs(x).mean()),
                           bias=("err", "mean"), cover80=("inside", "mean"),
                           band=("width", "mean"), brier=("brier", "mean")).round(2)
    return g


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    print("Full model (polls + early vote signals + counted votes)")
    print(run(n))
    print("\nPolls only before counting (no early-vote data)")
    print(run(n, use_early=False))
