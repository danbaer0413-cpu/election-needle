"""
Electorate model: a rough, editable guess of who votes in 2026 in each state, as one more piece of evidence for the swing.

Per state (config/electorate.csv): independents' share of the 2024 electorate (ind_share), how much more Democratic independents were than the state's
2024 margin (ind_edge_24), 2026 turnout relative to 2024 for Democrats / Republicans / independents (turnout_d/r/i), and how far independents move toward
Democrats vs 2024 (ind_shift, default 9 points: D+3 nationally in 2024 to about D+12 now).
Partisans vote their party with `loyalty`. The 2024 shares of Democrats and Republicans are solved so the guess reproduces the state's own 2024 margin.
A single partisan-defection shift d (same everywhere) is then solved so that the vote-weighted average swing equals the national swing the fundamentals use,
so this layer REDISTRIBUTES the swing across states (independents' weight, turnout guesses); it does not change the national level.
compute(rows) -> {race id: swing vs the race's 2024-based baseline, in points}.  rows = [(race_id, state, baseline_margin, expected_votes)]
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd


def national_swing(cfg_path="config/fundamentals.json"):
    cfg = json.load(open(cfg_path))
    gb = cfg["generic_ballot_margin_dem"] * cfg.get("generic_shrink", 1.0)
    sw = gb - cfg["pres_2024_national_margin_dem"]
    k = cfg["k_pooled"] if abs(sw) < cfg.get("wave_threshold", 99) else 0.5 * (cfg["k_pooled"] + cfg["k_wave"])
    return k * sw


def compute(rows, path="config/electorate.csv", cfg_path="config/electorate.json", detail=False):
    cfg = json.load(open(cfg_path))
    tab = pd.read_csv(path).set_index("state")
    L = float(cfg.get("loyalty", 0.95))
    P = (2 * L - 1) * 100.0
    out, parts = {}, []
    for rid, st, M24, votes in rows:
        if rid in cfg.get("skip_races", []) or st not in tab.index:
            continue
        r = tab.loc[st]
        sI = float(r.ind_share)
        i24 = M24 + float(r.ind_edge_24)
        x = (M24 - sI * i24) / P                               # sD - sR in 2024
        sD, sR = (1 - sI + x) / 2, (1 - sI - x) / 2
        sD, sR = max(sD, 0.03), max(sR, 0.03)
        z = sD + sR + sI
        sD, sR, sI = sD / z, sR / z, sI / z
        a, b, c = sD * float(r.turnout_d), sR * float(r.turnout_r), sI * float(r.turnout_i)
        z = a + b + c
        a, b, c = a / z, b / z, c / z
        i26 = i24 + float(r.ind_shift)
        base26 = P * (a - b) + c * i26                         # before the partisan defection shift
        m24 = P * (sD - sR) + sI * i24                         # ~M24 (exact unless clipped)
        parts.append((rid, float(votes), base26 - M24, a + b, m24 - M24))
    if not parts:
        return {}
    w = np.array([p[1] for p in parts]); w = w / w.sum()
    nat = national_swing()
    swing0 = np.array([p[2] for p in parts]); part = np.array([p[3] for p in parts])
    d = (nat - float((w * swing0).sum())) / float((w * part).sum())
    for rid, _, s0, pt, _ in parts:
        out[rid] = round(s0 + d * pt, 2)
    if detail:
        return out, dict(national_swing=round(nat, 2), defection_shift=round(d, 2))
    return out
