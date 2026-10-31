"""National environment needle: what overall national margin (generic-ballot equivalent) the counted vote implies.

Before any votes: the model's own assumption, generic ballot x generic_shrink (config/fundamentals.json), D+6.4 now, with a
spread tau (default 3.0) for how far the real national vote can land from it.
As votes come in: every race with at least min_pct_in counted gives a SURPRISE (its current median minus the median the
model gave before any results; the same number cross_race.py uses). Each surprise is one noisy read of the national shift,
with race-level noise sigma (default 4.0). Standard normal-normal update:

    shift = sum_j w_j * surprise_j / (sum_j w_j + sigma^2 / tau^2)        w_j = share of race j counted (0 to 1)
    env   = prior + shift         sd = sqrt(1 / (1/tau^2 + sum_j w_j / sigma^2))

So the needle starts at the model's assumption with a wide range, moves toward what the count shows, and the range narrows.
Senate and governor races in the same state are treated as separate reads (they are correlated, so it is slightly overconfident).
"""
from __future__ import annotations

import json
import math
import os

Z80, Z90 = 1.2816, 1.6449


def prior(cfg_path="config/fundamentals.json"):
    cfg = json.load(open(cfg_path))
    raw = float(cfg["generic_ballot_margin_dem"])
    return raw * float(cfg.get("generic_shrink", 1.0)), raw, cfg.get("generic_ballot_asof")


def estimate(items=None, tau=3.0, sigma=4.0, min_pct_in=20.0, skip=("NE-senate", "NE-governor"), cap=8.0, cfg_path="config/fundamentals.json"):
    """items: {race_id: {"pct_in":..., "surprise":... or None}} -> dict for the needle (JSON-safe)."""
    p0, raw, asof = prior(cfg_path)
    num = wsum = 0.0
    n = 0
    for rid, it in (items or {}).items():
        sur = it.get("surprise")
        if rid in skip or sur is None or float(it.get("pct_in") or 0) < min_pct_in:
            continue
        w = min(float(it["pct_in"]), 100.0) / 100.0
        num += w * sur
        wsum += w
        n += 1
    k = sigma ** 2 / tau ** 2
    shift = max(-cap, min(cap, num / (wsum + k))) if wsum > 0 else 0.0
    sd = math.sqrt(1.0 / (1.0 / tau ** 2 + wsum / sigma ** 2))
    env = p0 + shift
    return dict(median=round(env, 2), p05=round(env - Z90 * sd, 2), p10=round(env - Z80 * sd, 2),
                p90=round(env + Z80 * sd, 2), p95=round(env + Z90 * sd, 2), sd=round(sd, 2),
                prior=round(p0, 2), shift=round(shift, 2), generic_raw=round(raw, 2), generic_asof=asof,
                races_counted=n, weight=round(wsum, 2))
