"""
One update pass: pull data for every configured race, run the model, publish.

    python run_update.py [--config config/races.json] [--out data/latest.json] [--only ID]

Writes data/latest.json (latest summary per race) and appends data/needle_log.csv.
Runs the same on your laptop or in GitHub Actions. If a feed fails, the previous good
summary is kept and marked with the error, so the app never shows a blank needle.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import traceback

import pandas as pd

from feeds import fetch_table, to_results
from model import Params, project
from publish import to_json_summary, write_json_atomic


def _read(path):
    """CSV as a DataFrame, or None if the file is missing, empty or header-only."""
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return None
    df = pd.read_csv(path)
    return df if len(df) else None


def load_early(cfg: dict, folder: str):
    f = cfg.get("early_feed") or {}
    if f.get("kind") == "url" and f.get("url"):
        raw = fetch_table(f["url"], f.get("fmt", "csv"), sheet=f.get("sheet"))
        raw = raw.rename(columns={v: k for k, v in (f.get("columns") or {}).items()})
        keep = [c for c in ("county", "early_returned", "d_reg", "r_reg", "o_reg") if c in raw]
        df = raw[keep].copy()
        df["county"] = df["county"].astype(str).str.replace(r"\s+County$", "", regex=True).str.strip()
        return df
    if f.get("kind") == "scaled":       # county snapshot + VoteHub statewide changes since it
        from scale_early import scaled_early
        base = _read(os.path.join(folder, f.get("path", "early.csv")))
        hist = _read(f.get("history", "data/votehub_history.csv"))
        if base is None or hist is None:
            return base
        df, info = scaled_early(base, hist, f["state_name"], f["base_date"], f.get("votehub_kind"))
        print(f"  early vote scaled: base {info['base_total']:,} + {info['added']:,} from {info['days_added']} VoteHub days")
        return df
    return _read(os.path.join(folder, f.get("path", "early.csv")))


def load_results(cfg: dict, folder: str):
    f = cfg.get("feed") or {}
    if f.get("kind") == "url" and f.get("url"):
        raw = fetch_table(f["url"], f.get("fmt", "csv"), sheet=f.get("sheet"))
        return to_results(raw, f.get("county_col", "county"), f.get("dem_col", "dem"),
                          f.get("rep_col", "rep"), f.get("pct_col"), f.get("long_format"))
    if f.get("kind") == "file":
        return _read(os.path.join(folder, f.get("path", "results.csv")))
    return None


def build_params(cfg: dict) -> Params:
    kw = dict(cfg.get("params") or {})
    if cfg.get("poll_margin") is not None:
        kw["poll_margin"] = cfg["poll_margin"]
    h = cfg.get("rcv_history")                      # past ranked-choice contests -> transfer skew
    hdf = _read(h) if h else None
    if hdf is not None and "rcv_to_d" not in kw:
        from rcv import estimate_transfers
        _, pooled = estimate_transfers(hdf)
        kw["rcv_to_d"], kw["rcv_to_r"] = pooled["to_d"], pooled["to_r"]
    return Params(**kw)


def run(config_path: str, out_path: str, log_path: str, only: str | None = None) -> dict:
    with open(config_path) as fh:
        cfg = json.load(fh)
    old = {}
    if os.path.exists(out_path):
        try:
            old = json.load(open(out_path)).get("races", {})
        except Exception:
            old = {}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    # Top-rated-pollster averages (PROMPTS.md Prompt D): used when a race has no poll_margin of its own.
    pin = _read(cfg.get("poll_inputs", "data/poll_inputs_2026.csv"))
    pollmap = {}
    if pin is not None and {"id", "poll_margin"} <= set(pin.columns):
        pollmap = {str(k): float(v) for k, v in zip(pin["id"], pin["poll_margin"]) if pd.notna(v)}
    races: dict = {}
    new_log = not os.path.exists(log_path)
    with open(log_path, "a", newline="") as lf:
        w = csv.writer(lf)
        if new_log:
            w.writerow(["timestamp", "id", "pct_in", "median", "p10", "p90", "win_prob"])
        for r in cfg.get("races", []):
            rid = r["id"]
            if only and rid != only:
                races[rid] = old.get(rid, {})
                continue
            meta = {k: r.get(k) for k in ("state", "race", "level")}
            prev = old.get(rid, {})
            folder = r.get("dir", f"data/{rid}")
            counties = _read(os.path.join(folder, "counties.csv"))
            if counties is None:
                races[rid] = {"meta": meta, "status": "no baseline file (counties.csv)", "checked": now,
                              "summary": prev.get("summary"), "as_of": prev.get("as_of")}
                continue
            try:
                early = load_early(r, folder)
                results = load_results(r, folder)
                rr = dict(r)
                if rr.get("poll_margin") is None and rid in pollmap:
                    rr["poll_margin"] = pollmap[rid]
                s = project(counties, early, results, build_params(rr))
                races[rid] = {"meta": meta, "status": "ok", "checked": now, "as_of": now,
                              "summary": to_json_summary(s)}
                w.writerow([now, rid, round(s["pct_in"], 2), round(s["median"], 2), round(s["p10"], 2),
                            round(s["p90"], 2), round(s["win_prob"], 3)])
            except Exception as ex:  # keep last good numbers, flag the problem
                traceback.print_exc()
                races[rid] = {"meta": meta, "status": f"feed/model error: {ex}", "checked": now,
                              "summary": prev.get("summary"), "as_of": prev.get("as_of")}
    payload = {"updated": now, "races": races}
    write_json_atomic(out_path, payload)
    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/races.json")
    ap.add_argument("--out", default="data/latest.json")
    ap.add_argument("--log", default="data/needle_log.csv")
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    if not os.path.exists(a.config):
        sys.exit(f"missing {a.config}")
    p = run(a.config, a.out, a.log, a.only)
    for rid, v in p["races"].items():
        s = v.get("summary")
        line = f"{rid}: {v.get('status')}"
        if s:
            line += f" | {s['pct_in']:.0f}% in, margin {s['median']:+.1f}, Dem win {s['win_prob'] * 100:.0f}%"
        print(line)
