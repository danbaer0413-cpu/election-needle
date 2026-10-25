"""Our own polling average + trend chart data, built from every poll we collect (PollResults + Bluesky).

    python polling_average.py            (also called by fetch_polls.py)

Reads  data/polls_all.csv   id,pollster,end,n,d,r,source   (fetch_polls.py appends to it every run, de-duplicated)
Writes data/poll_average.json   per race: today's average, 80% band, n_polls, effective n, daily series, and the poll dots.

Method (kept simple on purpose, so every number can be explained):
  margin   two-party (D-R)/(D+R)*100 per poll, then house-effect adjusted: minus half of the pollster's historical bias
           (Silver Bulletin 'Bias', shrunk 50% because bias estimates are noisy).
  weight   quality x sample size x recency x repeat-pollster discount
             quality   from Silver Bulletin's Predictive Plus-Minus (pm, expected extra points of error; lower = better):
                       (4.6 / (4.6 + pm))^2, so the best firms (pm about -1.1) count 1.7, an average firm 1.0, a weak one (pm +1.3) 0.6.
                       Grade table used only if pm is missing: A+/A 1.0, A- .9, A/B .85, B+ .8, B .6, B- .5, B/C .4, C+ .3, C .25, C/D .15,
                       D .1; unrated pollsters are EXCLUDED (no Silver Bulletin rating = not used); F / banned 0
             sample    sqrt(n/600), capped 0.7 - 1.6
             recency   exp(-age/10 days)   (a 10-day-old poll counts about 37%)
             repeats   a pollster with k recent polls: each counts 1/sqrt(k), so one firm cannot dominate
  band     80% range = +/- 1.28 * 4.4 / sqrt(effective n); 4.4 pts is the typical miss of final poll averages in 2018/2022.
Unlike the tier rule used for the model input (fetch_polls.average), this uses ALL graded polls with weights, so it
leans less on one or two firms in thinly-polled races. The Tier rule still feeds the needle unless you change that.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import date, timedelta

import pandas as pd

GRADE_W = {"A+": 1.0, "A": 1.0, "A-": 0.9, "A/B": 0.85, "B+": 0.8, "B": 0.6, "B-": 0.5, "B/C": 0.4, "C+": 0.3,
           "C": 0.25, "C/D": 0.15, "D+": 0.1, "D": 0.1, "D-": 0.1, "F": 0.0}
TAU, SIGMA, UNRATED = 10.0, 4.4, 0.0


def prepare(polls: pd.DataFrame, grades: pd.DataFrame | None, match) -> pd.DataFrame:
    """polls: id,pollster,end,n,d,r. match(name, grades_dict) -> (key, grade). Adds margin/grade/bias/key."""
    p = polls.copy()
    p["end"] = pd.to_datetime(p["end"]).dt.date
    p["margin"] = (p["d"] - p["r"]) / (p["d"] + p["r"]) * 100
    gd = dict(zip(grades["pollster"].astype(str), grades["grade"].astype(str))) if grades is not None else {}
    bias = dict(zip(grades["pollster"].astype(str), grades["bias_dem"])) if grades is not None and "bias_dem" in grades else {}
    from fetch_polls import _norm
    pm_by = {_norm(a): b for a, b in zip(grades["pollster"].astype(str), grades["predictive_pm"])} if grades is not None and "predictive_pm" in grades else {}
    bias_by = {_norm(a): b for a, b in bias.items()}
    keys, gr, bs, pms = [], [], [], []
    for name in p["pollster"]:
        k, g = match(name, gd)
        keys.append(k); gr.append(g)
        b = bias_by.get(k)
        bs.append(float(b) if g is not None and b is not None and pd.notna(b) else 0.0)
        pm = pm_by.get(k)
        pms.append(float(pm) if g is not None and pm is not None and pd.notna(pm) else None)
    p["key"], p["grade"], p["bias"], p["pm"] = keys, gr, bs, pms
    p = p[p["grade"].notna() & (p["grade"] != "F")].copy()            # unrated or banned: left out entirely, dots included
    p["adj"] = p["margin"] - 0.5 * p["bias"]
    return p


def _w_static(row) -> float:
    if row["grade"] == "F":
        g = 0.0
    elif row.get("pm") is not None and pd.notna(row.get("pm")):
        g = (4.6 / max(2.5, 4.6 + float(row["pm"]))) ** 2
    else:
        g = GRADE_W.get(row["grade"], UNRATED) if row["grade"] is not None else UNRATED
    n = row["n"] if pd.notna(row["n"]) and row["n"] > 0 else 600.0
    return g * min(1.6, max(0.7, math.sqrt(n / 600.0)))


def average_on(p: pd.DataFrame, day: date):
    q = p[p["end"] <= day].copy()
    q["age"] = q["end"].map(lambda e: (day - e).days)
    q = q[q["age"] <= 60]
    if q.empty:
        return None
    q["w"] = q.apply(_w_static, axis=1) * q["age"].map(lambda a: math.exp(-a / TAU))
    recent = q[q["age"] <= 21].groupby("key").size()
    q["w"] = q["w"] / q["key"].map(lambda k: math.sqrt(max(1, recent.get(k, 1))))
    q = q[q["w"] > 1e-6]
    if q.empty or q["w"].sum() <= 0:
        return None
    sw = q["w"].sum()
    avg = float((q["w"] * q["adj"]).sum() / sw)
    n_eff = float(sw ** 2 / (q["w"] ** 2).sum())
    half = 1.28 * SIGMA / math.sqrt(max(n_eff, 1.0))
    return dict(avg=round(avg, 2), lo=round(avg - half, 2), hi=round(avg + half, 2), n_eff=round(n_eff, 1), q=q)


def build(polls: pd.DataFrame, grades, match, today: date | None = None, start: date = date(2026, 6, 1)) -> dict:
    today = today or date.today()
    out = {}
    for rid, g in polls.groupby("id"):
        p = prepare(g, grades, match)
        now = average_on(p, today)
        if now is None:
            continue
        first = max(start, min(p["end"]))
        series, d = [], first
        while d <= today:
            a = average_on(p, d)
            if a:
                series.append(dict(date=d.isoformat(), avg=a["avg"], lo=a["lo"], hi=a["hi"]))
            d += timedelta(days=1)
        q = now["q"]
        pts = []
        for _, row in p[p["end"] >= first].iterrows():
            w = _w_static(row) * math.exp(-(today - row["end"]).days / TAU)
            pts.append(dict(date=row["end"].isoformat(), pollster=row["pollster"], grade=row["grade"] or "unrated",
                            margin=round(float(row["margin"]), 1), weight=round(float(w), 3)))
        out[rid] = dict(as_of=today.isoformat(), avg=now["avg"], lo=now["lo"], hi=now["hi"], n_eff=now["n_eff"],
                        n_polls=int(len(q)), series=series, points=pts)
    return out


def main(polls_path="data/polls_all.csv", out_path="data/poll_average.json", grades_path="data/pollster_grades.csv"):
    from fetch_polls import _match
    if not os.path.exists(polls_path):
        print("no polls_all.csv yet; nothing to average"); return {}
    polls = pd.read_csv(polls_path)
    grades = pd.read_csv(grades_path) if os.path.exists(grades_path) else None
    res = build(polls, grades, _match)
    json.dump(res, open(out_path, "w"))
    for k, v in sorted(res.items()):
        print(f"{k:14s} our average {v['avg']:+6.2f}  ({v['lo']:+.1f} to {v['hi']:+.1f})  {v['n_polls']} polls, n_eff {v['n_eff']}")
    return res


if __name__ == "__main__":
    try:
        main(*sys.argv[1:4])
    except Exception as ex:
        print("polling_average failed:", ex)
