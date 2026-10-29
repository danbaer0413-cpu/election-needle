"""Plain-language explanation of a projection: what was inputted, what moves the needle."""
from __future__ import annotations

import pandas as pd

LABELS = {
    "polls": "Polling prior",
    "no polls": "No-poll prior",
    "early party reg": "Early vote: party registration",
    "early geography": "Early vote: where ballots are coming from",
    "counted": "Counted votes",
}
TIER_NOTE = {"Solid D": "Solid D", "Lean D": "Lean D", "Toss-up": "Toss-up",
             "Lean R": "Lean R", "Solid R": "Solid R"}


def _dr(x: float) -> str:
    return "Even" if abs(x) < 0.05 else f"{'D' if x > 0 else 'R'}+{abs(x):.1f}"


def _pts(x: float) -> str:
    """A shift in points, named by who it favors (e.g. 'D+1.2')."""
    return _dr(x)


def _votes(x: float) -> str:
    return f"{x:+,.0f}"


def _tiers(s: dict) -> pd.DataFrame:
    t = s.get("tiers")
    return t if isinstance(t, pd.DataFrame) else pd.DataFrame(t or [])


def inputs_lines(s: dict) -> list[str]:
    i = s.get("inputs") or {}
    if not i:
        return ["No input summary available."]
    L = []
    if i.get("poll_margin") is None:
        L.append("**Polls:** none entered, so the starting point is the baseline with a wide range.")
    else:
        extra = []
        if i.get("poll_bias"):
            extra.append(f"history-based bias {_pts(i['poll_bias'])}")
        if i.get("poll_skew"):
            extra.append(f"skew shape {i['poll_skew']:+.1f}")
        L.append(f"**Polls:** average margin {_dr(i['poll_margin'])}, polling-error "
                 f"spread {i['sd_poll']:.1f}" + (f", {', '.join(extra)}" if extra else "") + ".")
    L.append(f"**Baseline:** statewide margin {_dr(i['baseline_margin'])} built from {i['units']} reporting units.")
    if i["units_with_early"]:
        pct = i["early_returned"] / max(i["early_expected_final"], 1) * 100
        kind = "party registration and geography" if i["early_party_data"] else "geography only (no party data)"
        L.append(f"**Early/mail vote:** {i['early_returned']:,.0f} ballots returned in {i['units_with_early']} units, "
                 f"about {pct:.0f}% of the expected final early vote; signals used: {kind}. "
                 f"Turnout adjustment x{i['turnout_mult']:.2f}.")
        L.append(f"**Early vs Election Day gap assumed:** {i['early_gap']:.1f} points more Democratic; "
                 f"{'early votes are reported first' if i['early_first'] else 'early and Election Day votes are mixed'}.")
    else:
        L.append("**Early/mail vote:** none loaded.")
    vh = i.get("votehub")
    if vh:
        t = f"**VoteHub (as of {vh.get('as_of')}):** {vh.get('total') or 0:,.0f} ballots cast"
        if vh.get("pct_of_final"):
            t += f", {vh['pct_of_final']:.1f}% of their projected final turnout of {vh.get('implied_final') or 0:,.0f} (about {(vh.get('implied_final') or 0) - (vh.get('total') or 0):,.0f} still to come)"
        if vh.get("early_margin") is not None:
            t += f"; their modeled vote of ballots cast {vh.get('dem')} vs {vh.get('rep')} = {_dr(vh['early_margin'])} two-party among ballots cast ({('used as a bounded signal: their house bias of ' + format(vh['bias'], '+.1f') + ' removed across ' + str(vh['states']) + ' states, effect on the median ' + format(vh['effect'], '+.2f') + ' pts') if vh.get('effect') is not None else 'shown; used only once 3+ states have posted'})"
        if vh.get("rating"):
            t += f"; their rating: {vh['rating']} (display only)"
        L.append(t + ".")
    if i["counted"] > 0:
        L.append(f"**Counted:** {i['counted']:,.0f} votes, {i['counted'] / max(i['expected_total'], 1) * 100:.0f}% of "
                 f"expected, {i['units_reporting']} units reporting ({i['units_final']} complete).")
    else:
        L.append("**Counted:** nothing yet.")
    if i.get("rcv"):
        L.append(f"**Ranked-choice:** other candidates hold {i['third_share'] * 100:.1f}% of first-round ballots; "
                 f"{i['rcv_to_d'] * 100:.0f}% assumed to end with D, {i['rcv_to_r'] * 100:.0f}% with R, "
                 f"{max(1 - i['rcv_to_d'] - i['rcv_to_r'], 0) * 100:.0f}% exhausted.")
    if i.get("runoff_rule"):
        L.append(f"**Runoff rule:** a candidate needs a majority of all ballots; other candidates hold "
                 f"{i['third_share'] * 100:.1f}%.")
    warn = []
    if not i["units_with_early"] and i["counted"] == 0:
        warn.append("No early-vote or results data yet: this is only the polling prior and baseline.")
    if i["units_with_early"] and not i["early_party_data"]:
        warn.append("No party registration on the early file, so the early signal is weaker.")
    if i["poll_margin"] is None:
        warn.append("No polling average entered.")
    return L + [f":warning: {w}" for w in warn]


def drivers_lines(s: dict) -> list[str]:
    L = [f"Estimated swing vs baseline: **{_pts(s['swing'])}** (±{s['swing_sd']:.1f})."]
    for d in sorted(s.get("drivers") or [], key=lambda d: -d["weight"]):
        L.append(f"- {LABELS.get(d['source'], d['source'])}: points to {_pts(d['swing'])}, "
                 f"{d['weight']:.0f}% of the estimate")
    i = s.get("inputs") or {}
    if i:
        out = i["outstanding_share"]
        L.append(f"{out * 100:.0f}% of the expected vote is still out, so a 1-point miss in how it breaks "
                 f"moves the final margin about {out:.2f} points.")
    return L


def firewall_lines(s: dict) -> list[str]:
    t = _tiers(s)
    if t.empty:
        return ["No unit breakdown yet."]
    c, r = t["counted_net"].sum(), t["remaining_net"].sum()
    L = [f"Net votes (Dem minus GOP): counted **{_votes(c)}**, still expected from outstanding votes "
         f"**{_votes(r)}**, projected final **{_votes(c + r)}**."]
    for row in t.itertuples():
        if row.remaining > 0:
            L.append(f"- **{TIER_NOTE.get(row.tier, row.tier)} firewall:** {_votes(row.remaining_net)} net votes expected "
                     f"from {row.remaining:,.0f} outstanding votes in {row.units} units "
                     f"(counted so far {_votes(row.counted_net)}).")
    tab = s.get("table")
    if isinstance(tab, pd.DataFrame) and len(tab):
        top = tab.sort_values("remaining", ascending=False).head(3)
        bits = [f"{x.county} ({x.remaining:,.0f} out, projected {_dr(x.proj_margin)})" for x in top.itertuples()
                if x.remaining > 0]
        if bits:
            L.append("Biggest outstanding piles: " + "; ".join(bits) + ".")
    return L


def outcome_lines(s: dict) -> list[str]:
    L = []
    o = s.get("outcome")
    if o:
        L.append(f"Majority rule: Dem wins outright {o['p_d_outright'] * 100:.0f}%, GOP wins outright "
                 f"{o['p_r_outright'] * 100:.0f}%, **runoff {o['p_runoff'] * 100:.0f}%**."
                 + (f" If it goes to a runoff, Dem wins about {o['p_d_wins_runoff_given'] * 100:.0f}%."
                    if o.get("p_d_wins_runoff_given") is not None else ""))
    fr = s.get("first_round")
    if fr:
        L.append(f"Ranked-choice: first-round margin about {_dr(fr['median'])} (Dem win {fr['win_prob'] * 100:.0f}%); "
                 f"after transfers {_dr(s['median'])} (Dem win {s['win_prob'] * 100:.0f}%).")
    return L


SRC_TEXT = {
    "polls": "Polling average",
    "no polls": "No polls (baseline only)",
    "fundamentals": "National environment (generic ballot)",
    "early party reg": "Early vote: party mix of returned ballots",
    "early geography": "Early vote: which counties are voting",
    "votehub": "VoteHub early-vote model",
    "counted": "Votes counted so far",
}


def behind_lines(s: dict, pa_avg: float | None = None) -> list[str]:
    """Plain-language table: each source, what it says, how much it counts."""
    drv = sorted(s.get("drivers") or [], key=lambda d: -d["weight"])
    base = (s.get("inputs") or {}).get("baseline_margin")
    dr = lambda x: "Even" if abs(x) < 0.05 else f"{'D' if x > 0 else 'R'}+{abs(x):.1f}"
    L = []
    if base is not None:
        m, sd = float(s["median"]), float(s.get("swing_sd") or 0)
        head = f"**Model: {dr(m)}**, start point {dr(base)}"
        if pa_avg is not None:
            diff = m - pa_avg
            head += f"; polling average {dr(pa_avg)}, so the other evidence moves it **{abs(diff):.1f} pts toward {'Democrats' if diff > 0 else 'Republicans'}**" if abs(diff) >= 0.05 else f"; polling average {dr(pa_avg)}, the same as the model"
        L.append(head + ".")
    if drv:
        L.append("\n| Source | What it says | Share of the estimate |\n|---|---|---|")
        for d in drv:
            name = SRC_TEXT.get(d["source"], LABELS.get(d["source"], d["source"]))
            L.append(f"| {name} | {dr(float(d['swing']) + float(base or 0))} | {d['weight']:.0f}% |")
    i = s.get("inputs") or {}
    if i:
        L.append(f"Early vote loaded: {i.get('early_returned', 0):,.0f} ballots"
                 + ("; party data used, but capped so it can't swing the result more than 1.5 pts." if i.get("early_party_data")
                    else "; no party data, so only geography is read.")
                 + f" About {i.get('outstanding_share', 0) * 100:.0f}% of the vote is still out.")
    _p = performance_line(s)
    if _p:
        L.append(_p)
    L.append("The rating (Toss-up, Tilt, Lean, Likely, Solid) comes from the model win chance; polls can miss by 5+ points, so treat it as a lean, not a lock.")
    return L


def performance_line(s: dict) -> str | None:
    """One line: is the statewide count running more Democratic or Republican than expected, and which counties drive it."""
    t = s.get("table")
    if not isinstance(t, pd.DataFrame) or "vs_expected" not in t or "counted" not in t:
        return None
    t = t[t["counted"] > 0]
    if t.empty or float(t["counted"].sum()) <= 0:
        return None
    w = t["counted"].astype(float)
    avg = float((t["vs_expected"] * w).sum() / w.sum())
    side = "more Democratic" if avg > 0 else "more Republican"
    if abs(avg) < 0.3:
        return "So far the count is running about as expected statewide."
    big = t.assign(push=(t["vs_expected"] * w) * (1 if avg > 0 else -1)).sort_values("push", ascending=False)
    names = [f"{r.county} ({_pts(r.vs_expected)})" for r in big.head(2).itertuples() if r.push > 0]
    return (f"So far the count is running **{abs(avg):.1f} points {side} than expected** statewide"
            + (f", led by {' and '.join(names)}." if names else "."))
