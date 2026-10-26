"""
Cross-race adjustment: when counted races come in bluer or redder than the model expected, move the races that are still out.

For every race with enough counted vote we measure its SURPRISE = (current median margin) - (median margin the model gave before
any results, from polls and fundamentals). Positive = bluer than expected. A race still mostly out then gets its prior shifted by

    shift_r = sum_j c_rj * w_j * surprise_j / (sum_j c_rj * w_j + k)        (j = every OTHER race with counts)

w_j = share of race j's vote counted (0 to 1), c_rj = how strongly j informs r (rho_same_state if same state, else rho_national),
k shrinks the estimate when only a little has been counted. The shift is capped. It is applied as extra polling error and extra
fundamentals shift for race r, so r's own counted vote still takes over as it comes in. Races listed in `skip` neither give nor
receive a shift (independents on the ballot, ranked-choice quirks).  Settings: config/cross_race.json.
"""
from __future__ import annotations

import json
import os

DEFAULT = dict(enabled=True, rho_national=0.5, rho_same_state=0.8, min_pct_in=20.0, k=1.0, cap=6.0,
               skip=["NE-senate", "NE-governor"])


def load_cfg(path="config/cross_race.json"):
    cfg = dict(DEFAULT)
    if os.path.exists(path):
        try:
            cfg.update(json.load(open(path)))
        except Exception:
            pass
    return cfg


def compute_shifts(items: dict, cfg: dict | None = None) -> dict:
    """items: {race_id: {"state":..., "pct_in":..., "surprise":... (None if no counted vote)}} -> {race_id: shift}."""
    cfg = cfg or load_cfg()
    if not cfg.get("enabled", True):
        return {}
    skip = set(cfg.get("skip", []))
    src = {k: v for k, v in items.items()
           if k not in skip and v.get("surprise") is not None and v.get("pct_in", 0) >= cfg["min_pct_in"]}
    out = {}
    for rid, it in items.items():
        if rid in skip:
            continue
        num = den = 0.0
        for j, v in src.items():
            if j == rid:
                continue
            c = cfg["rho_same_state"] if v["state"] == it["state"] else cfg["rho_national"]
            w = min(float(v["pct_in"]), 100.0) / 100.0
            num += c * w * v["surprise"]
            den += c * w
        if den > 0:
            out[rid] = max(-cfg["cap"], min(cfg["cap"], num / (den + cfg["k"])))
    return out
