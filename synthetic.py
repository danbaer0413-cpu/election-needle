"""
Synthetic state for testing and replay. NOT real election data.

A hidden true swing, region effects, county effects and an early-vs-Election-Day gap
generate final county results. Counting follows a timeline: each county reports its
early/mail vote in one dump, then Election Day votes ramp in. Step 0 is the moment
before Election Day, when only early/mail returns exist.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

REGIONS = {
    #            n  base margin (mean, sd)  votes (mean)  start step range
    "Urban core": (6, (32, 7), 260_000, (5, 11)),
    "Suburbs": (14, (3, 6), 90_000, (3, 9)),
    "Rural North": (14, (-24, 6), 22_000, (1, 6)),
    "Rural South": (14, (-34, 6), 18_000, (1, 6)),
}


@dataclass
class Scenario:
    counties: pd.DataFrame
    early: pd.DataFrame
    poll_margin: float
    steps: int
    true_margin: float
    true_swing: float
    _sched: pd.DataFrame

    def results_at(self, t: int) -> pd.DataFrame:
        rows = []
        for r in self._sched.itertuples():
            if t < r.start:
                rows.append((r.county, 0.0, 0.0, False))
                continue
            f = float(np.clip((t - r.start) / r.dur, 0, 1))
            e_d = r.E * (0.5 + r.early_m / 200)
            e_r = r.E * (0.5 - r.early_m / 200)
            ced = f * r.ED
            m_ed = r.ed_m + r.bias * (1 - f) if f < 1 else r.ed_m
            d_d = ced * (0.5 + m_ed / 200)
            d_r = ced * (0.5 - m_ed / 200)
            rows.append((r.county, round(e_d + d_d), round(e_r + d_r), f >= 1))
        return pd.DataFrame(rows, columns=["county", "dem", "rep", "final"])


def make_scenario(seed: int = 7, true_swing: float = 2.0, gap_true: float = 10.0,
                  steps: int = 21, early_pct_in: float = 0.85) -> Scenario:
    rng = np.random.default_rng(seed)
    recs = []
    for reg, (n, (mu, sd), votes, (s0, s1)) in REGIONS.items():
        for i in range(n):
            recs.append(dict(
                county=f"{reg.split()[0]} {reg.split()[-1]} {i + 1}", region=reg,
                base_margin=rng.normal(mu, sd),
                exp_votes=votes * rng.lognormal(0, 0.45),
                exp_early_share=float(np.clip(rng.normal(0.45, 0.08), 0.2, 0.7)),
                start=rng.integers(s0, s1 + 1), dur=rng.integers(3, 9),
                bias=rng.normal(0, 5)))
    c = pd.DataFrame(recs)
    # centre the state near even
    M0 = (c.exp_votes * c.base_margin).sum() / c.exp_votes.sum()
    c["base_margin"] = (c.base_margin - M0 - 1.0).round(1)
    c["exp_votes"] = c.exp_votes.round(0)
    c["exp_early_share"] = c.exp_early_share.round(3)
    M0 = (c.exp_votes * c.base_margin).sum() / c.exp_votes.sum()

    # ---- hidden truth ----------------------------------------------------------------
    g_true = {r: rng.normal(0, 2.0) for r in REGIONS}
    m_true = (c.base_margin + true_swing + c.region.map(g_true) + rng.normal(0, 2.5, len(c))).to_numpy()
    E = c.exp_votes * c.exp_early_share * 1.08 * rng.lognormal(0, 0.03, len(c))   # early surge
    ED = c.exp_votes * (1 - c.exp_early_share) * rng.lognormal(0, 0.03, len(c))
    w = (E / (E + ED)).to_numpy()
    early_m = m_true + (1 - w) * gap_true
    ed_m = m_true - w * gap_true
    sched = pd.DataFrame(dict(county=c.county, start=c.start, dur=c.dur, bias=c.bias,
                              E=E.round(0), ED=ED.round(0), early_m=early_m, ed_m=ed_m))

    tot_d = (E * (0.5 + early_m / 200) + ED * (0.5 + ed_m / 200)).sum()
    tot_r = (E * (0.5 - early_m / 200) + ED * (0.5 - ed_m / 200)).sum()
    true_margin = (tot_d - tot_r) / (tot_d + tot_r) * 100

    # ---- early/mail returns at step 0, with party registration -----------------------
    L_true, pO = 0.90, rng.uniform(0.2, 0.3, len(c))
    se = 0.5 + early_m / 200
    delta = (2 * se - 1) * (1 - pO) / (2 * L_true - 1) + rng.normal(0, 0.02, len(c))
    pD = ((1 - pO) + delta) / 2
    pR = ((1 - pO) - delta) / 2
    E_ret = (E * early_pct_in * rng.lognormal(0, 0.02, len(c))).round(0)
    early = pd.DataFrame(dict(county=c.county, early_returned=E_ret,
                              d_reg=(E_ret * pD).round(0), r_reg=(E_ret * pR).round(0),
                              o_reg=(E_ret * pO).round(0)))

    poll = float(M0 + true_swing + rng.normal(0, 2.5))
    counties = c[["county", "region", "base_margin", "exp_votes", "exp_early_share"]].copy()
    return Scenario(counties, early, round(poll, 1), steps, float(true_margin), true_swing, sched)
