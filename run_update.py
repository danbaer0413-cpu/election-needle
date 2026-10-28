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
import sources
import statewide_mode
import house_live
import sheet_inbox
from model import Params, project
from publish import to_json_summary, write_json_atomic


def _read(path):
    """CSV as a DataFrame, or None if the file is missing, empty or header-only."""
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return None
    df = pd.read_csv(path)
    return df if len(df) else None


import votehub_feed
STATE_NAMES = {"AK": "Alaska", "FL": "Florida", "GA": "Georgia", "IA": "Iowa", "KS": "Kansas", "ME": "Maine", "MI": "Michigan",
               "MN": "Minnesota", "MS": "Mississippi", "NE": "Nebraska", "NH": "New Hampshire", "NV": "Nevada", "OH": "Ohio",
               "SC": "South Carolina", "TX": "Texas", "WI": "Wisconsin", "NC": "North Carolina"}


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


def load_feedmap(path="config/feeds.csv"):
    df = _read(path)
    if df is None or "id" not in df:
        return {}
    return {str(r["id"]): r for r in df.to_dict("records") if str(r.get("url", "")).strip() not in ("", "nan")}


def load_results(cfg: dict, folder: str, rid: str = "", feedmap=None):
    """Order: config/feeds.csv URL -> races.json feed -> data/<race>/results.csv (paste/manual). A failing
    URL falls back to the results.csv file, so a dead feed never blanks the needle."""
    fm = (feedmap or {}).get(rid)
    if fm is not None:
        try:
            from feeds import load_feed
            df = load_feed(fm)
            if df is not None and len(df):
                return df
        except Exception as ex:
            print(f"  feed for {rid} failed ({ex}); falling back to results.csv")
        return _read(os.path.join(folder, "results.csv"))
    f = cfg.get("feed") or {}
    if f.get("kind") == "url" and f.get("url"):
        raw = fetch_table(f["url"], f.get("fmt", "csv"), sheet=f.get("sheet"))
        return to_results(raw, f.get("county_col", "county"), f.get("dem_col", "dem"),
                          f.get("rep_col", "rep"), f.get("pct_col"), f.get("long_format"))
    if f.get("kind") == "file":
        return _read(os.path.join(folder, f.get("path", "results.csv")))
    return _read(os.path.join(folder, "results.csv"))


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
    pollmap, auto_m, manual_m, npolls = {}, {}, {}, {}
    try:
        perr = json.load(open("config/poll_error.json"))     # historical polling error (poll_error_fit.py)
    except Exception:
        perr = None
    # automatic pull first, then the hand-entered file wins where it has a race (manual override)
    for label, pf, store in (("auto", cfg.get("poll_inputs_auto", "data/poll_inputs_auto.csv"), auto_m),
                             ("manual", cfg.get("poll_inputs", "data/poll_inputs_2026.csv"), manual_m)):
        pin = _read(pf)
        if pin is not None and {"id", "poll_margin"} <= set(pin.columns):
            store.update({str(k): float(v) for k, v in zip(pin["id"], pin["poll_margin"]) if pd.notna(v)})
            if "n_polls" in pin.columns:
                for k_, n_ in zip(pin["id"], pin["n_polls"]):
                    if pd.notna(n_):
                        npolls[(label, str(k_))] = float(n_)
    pollmap.update(auto_m); pollmap.update(manual_m)
    both = sorted(set(auto_m) & set(manual_m))
    if both:                                # tell you when the live poll pull and your hand-entered numbers drift apart
        cmp_rows = [(i, manual_m[i], auto_m[i], round(auto_m[i] - manual_m[i], 2)) for i in both]
        with open("data/poll_compare.csv", "w", newline="") as cf:
            cw = csv.writer(cf); cw.writerow(["id", "manual", "auto", "auto_minus_manual"]); cw.writerows(cmp_rows)
        for i, m_, a_, d_ in cmp_rows:
            if abs(d_) >= 1.5:
                print(f"  POLL DRIFT {i}: manual {m_:+.1f} vs live pull {a_:+.1f} (diff {d_:+.1f}); refresh your numbers?")
    try:                                    # fundamentals prior (structure only; small weight, see FUNDAMENTALS.md)
        from fundamentals import compute as _fund
        fundmap = _fund(out=None)
    except Exception as ex:
        print(f"  fundamentals unavailable ({ex}); running without them")
        fundmap = {}
    try:                                    # electorate model: state-specific deviation from the national swing adjusts the fundamentals prior (no extra weight)
        import electorate
        _rows = []
        for _r in cfg.get("races", []):
            _c = _read(os.path.join(_r.get("dir", f"data/{_r['id']}"), "counties.csv"))
            if _c is not None and len(_c):
                _v = pd.to_numeric(_c["exp_votes"], errors="coerce").fillna(0.0)
                _m = pd.to_numeric(_c["base_margin"], errors="coerce").fillna(0.0)
                _rows.append((_r["id"], _r["state"], float((_v * _m).sum() / max(_v.sum(), 1.0)), float(_v.sum())))
        _swing = electorate.compute(_rows)
        _nat = electorate.national_swing()
        for _rid, _s in _swing.items():
            if _rid in fundmap:
                fundmap[_rid] = (round(fundmap[_rid][0] + (_s - _nat), 2), fundmap[_rid][1])
        print(f"  electorate model: adjusted {len(_swing)} fundamentals priors (national swing {_nat:.1f})")
    except Exception as ex:
        print(f"  electorate model skipped ({str(ex)[:100]})")
    olean = {}
    try:
        _ol = _read("config/other_lean.csv")
        if _ol is not None:
            olean = {x["race"]: (float(x["other_lean"]), float(x["sd_other"])) for x in _ol.to_dict("records")}
    except Exception:
        olean = {}
    try:
        vh_on = votehub_feed.enabled()
        vh_rows, vh_map = (votehub_feed.load(), votehub_feed.load_map()) if vh_on else ({}, {})
    except Exception as ex:
        vh_on, vh_rows, vh_map = False, {}, {}
        print(f"  VoteHub feed skipped ({str(ex)[:100]})")
    vh_swing = vh_on and votehub_feed.swing_on()
    vh_pending: dict = {}
    feedmap = load_feedmap(cfg.get("feeds", "config/feeds.csv"))
    races: dict = {}
    jobs: dict = {}
    new_log = not os.path.exists(log_path)
    with open(log_path, "a", newline="") as lf:
        w = csv.writer(lf)
        if new_log:
            w.writerow(["timestamp", "id", "pct_in", "median", "p10", "p90", "win_prob"])
        try:
            sheet_inbox.sync(cfg.get("races", []))
            sheet_inbox.sync_early(cfg.get("races", []))
        except Exception as ex:
            print(f"  election-night sheet skipped ({str(ex)[:100]})")
        try:
            house_live.refresh()
        except Exception as ex:
            print(f"  house reader skipped ({str(ex)[:100]})")
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
                vh_kw, vh_info = {}, {}
                if vh_on and r.get("state_name", STATE_NAMES.get(r.get("state"))) in vh_rows:
                    sn = r.get("state_name", STATE_NAMES.get(r.get("state")))
                    early = votehub_feed.adjust_early(early, counties, vh_rows[sn])
                    vh_kw, vh_info = votehub_feed.params_for(rid, sn, vh_rows, vh_map, early)
                results = load_results(r, folder, rid, feedmap)
                extra, sw_auto = sources.load_race(rid)
                results = sources.merge_results(results, extra)
                hp = house_live.county_pct_for(r.get("state"), counties["county"])
                if hp:
                    print(f"  {rid}: House progress gives % counted for {len(hp)} counties")
                results = statewide_mode.build(counties, results, folder, rid, statewide=sw_auto, extra_pct=hp)
                rr = dict(r)
                if rr.get("poll_margin") is None and rid in pollmap:
                    rr["poll_margin"] = pollmap[rid]
                if rr.get("poll_margin") is None and (results is None or not len(results)):
                    races[rid] = {"meta": meta, "status": "baseline ready, waiting for polls", "checked": now,
                                  "summary": prev.get("summary"), "as_of": prev.get("as_of")}
                    continue
                if perr and rr.get("poll_margin") is not None and "poll_bias" not in (rr.get("params") or {}):
                    src = "manual" if rid in manual_m else "auto"
                    n_ = npolls.get((src, rid), 4.0 if src == "manual" else 1.0)   # a hand-typed Silver average is a broad average
                    sd_ = (perr["sd_by_polls"].get("4+") if n_ >= 4 else perr["sd_by_polls"].get("<4")) or perr["sd_default"]
                    sb_ = 0.0 if rid in perr.get("skip_state_bias", []) else perr["state_bias"].get(rr.get("state"), 0.0)
                    rr["params"] = dict(rr.get("params") or {}, poll_bias=round(perr["global_bias"] + sb_ + perr.get("race_bias", {}).get(rid, 0.0), 2),
                                        sd_poll=max(perr.get("sd_floor", 3.5), sd_))
                if rid in olean and "other_lean" not in (rr.get("params") or {}):
                    rr["params"] = dict(rr.get("params") or {}, other_lean=olean[rid][0], sd_other=olean[rid][1])
                if rid in fundmap and "fund_margin" not in (rr.get("params") or {}):
                    rr["params"] = dict(rr.get("params") or {}, fund_margin=fundmap[rid][0], sd_fund=fundmap[rid][1])
                if vh_kw:
                    rr["params"] = dict(rr.get("params") or {}, **vh_kw)
                s = project(counties, early, results, build_params(rr))
                if vh_info:
                    s.setdefault("inputs", {})["votehub"] = vh_info
                    rr["_vh_info"] = vh_info
                jobs[rid] = (counties, early, results, rr, meta)
                races[rid] = {"meta": meta, "status": "ok", "checked": now, "as_of": now,
                              "summary": to_json_summary(s)}
                if vh_info.get("modeled") and vh_swing and s.get("inputs", {}).get("early_pool_expected") is not None:
                    vh_pending[rid] = (s, vh_info)
            except Exception as ex:  # keep last good numbers, flag the problem
                traceback.print_exc()
                races[rid] = {"meta": meta, "status": f"feed/model error: {ex}", "checked": now,
                              "summary": prev.get("summary"), "as_of": prev.get("as_of")}

    # ---- VoteHub modeled vote as a bounded swing signal (needs several states to remove their house bias) ----
    if vh_pending:
        try:
            import numpy as _np
            sp = "data/votehub_state.json"
            prev_eff = json.load(open(sp)) if os.path.exists(sp) else {}
            step = votehub_feed.STEP
            devs = {rid: info["early_margin"] - s0["inputs"]["early_pool_expected"] - s0["swing"] for rid, (s0, info) in vh_pending.items()}
            if len(devs) >= 3:
                bias = float(_np.median(list(devs.values())))
                new_eff = dict(prev_eff)
                for rid, (s0, info) in vh_pending.items():
                    counties, early, results, rr, meta = jobs[rid]
                    rr["params"] = dict(rr.get("params") or {}, vh_early_margin=info["early_margin"] - bias, vh_scale=1.0)
                    s1 = project(counties, early, results, build_params(rr))
                    eff = s1["median"] - s0["median"]
                    prv = float(prev_eff.get(rid, 0.0))
                    tgt = min(max(eff, prv - step), prv + step)
                    if abs(eff - tgt) > 0.01:
                        rr["params"]["vh_scale"] = max(0.0, min(1.0, tgt / eff)) if eff * tgt > 0 else 0.0
                        s1 = project(counties, early, results, build_params(rr))
                        eff = s1["median"] - s0["median"]
                    info = dict(info, bias=round(bias, 1), effect=round(eff, 2), states=len(devs))
                    s1.setdefault("inputs", {})["votehub"] = info
                    rr["_vh_info"] = info
                    races[rid]["summary"] = to_json_summary(s1)
                    new_eff[rid] = round(eff, 3)
                    print(f"  VoteHub swing signal {rid}: {eff:+.2f} pts (their house bias {bias:+.1f} removed, {len(devs)} states)")
                write_json_atomic(sp, new_eff)
            else:
                print(f"  VoteHub swing signal waits for 3+ states with modeled votes (have {len(devs)})")
        except Exception as ex:
            traceback.print_exc()
            print(f"  VoteHub swing signal skipped ({str(ex)[:100]})")

    # ---- cross-race adjustment: races counted bluer/redder than expected move the races still out ----
    try:
        import cross_race
        from dataclasses import replace
        ccfg = cross_race.load_cfg()
        items = {}
        for rid, (counties, early, results, rr, meta) in jobs.items():
            sm_ = (races.get(rid) or {}).get("summary") or {}
            if sm_.get("pct_in") is None:
                continue
            sur = None
            if sm_["pct_in"] >= ccfg["min_pct_in"]:
                prior = project(counties, early, None, build_params(rr))["median"]
                sur = sm_["median"] - prior
            items[rid] = dict(state=meta.get("state"), pct_in=sm_["pct_in"], surprise=sur)
        shifts = cross_race.compute_shifts(items, ccfg)
        for rid, sh in shifts.items():
            if abs(sh) < 0.05 or items[rid]["pct_in"] >= 99.5:
                continue
            counties, early, results, rr, meta = jobs[rid]
            p_ = build_params(rr)
            if p_.poll_margin is None and p_.fund_margin is None:
                continue
            kw_ = {}
            if p_.poll_margin is not None:
                kw_["poll_bias"] = p_.poll_bias + sh
            if p_.fund_margin is not None:
                kw_["fund_margin"] = p_.fund_margin + sh
            s2 = project(counties, early, results, replace(p_, **kw_))
            if jobs[rid][3].get("_vh_info"):
                s2.setdefault("inputs", {})["votehub"] = jobs[rid][3]["_vh_info"]
            races[rid]["summary"] = to_json_summary(s2)
            races[rid]["summary"]["cross_race_shift"] = round(sh, 2)
            print(f"  cross-race: {rid} prior moved {sh:+.1f} (from counted races) -> median {s2['median']:+.1f}")
        if shifts:
            for rid, it in items.items():
                if it["surprise"] is not None:
                    races[rid].setdefault("summary", {})["surprise"] = round(it["surprise"], 2)
    except Exception as ex:
        print(f"  cross-race adjustment skipped ({ex})")
    try:
        import control
        import cross_race as _cr
        rho = _cr.load_cfg().get("rho_shared", 0.5)
        ctl = control.simulate(races, rho)
    except Exception as ex:
        print(f"  control summary skipped ({ex})"); ctl = {}
    try:        # the log records the FINAL numbers of this run (after VoteHub and cross-race steps), so 'what changed' compares like with like
        with open(log_path, "a", newline="") as lf2:
            w2 = csv.writer(lf2)
            for rid_, r_ in races.items():
                s_ = r_.get("summary")
                if s_ and r_.get("status") == "ok" and s_.get("median") is not None:
                    w2.writerow([now, rid_, round(s_["pct_in"], 2), round(s_["median"], 2), round(s_["p10"], 2),
                                 round(s_["p90"], 2), round(s_["win_prob"], 3)])
    except Exception as ex:
        print(f"  could not write needle log ({ex})")
    payload = {"updated": now, "races": races, "control": ctl}
    write_json_atomic(out_path, payload)
    try:                                   # House lean map + seat chart data (separate file; never affects the needles)
        import house_lean
        house_lean.build_and_save()
    except Exception as ex:
        print(f"  house lean skipped ({str(ex)[:120]})")
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
