"""
Historical poll error by state -> prior for the needle.

Input: one row per (state, election) with
    state, year, race, poll_margin, actual_margin     (margins D-R, points)
    e.g. the final polling average vs the certified result.
Error is actual - poll: positive = polls underestimated Democrats.

Model
  err[s,c] = cycle effect[c] + state bias[s] + noise[s,c]
  cycle effect  = shared miss in a given year/race type (the "national environment").
                  Unpredictable, so it widens the spread but is NOT added to the mean.
  state bias    = persistent skew for a state, SHRUNK toward 0 (empirical Bayes), since
                  ~10 points per state is thin and past misses have not always repeated.
  spread        = state noise (shrunk toward the pooled noise) combined with cycle sd.
  skew          = estimated on ALL residuals pooled (hundreds of points), not per state.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED = ["state", "year", "race", "poll_margin", "actual_margin"]


def _skewnormal_alpha(gamma: float) -> float:
    """Method-of-moments shape for a skew-normal with sample skewness `gamma`."""
    g = float(np.clip(gamma, -0.95, 0.95))
    d = np.linspace(-0.995, 0.995, 3981)
    mu = d * np.sqrt(2 / np.pi)
    skew = (4 - np.pi) / 2 * mu ** 3 / (1 - mu ** 2) ** 1.5
    dsel = d[np.argmin(np.abs(skew - g))]
    return float(dsel / np.sqrt(1 - dsel ** 2))


def estimate(history: pd.DataFrame, k_noise: float = 4.0, min_state_n: int = 1) -> tuple[pd.DataFrame, dict]:
    miss = [c for c in REQUIRED if c not in history]
    if miss:
        raise ValueError(f"history is missing columns: {miss}")
    d = history.dropna(subset=["poll_margin", "actual_margin"]).copy()
    d["err"] = d["actual_margin"] - d["poll_margin"]
    d["cycle"] = d["year"].astype(str) + "|" + d["race"].astype(str)

    cyc = d.groupby("cycle")["err"].agg(["mean", "count"])
    cyc = cyc[cyc["count"] >= 3]                       # need several states to call it a cycle effect
    sd_cycle = float(cyc["mean"].std(ddof=1)) if len(cyc) > 1 else 0.0
    d["resid"] = d["err"] - d["cycle"].map(cyc["mean"]).fillna(0.0)

    pooled_sd = float(d["resid"].std(ddof=1))
    skew_g = float(((d["resid"] - d["resid"].mean()) ** 3).mean() / d["resid"].std(ddof=0) ** 3)
    # Sample skewness is wildly unstable on small samples; don't use it below ~100 observations.
    alpha = _skewnormal_alpha(skew_g) if len(d) >= 100 else 0.0

    g = d.groupby("state")["resid"].agg(n="count", mean="mean", sd="std").reset_index()
    g = g[g["n"] >= min_state_n].copy()
    g["sd"] = g["sd"].fillna(pooled_sd)
    # shrink the bias: tau^2 = spread of true state biases beyond sampling noise
    samp_var = (pooled_sd ** 2) / g["n"]
    tau2 = max(float(g["mean"].var(ddof=1) - samp_var.mean()), 0.05 ** 2) if len(g) > 1 else 0.0
    w = tau2 / (tau2 + samp_var)
    g["bias_raw"] = g["mean"]
    g["bias"] = (w * g["mean"]).round(2)
    # shrink the state noise toward the pooled noise
    g["sd_state"] = np.sqrt(((g["n"] - 1).clip(lower=0) * g["sd"] ** 2 + k_noise * pooled_sd ** 2)
                            / ((g["n"] - 1).clip(lower=0) + k_noise))
    g["sd_total"] = np.sqrt(g["sd_state"] ** 2 + sd_cycle ** 2)
    out = g[["state", "n", "bias_raw", "bias", "sd_state", "sd_total"]].round(2).sort_values("state")
    pooled = {"sd_cycle": round(sd_cycle, 2), "sd_pooled_resid": round(pooled_sd, 2),
              "skewness": round(skew_g, 2), "alpha": round(alpha, 2), "tau_bias": round(float(np.sqrt(tau2)), 2),
              "n_obs": int(len(d)), "n_cycles": int(len(cyc))}
    return out.reset_index(drop=True), pooled


def params_for(state: str, table: pd.DataFrame, pooled: dict, use_skew: bool = True) -> dict:
    """Values to plug into model.Params for one state (falls back to pooled if state unseen)."""
    r = table[table["state"] == state]
    if len(r):
        bias, sd = float(r["bias"].iloc[0]), float(r["sd_total"].iloc[0])
    else:
        bias, sd = 0.0, float(np.hypot(pooled["sd_pooled_resid"], pooled["sd_cycle"]))
    return {"poll_bias": bias, "sd_poll": round(sd, 2), "poll_skew": pooled["alpha"] if use_skew else 0.0}


def synthetic_history(seed: int = 0, n_states: int = 40, n_cycles: int = 10):
    """Fake history with planted truth, for testing the estimator only."""
    rng = np.random.default_rng(seed)
    states = [f"S{i:02d}" for i in range(n_states)]
    bias = rng.normal(0, 1.2, n_states)
    sd_s = rng.uniform(2.5, 4.5, n_states)
    cyc = rng.normal(0, 2.5, n_cycles)
    alpha = -3.0
    dlt = alpha / np.sqrt(1 + alpha ** 2)
    rows = []
    for c in range(n_cycles):
        for i, s in enumerate(states):
            if rng.random() < 0.15:
                continue                                  # not every state polled every cycle
            u0, v = rng.normal(), rng.normal()
            z = dlt * abs(u0) + np.sqrt(1 - dlt ** 2) * v
            z = (z - dlt * np.sqrt(2 / np.pi)) / np.sqrt(1 - 2 * dlt ** 2 / np.pi)
            poll = rng.normal(0, 8)
            rows.append(dict(state=s, year=2008 + 2 * c, race="Pres" if c % 2 == 0 else "Senate",
                             poll_margin=poll, actual_margin=poll + cyc[c] + bias[i] + sd_s[i] * z))
    truth = pd.DataFrame({"state": states, "bias_true": bias, "sd_true": sd_s})
    return pd.DataFrame(rows), truth, {"cycle_sd": float(cyc.std(ddof=1)), "alpha": alpha}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit("usage: python poll_error.py history.csv   (columns: " + ", ".join(REQUIRED) + ")")
    t, p = estimate(pd.read_csv(sys.argv[1]))
    print(p)
    print(t.to_string(index=False))
