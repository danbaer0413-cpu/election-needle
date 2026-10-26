"""
All races together: how many of our Senate (and governor) races does each party win, with ONE shared error across races.

Each race is a normal draw around its median with the spread its own 80% band implies, and part of that spread (rho_shared,
default 0.5, config/cross_race.json) is the same for every race in a draw: a polling miss or a late swing that hits everywhere.
Independent draws would make "Democrats sweep" and "Democrats lose all" far too unlikely.

This counts only the races on this site (not a full chamber: no holdover seats or races outside our 16 states).
"""
from __future__ import annotations

import numpy as np

Z80 = 1.2816


def simulate(races: dict, rho: float = 0.5, n: int = 20000, seed: int = 7) -> dict:
    out = {}
    rng = np.random.default_rng(seed)
    for key, word in (("senate", "senate"), ("governor", "governor")):
        ids, mu, sd = [], [], []
        for rid, v in races.items():
            s = v.get("summary") or {}
            meta = v.get("meta") or {}
            if not s or s.get("swing_sd") in (None, 0) or word not in str(meta.get("race", "")).lower():
                continue
            ids.append(rid); mu.append(float(s["median"]))
            sd.append(max((float(s["p90"]) - float(s["p10"])) / (2 * Z80), 0.05))
        if not ids:
            continue
        mu, sd = np.array(mu), np.array(sd)
        z = np.sqrt(rho) * rng.standard_normal((n, 1)) + np.sqrt(1 - rho) * rng.standard_normal((n, len(ids)))
        wins = ((mu + sd * z) > 0).sum(axis=1)
        k = len(ids)
        dist = [float((wins == i).mean()) for i in range(k + 1)]
        out[key] = dict(n=k, races=ids, expected_dem_wins=float(wins.mean()), dist=dist,
                        p_dem_majority=float((wins > k / 2).mean()), p_rep_majority=float((wins < k / 2).mean()),
                        rho=rho)
    return out
