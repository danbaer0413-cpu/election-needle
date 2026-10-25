"""
Keep county early-vote numbers current between hand updates, using VoteHub's statewide totals.

Method: take the last real county snapshot (base), add the statewide votes VoteHub reports AFTER the
snapshot date (its daily changes, not its level, so definition gaps between sources cancel out), and
spread that increase across counties in proportion to each county's share of the base snapshot.
Geography is therefore frozen at the snapshot; only the size grows. Real county data always wins:
refresh the base snapshot whenever you have one and the scaling restarts from it.
"""
from __future__ import annotations

import pandas as pd


def scaled_early(base: pd.DataFrame, history: pd.DataFrame, state: str, base_date: str,
                 kind: str | None = None) -> tuple[pd.DataFrame, dict]:
    h = history[history["state"].str.lower() == state.lower()].copy()
    if kind:
        h = h[h["kind"] == kind]
    h = h[h["as_of"] > base_date].dropna(subset=["delta"])
    h["delta"] = pd.to_numeric(h["delta"], errors="coerce")
    added = float(h["delta"].sum()) if len(h) else 0.0
    out = base.copy()
    tot = float(out["early_returned"].sum())
    out["early_returned"] = (out["early_returned"] * (1 + added / tot)).round().astype(int)
    info = {"base_total": int(tot), "added": int(added), "days_added": int(len(h)),
            "latest_post": h["as_of"].max() if len(h) else None}
    return out, info
