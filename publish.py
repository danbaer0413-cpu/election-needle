"""Serialize model output for publishing (latest.json + log) and read it back in the app."""
from __future__ import annotations

import json
import os
import tempfile

import pandas as pd

KEYS = ["median", "p05", "p10", "p90", "p95", "win_prob", "pct_in", "baseline_margin",
        "swing", "swing_sd", "turnout_mult", "signals", "point_first", "drivers", "inputs",
        "outcome", "first_round"]


def to_json_summary(out: dict) -> dict:
    d = {k: out.get(k) for k in KEYS}
    d["table"] = out["table"].to_dict("records")
    d["tiers"] = out["tiers"].to_dict("records")
    return d


def from_json_summary(d: dict) -> dict:
    s = dict(d)
    s["table"] = pd.DataFrame(d["table"])
    s["tiers"] = pd.DataFrame(d.get("tiers") or [])
    return s


def _default(o):
    return o.item() if hasattr(o, "item") else str(o)


def write_json_atomic(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        json.dump(obj, fh, default=_default)
    os.replace(tmp, path)


def read_log(path: str, race_id: str) -> list[dict]:
    if not path.startswith("http") and not os.path.exists(path):
        return []
    try:
        df = pd.read_csv(path)
    except Exception:
        return []
    df = df[df["id"] == race_id].dropna(subset=["median"])
    return df[["pct_in", "median", "p10", "p90"]].to_dict("records")
