"""
Election needle model (numpy/pandas only).

Margins are Democratic minus Republican, in percentage points of the
two-party vote. Positive = Dem lead.

Inputs (DataFrames):
  counties : county, region, base_margin, exp_votes, exp_early_share
             base_margin     = prior-cycle two-party margin for this county, already
                               adjusted to the race you are modelling
             exp_votes       = expected total two-party votes this year
             exp_early_share = expected share of votes cast early/by mail
  early    : county, early_returned, [d_reg, r_reg, o_reg]
             early_returned  = early + mail ballots returned so far
             d_reg/r_reg/o_reg = party registration of those returned ballots
                               (optional; many states publish this, some don't)
  results  : county, dem, rep, [final]
             votes counted so far; `final` = county is 100% complete

How it works
  final county margin = base_margin + S + region effect + county effect
    S              statewide swing vs. baseline
    region effect  shared by counties in a region
    county effect  county-specific leftover
  S starts from the polling prior, is updated by the early-vote signals
  (party-registration and geography), then by counted votes as they arrive.
  The vote still outstanding is split into early and Election Day pools; Election
  Day votes lean toward the GOP by `early_gap`.  A Monte Carlo over S, region
  effects, county effects and turnout gives the needle's range and win probability.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd


def two_party_margin(d, r):
    d = np.asarray(d, float)
    r = np.asarray(r, float)
    tot = d + r
    return np.where(tot > 0, (d - r) / np.where(tot > 0, tot, 1.0) * 100.0, 0.0)


@dataclass
class Params:
    # priors
    poll_margin: float | None = None   # statewide polling-average margin (D-R)
    sd_poll: float = 3.0               # how far the result can land from the polls
    sd_prior_nopoll: float = 5.0       # used when no poll is given
    fund_margin: float | None = None   # fundamentals prior (fundamentals.py): 2024 lean + national swing
    sd_fund: float = 10.5              # its out-of-sample error from the 2018/2022 backtest
    poll_bias: float = 0.0             # expected (actual - poll) for this state, from poll_error.py
    poll_skew: float = 0.0             # skew-normal shape of poll error (+ = long Dem-side tail)
    # structure
    tau_county: float = 2.5            # county-level spread around baseline+swing
    tau_region: float = 2.0            # region-level spread
    sigma_nonrep: float = 12.0         # error of a county's counted pool when little is in
    sd_remaining: float = 4.0          # extra county-level noise on outstanding votes
    slope_prior_sd: float = 0.12       # swing may differ by county lean: shift_i = S + beta*(m0_i - M0). beta is learned from counted counties; prior N(0, this).
                                       # 0.12 = a county 20 points bluer than the state moves 2.4 points more (or less) than average. 0 turns the slope off.
    # early vs Election Day
    early_gap_max: float = 20.0        # the early-vs-Election-Day gap can be raised to at most this when the early electorate is lopsided
    early_gap: float = 8.0             # early margin minus Election Day margin
    sd_gap: float = 3.0                # uncertainty on that gap
    early_first: bool = True           # state reports early/mail votes first
    early_final_pct_in: float = 0.85   # share of the FINAL early vote returned so far
    # VoteHub (votehub_feed.py)
    vh_final_turnout: float | None = None   # their projected final TOTAL turnout (ballots cast / share of projected final turnout)
    vh_early_margin: float | None = None    # two-party margin of their modeled vote among ballots cast so far
    early_geo_signal: bool = True           # False when the early table is only a statewide total spread over counties (no geography to read)
    vh_scale: float = 1.0                   # multiplies how far VoteHub's signal sits from the other evidence (run_update uses it to limit the move per update)
    vh_max_effect: float = 1.0              # VoteHub's modeled vote can move this race's statewide median by at most this many points
    sd_votehub: float = 9.0                 # how far that can miss the early-pool margin we expect (points); third-party model, uncalibrated, so wide
    # early-vote signals
    reg_loyalty: float = 0.92          # share of registered partisans voting their party
    party_bias: float = 0.0            # calibrate on a past cycle (points)
    other_lean: float = 4.0            # how many points MORE Democratic (D-R margin) unaffiliated/other voters are than the early pool overall.
                                       # default +4: exit polls had independents about 3.4 (2018) and 4.8 (2022) points MORE Democratic than the national House vote; Trump's approval among independents is ~20-25% in 2026 (see INDEPENDENTS.md). Set 0 for 'a wash'
    sd_other: float = 5.0              # uncertainty on that lean (points); widens the early party signal in states with many 'other' registrants
    sd_early_party: float = 3.5
    party_max_effect: float = 1.5      # early party-registration evidence can move the swing estimate by at most this many points (as for VoteHub)
    sd_floor_swing: float = 6.5        # the swing estimate never gets more certain than this before votes are counted (state polls miss by ~5 pts; signals share one national environment)
    sd_early_geo: float = 8.0          # was 3.0; geography of returns says little about the swing (see README Georgia notes)
    # turnout
    turnout_sd: float = 0.04           # statewide
    county_turnout_sd: float = 0.03
    # ballot rules
    third_share: float = 0.0           # share of ALL first-round ballots for candidates other than D and R
    rcv: bool = False                  # ranked-choice: other ballots transfer (Maine, Alaska)
    rcv_to_d: float = 0.5              # share of those ballots ending with D (calibrate with rcv.py)
    rcv_to_r: float = 0.5              # share ending with R (the rest exhaust)
    runoff_rule: bool = False          # majority required, else runoff (Georgia)
    runoff_threshold: float = 0.5
    runoff_shift: float = 0.0          # runoff margin shift vs the general, points (+ = toward D)
    runoff_sd: float = 3.0             # extra uncertainty in the runoff, points
    # simulation
    n_sims: int = 8000
    seed: int = 0


def norm_name(s) -> str:
    """Match key for unit names: case, 'County'/'Parish'/'Borough' suffix, 'Saint'/'St.' and punctuation
    don't matter. Independent cities ('Richmond city') keep their suffix on purpose."""
    s = re.sub(r"[-/]", " ", str(s).lower().strip()).replace(".", "")
    s = re.sub(r"\bsaint\b", "st", s)
    s = re.sub(r"\s+(county|parish|borough|census area)$", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _prepare(counties, early, results, p: Params) -> pd.DataFrame:
    df = counties.copy()
    df["county"] = df["county"].astype(str)
    df["_k"] = df["county"].map(norm_name)

    if early is not None and len(early):
        e = early.copy()
        e["_k"] = e["county"].astype(str).map(norm_name)
        df = df.merge(e.drop(columns=["county"]).drop_duplicates("_k"), on="_k", how="left")
    for c in ("early_returned", "d_reg", "r_reg", "o_reg"):
        if c not in df:
            df[c] = 0.0
        df[c] = df[c].fillna(0.0).astype(float)

    if results is not None and len(results):
        r = results.copy()
        r["_k"] = r["county"].astype(str).map(norm_name)
        df = df.merge(r.drop(columns=["county"]).drop_duplicates("_k"), on="_k", how="left")
    for c in ("dem", "rep"):
        if c not in df:
            df[c] = 0.0
        df[c] = df[c].fillna(0.0).astype(float)
    if "weight" not in df:
        df["weight"] = 1.0
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce").fillna(1.0).clip(0.01, 1.0)
    if "final" not in df:
        df["final"] = False
    df["final"] = df["final"].fillna(False).astype(bool)
    return df


def project(counties, early=None, results=None, p: Params | None = None) -> dict:
    p = p or Params()
    df = _prepare(counties, early, results, p)
    K = len(df)
    g = p.early_gap

    m0 = df["base_margin"].to_numpy(float)
    T0 = df["exp_votes"].to_numpy(float)
    w0 = df["exp_early_share"].clip(0.02, 0.98).to_numpy(float)
    exp_early0 = w0 * T0
    M0 = float((T0 * m0).sum() / T0.sum())  # baseline statewide margin

    # ---- turnout: let early returns nudge expected turnout (shrunk 50%) -------------
    E_ret = df["early_returned"].to_numpy(float)
    have_early = E_ret.sum() > 0
    if have_early and p.vh_final_turnout:
        # VoteHub's projected final turnout fixes how much early vote is still to come (shrunk 50% toward our baseline, as below)
        mult = 1.0 + 0.5 * (np.clip(p.vh_final_turnout / T0.sum(), 0.7, 1.4) - 1.0)
        E_final = E_ret * (exp_early0.sum() * mult / E_ret.sum())
    elif have_early:
        E_final = E_ret / max(p.early_final_pct_in, 0.05)
        raw = E_final.sum() / exp_early0.sum()
        mult = 1.0 + 0.5 * (np.clip(raw, 0.7, 1.4) - 1.0)
    else:
        E_final, mult = exp_early0.copy(), 1.0
    ED_tot = (T0 - exp_early0) * mult

    # ---- what has been counted, and what it was made of -----------------------------
    dem = df["dem"].to_numpy(float)
    rep = df["rep"].to_numpy(float)
    counted = dem + rep
    if p.early_first:
        ce = np.minimum(counted, E_final)
    else:
        ce = counted * E_final / np.maximum(E_final + ED_tot, 1.0)
    ced = counted - ce
    rem_e = np.maximum(E_final - ce, 0.0)
    rem_ed = np.maximum(ED_tot - ced, 0.0)
    final = df["final"].to_numpy(bool)
    rem_e[final] = 0.0
    rem_ed[final] = 0.0
    rem = rem_e + rem_ed
    T_hat = np.maximum(counted + rem, 1.0)
    frac = counted / T_hat

    w = np.clip(E_final / np.maximum(E_final + ED_tot, 1.0), 0.02, 0.98)
    # ---- how lopsided is the early electorate? --------------------------------------------------------------
    # The 8-pt gap is only a prior.  If the early ballots already banked are far more Democratic than baseline + polling swing explains,
    # the leftover (Election Day) vote is redder than a flat gap assumes, so the gap is raised (never lowered), by half the excess, up to early_gap_max.
    g_prior = g
    if have_early:
        S_prior = (p.poll_margin + p.poll_bias - M0) if p.poll_margin is not None else 0.0
        em_obs = None
        regp = df["d_reg"] + df["r_reg"] + df["o_reg"]
        okp = ((regp > 0) & (E_ret > 0)).to_numpy(bool)
        if okp.any():
            rg = regp.where(regp > 0, 1)
            pD_, pR_, pO_ = (df[c] / rg for c in ("d_reg", "r_reg", "o_reg"))
            u_ = np.clip((1 + (m0 + p.other_lean) / 100) / 2, 0.02, 0.98)
            e_ = (2 * (pD_.to_numpy(float) * p.reg_loyalty + pR_.to_numpy(float) * (1 - p.reg_loyalty) + pO_.to_numpy(float) * u_) - 1) * 100
            em_obs = float((E_ret[okp] * e_[okp]).sum() / E_ret[okp].sum()) - p.party_bias
            wsel = okp
        elif p.vh_early_margin is not None:
            em_obs, wsel = float(p.vh_early_margin), E_ret > 0
        if em_obs is not None:
            Mw = float((E_ret[wsel] * m0[wsel]).sum() / E_ret[wsel].sum())
            wbar = float((E_ret[wsel] * w[wsel]).sum() / E_ret[wsel].sum())
            g_obs = (em_obs - Mw - S_prior) / max(1.0 - wbar, 0.15)
            g = float(np.clip(g + 0.5 * (g_obs - g), g, p.early_gap_max))
    em0 = m0 + (1 - w) * g      # expected early-pool margin
    edm0 = m0 - w * g           # expected Election Day-pool margin

    # ---- evidence about the statewide swing S ----------------------------------------
    obs = []  # (mean, variance, label)
    if p.poll_margin is not None:
        obs.append((p.poll_margin + p.poll_bias - M0, p.sd_poll ** 2, "polls"))
    else:
        obs.append((0.0, p.sd_prior_nopoll ** 2, "no polls"))
    if p.fund_margin is not None:
        obs.append((p.fund_margin - M0, p.sd_fund ** 2, "fundamentals"))

    early_counted_state = float(ce.sum() / max(E_final.sum(), 1.0))
    infl = 1.0 / max(1.0 - early_counted_state, 0.02)  # early ballots are counted -> don't double count

    sig_party = sig_geo = None
    if have_early:
        reg = df["d_reg"] + df["r_reg"] + df["o_reg"]
        ok = (reg > 0) & (E_ret > 0)
        if ok.any():
            L = p.reg_loyalty
            pD = (df["d_reg"] / reg.where(reg > 0, 1)).to_numpy(float)
            pR = (df["r_reg"] / reg.where(reg > 0, 1)).to_numpy(float)
            pO = (df["o_reg"] / reg.where(reg > 0, 1)).to_numpy(float)
            u = (1 + (em0 + p.other_lean) / 100) / 2
            u = np.clip(u, 0.02, 0.98)
            s = pD * L + pR * (1 - L) + pO * u
            e_est = (2 * s - 1) * 100
            dev = e_est - em0 - p.party_bias
            sig_party = float((E_ret[ok] * dev[ok]).sum() / E_ret[ok].sum())
            pO_bar = float((E_ret[ok] * pO[ok]).sum() / E_ret[ok].sum())       # weight of 'other' registrants in the returned ballots
            var_ep = (p.sd_early_party * infl) ** 2 + (pO_bar * p.sd_other * infl) ** 2
            # bounded like the VoteHub signal: whatever the early party mix says, it moves the swing estimate by at most party_max_effect points
            P0_ = sum(1.0 / v for _, v, _ in obs)
            S0_ = sum(mm_ / v for mm_, v, _ in obs) / P0_
            om_ = (1.0 / var_ep) / (1.0 / var_ep + P0_)
            lim_ = p.party_max_effect / om_
            sig_party_raw = sig_party
            sig_party = float(np.clip(sig_party, S0_ - lim_, S0_ + lim_))
            obs.append((sig_party, var_ep, "early party reg"))
        sig_geo = float((E_ret * m0).sum() / E_ret.sum() - (exp_early0 * m0).sum() / exp_early0.sum())
        if p.early_geo_signal and abs(sig_geo) > 1e-6:      # exactly 0 = the early table is a statewide total spread over counties: no geography to read
            var_eg = (p.sd_early_geo * infl) ** 2
            P1_ = sum(1.0 / v for _, v, _ in obs)
            S1_ = sum(mm_ / v for mm_, v, _ in obs) / P1_
            lim_g = p.party_max_effect / ((1.0 / var_eg) / (1.0 / var_eg + P1_))     # same bound as the party signal
            obs.append((float(np.clip(sig_geo, S1_ - lim_g, S1_ + lim_g)), var_eg, "early geography"))

    wv = E_ret if have_early else exp_early0
    em_exp = float((wv * em0).sum() / max(wv.sum(), 1.0))
    if p.vh_early_margin is not None:
        # VoteHub's early-electorate margin, read as a swing; it can only pull the swing estimate toward it, never by more than vh_max_effect points
        mean_raw = float(p.vh_early_margin) - em_exp
        var_v = (p.sd_votehub * infl) ** 2
        P0 = sum(1.0 / v for _, v, _ in obs)
        S0 = sum(mm / v for mm, v, _ in obs) / P0
        om = (1.0 / var_v) / (1.0 / var_v + P0)
        dev = float(np.clip((mean_raw - S0) * p.vh_scale, -p.vh_max_effect / om, p.vh_max_effect / om))
        obs.append((S0 + dev, var_v, "VoteHub early model"))

    # ---- counted votes: deviation of each county from expectation -------------------
    has = counted > 0
    exp_counted = np.where(has, (ce * em0 + ced * edm0) / np.maximum(counted, 1.0), m0)
    obs_margin = two_party_margin(dem, rep)
    d_i = np.where(has, obs_margin - exp_counted, 0.0)
    v_i = p.sigma_nonrep ** 2 * (1 - frac) + 1e4 / np.maximum(counted, 1.0)
    v_i = np.where(final, 1e4 / np.maximum(counted, 1.0), v_i)
    # `weight` < 1 marks rows ESTIMATED from a statewide total (statewide_mode.py): they carry less information than real county counts
    v_i = v_i / df["weight"].to_numpy(float)
    var_swing_i = v_i + p.tau_county ** 2 + p.tau_region ** 2
    # ---- does the swing depend on how blue/red the county is? (turnout and composition effects) --------------------------
    x_i = m0 - M0
    beta_hat, sd_beta = 0.0, 0.0
    if p.slope_prior_sd > 0:
        hh = np.where(has)[0]
        if len(hh) >= 3:
            ww = 1.0 / var_swing_i[hh]
            xm = float((ww * x_i[hh]).sum() / ww.sum())
            xc = x_i[hh] - xm
            sxx = float((ww * xc * xc).sum())
            sxy = float((ww * xc * d_i[hh]).sum())
            prec_b = sxx + 1.0 / p.slope_prior_sd ** 2
            beta_hat = sxy / prec_b
            sd_beta = float(np.sqrt(1.0 / prec_b))
        else:
            sd_beta = p.slope_prior_sd
    d_adj = d_i - beta_hat * x_i
    for i in np.where(has)[0]:
        obs.append((float(d_adj[i]), float(var_swing_i[i]), "counted"))

    prec = np.array([1.0 / v for _, v, _ in obs])
    means = np.array([m for m, _, _ in obs])
    S_hat = float((prec * means).sum() / prec.sum())
    groups: dict = {}                      # which evidence is driving the swing estimate
    for mm, vv, lab in obs:
        g_ = groups.setdefault(lab, [0.0, 0.0])
        g_[0] += 1.0 / vv
        g_[1] += mm / vv
    drivers = [dict(source=lab, swing=g_[1] / g_[0], weight=g_[0] / float(prec.sum()) * 100)
               for lab, g_ in groups.items()]
    # A wrong early-vs-Election-Day gap only matters when the outstanding pool's mix
    # differs from the baseline mix (e.g. early already counted, Election Day still out).
    gap_sens = float((rem_e * (1 - w) - rem_ed * w).sum() / T_hat.sum())
    var_S = 1.0 / prec.sum() + (p.sd_gap * gap_sens) ** 2
    _floor = p.sd_floor_swing * (1.0 - float(counted.sum() / max(T_hat.sum(), 1.0))) ** 0.5    # relaxes as the vote is counted
    var_S = max(var_S, _floor ** 2)
    sd_S = float(np.sqrt(var_S))

    # ---- region and county effects (empirical-Bayes shrinkage) ----------------------
    regions = df["region"].astype(str).to_numpy()
    uniq = sorted(set(regions))
    reg_idx = np.array([uniq.index(r) for r in regions])
    g_mean = np.zeros(len(uniq))
    g_sd = np.full(len(uniq), p.tau_region)
    for j in range(len(uniq)):
        m = (reg_idx == j) & has
        if m.any():
            wt = 1.0 / (v_i[m] + p.tau_county ** 2)
            num = (wt * (d_adj[m] - S_hat)).sum()
            den = wt.sum() + 1.0 / p.tau_region ** 2
            g_mean[j] = num / den
            g_sd[j] = np.sqrt(1.0 / den)
    resid = d_adj - S_hat - g_mean[reg_idx]
    shrink = p.tau_county ** 2 / (p.tau_county ** 2 + v_i)
    r_mean = np.where(has, resid * shrink, 0.0)
    r_sd = np.where(has, np.sqrt(p.tau_county ** 2 * v_i / (p.tau_county ** 2 + v_i)), p.tau_county)

    # ---- point projection --------------------------------------------------------------
    def pooled_margin(shift):
        num = rem_e * (em0 + shift) + rem_ed * (edm0 + shift)
        return np.clip(np.where(rem > 0, num / np.maximum(rem, 1e-9), m0 + shift), -100, 100)

    shift_pt = S_hat + beta_hat * x_i + g_mean[reg_idx] + r_mean
    rm_pt = pooled_margin(shift_pt)
    D_pt = dem + rem * (0.5 + rm_pt / 200)
    R_pt = rep + rem * (0.5 - rm_pt / 200)
    third = float(np.clip(p.third_share, 0.0, 0.5))

    def final_margin(Dt, Rt):
        """Two-party margin after any ranked-choice transfers of other candidates' ballots."""
        if p.rcv and third > 0:
            oth = (Dt + Rt) / (1 - third) * third
            return two_party_margin(Dt + oth * p.rcv_to_d, Rt + oth * p.rcv_to_r)
        return two_party_margin(Dt, Rt)

    point_first = float(two_party_margin(D_pt.sum(), R_pt.sum()))
    point = float(final_margin(D_pt.sum(), R_pt.sum()))

    # ---- firewall view: net votes by how each unit is projected to finish -------------
    fin_u = two_party_margin(D_pt, R_pt)
    net_counted = dem - rep
    net_remaining = rem * rm_pt / 100.0
    rows = []
    for lo, hi, name in ((15, 1e9, "Solid D"), (3, 15, "Lean D"), (-3, 3, "Toss-up"),
                         (-15, -3, "Lean R"), (-1e9, -15, "Solid R")):
        m = (fin_u >= lo) & (fin_u < hi)
        if m.any():
            rows.append(dict(tier=name, units=int(m.sum()), counted=float(counted[m].sum()),
                             remaining=float(rem[m].sum()), counted_net=float(net_counted[m].sum()),
                             remaining_net=float(net_remaining[m].sum())))
    tiers = pd.DataFrame(rows)
    if len(tiers):
        tiers["final_net"] = tiers["counted_net"] + tiers["remaining_net"]

    # ---- Monte Carlo -------------------------------------------------------------------
    rng = np.random.default_rng(p.seed)
    n = p.n_sims
    # Skew: only the polling prior is skewed; counted votes dilute it, so scale by its precision share.
    z = rng.normal(size=(n, 1))
    if p.poll_skew != 0.0 and p.poll_margin is not None:
        share = float(prec[0] / prec.sum())
        a = p.poll_skew * share
        dl = a / np.sqrt(1 + a * a)
        zs = dl * np.abs(rng.normal(size=(n, 1))) + np.sqrt(1 - dl * dl) * z
        z = (zs - dl * np.sqrt(2 / np.pi)) / np.sqrt(1 - 2 * dl * dl / np.pi)
    S = S_hat + sd_S * z
    G = rng.normal(g_mean, g_sd, (n, len(uniq)))[:, reg_idx]
    Rr = rng.normal(r_mean, r_sd, (n, K))
    Bd = rng.normal(beta_hat, sd_beta, (n, 1)) if sd_beta > 0 else np.zeros((n, 1))
    shift = S + Bd * x_i[None, :] + G + Rr
    num = rem_e * (em0 + shift) + rem_ed * (edm0 + shift)
    rm = np.where(rem > 0, num / np.maximum(rem, 1e-9), m0 + shift)
    # the last votes counted rarely look like the first ones (late mail, big precincts)
    rm = np.clip(rm + rng.normal(0, p.sd_remaining, (n, K)), -100, 100)
    turn =np.exp(rng.normal(0, p.turnout_sd, (n, 1)) + rng.normal(0, p.county_turnout_sd, (n, K)))
    rem_t = rem * turn
    D = dem + rem_t * (0.5 + rm / 200)
    R = rep + rem_t * (0.5 - rm / 200)
    Dt, Rt = D.sum(1), R.sum(1)
    margins_first = two_party_margin(Dt, Rt)
    margins = final_margin(Dt, Rt)
    win_prob = float((margins > 0).mean())
    outcome = None
    if p.runoff_rule:  # no majority -> runoff; a runoff is a fresh two-way race
        tot_all = (Dt + Rt) / (1 - third)
        d_out = Dt / tot_all > p.runoff_threshold
        r_out = Rt / tot_all > p.runoff_threshold
        run = ~(d_out | r_out)
        run_m = margins_first + p.runoff_shift + rng.normal(0, p.runoff_sd, n)
        win_prob = float((d_out | (run & (run_m > 0))).mean())
        outcome = {"p_d_outright": float(d_out.mean()), "p_r_outright": float(r_out.mean()),
                   "p_runoff": float(run.mean()),
                   "p_d_wins_runoff_given": float((run_m[run] > 0).mean()) if run.any() else None,
                   "threshold": p.runoff_threshold}
    first_round = None
    if p.rcv and third > 0:
        first_round = {"median": float(np.median(margins_first)),
                       "win_prob": float((margins_first > 0).mean())}
    inputs = {
        "units": int(K), "units_with_early": int((E_ret > 0).sum()), "early_returned": float(E_ret.sum()),
        "swing_slope": float(beta_hat), "swing_slope_sd": float(sd_beta),
        "early_pool_expected": em_exp, "early_expected_final": float(E_final.sum()), "early_final_pct_in": (float(E_ret.sum() / max(E_final.sum(), 1.0)) if have_early else p.early_final_pct_in),
        "early_party_data": sig_party is not None, "units_reporting": int(has.sum()),
        "units_final": int(final.sum()), "counted": float(counted.sum()), "expected_total": float(T_hat.sum()),
        "outstanding_share": float(rem.sum() / T_hat.sum()), "poll_margin": p.poll_margin,
        "poll_bias": p.poll_bias, "sd_poll": p.sd_poll, "poll_skew": p.poll_skew,
        "early_gap": g, "early_gap_prior": g_prior, "early_first": p.early_first, "turnout_mult": float(mult),
        "tau_county": p.tau_county, "tau_region": p.tau_region, "rcv": p.rcv, "third_share": third,
        "rcv_to_d": p.rcv_to_d, "rcv_to_r": p.rcv_to_r, "runoff_rule": p.runoff_rule,
        "baseline_margin": M0,
    }

    table = pd.DataFrame({
        "county": df["county"], "region": df["region"],
        "pct_in": np.where(final, 100.0, np.minimum(frac * 100, 99.9)),
        "counted": counted.round(0), "remaining": rem.round(0),
        "proj_margin": two_party_margin(D_pt, R_pt).round(1),
        "base_margin": m0.round(1),
        "early_returned": E_ret.round(0),                                # early / mail ballots returned so far (loaded early vote)
    })
    table.loc[~has & ~final, "pct_in"] = 0.0

    return {
        "point": point,
        "median": float(np.median(margins)),
        "p05": float(np.percentile(margins, 5)), "p10": float(np.percentile(margins, 10)),
        "p90": float(np.percentile(margins, 90)), "p95": float(np.percentile(margins, 95)),
        "win_prob": win_prob,
        "point_first": point_first, "drivers": drivers, "tiers": tiers, "inputs": inputs,
        "outcome": outcome, "first_round": first_round,
        "pct_in": float(counted.sum() / T_hat.sum() * 100),
        "baseline_margin": M0,
        "swing": S_hat, "swing_sd": sd_S,
        "turnout_mult": float(mult),
        "signals": {"poll_swing": (None if p.poll_margin is None else p.poll_margin - M0),
                    "fund_swing": (None if p.fund_margin is None else p.fund_margin - M0),
                    "early_party": sig_party, "early_geo": sig_geo},
        "table": table,
        "sims": margins,
    }
