"""Build data/poll_error_history.csv from Silver Bulletin's Rawpolls + Pollster_Stats_Full files.
usage: python build_poll_error.py Rawpolls.xlsx Pollster_Stats_Full.xlsx [out.csv]
Rule (same as live polls): polls ending <=21 days before the election, nonpartisan, latest per pollster,
weight sqrt(sample). Tier 1 = grade B+ or better (A/B provisional counts); Tier 2 = B, B- if <2 Tier 1."""
import sys, numpy as np, pandas as pd
T1 = {"A+", "A", "A-", "A/B", "B+"}; T2 = {"B", "B-"}
RACE = {"Pres-G": "President", "Sen-G": "U.S. Senate", "Sen-GS": "U.S. Senate (special)", "Gov-G": "Governor"}


def main(raw, stats, out="data/poll_error_history.csv"):
    r = pd.read_excel(raw); s = pd.read_excel(stats, sheet_name=0)
    s = s.rename(columns={"Unnamed: 1": "name"}).set_index("Pollster Rating ID")
    r["grade"] = r.pollster_rating_id.map(s["SB Grade"])
    r["banned"] = r.pollster_rating_id.map(s["Banned by Silver Bulletin"]).astype(str).str.lower().eq("yes")
    r = r[r.type_detail.isin(RACE) & r.year.isin([2016, 2018, 2020, 2022, 2024]) & r.partisan.isna() & ~r.banned].copy()
    ok = (r.cand1_party.isin(["DEM", "REP"]) & r.cand2_party.isin(["DEM", "REP"]) & (r.cand1_party != r.cand2_party))
    r = r[ok]
    sw = r.cand1_party.eq("REP")                                     # put Dem first
    d = np.where(sw, r.cand2_pct, r.cand1_pct); rp = np.where(sw, r.cand1_pct, r.cand2_pct)
    da = np.where(sw, r.cand2_actual, r.cand1_actual); ra = np.where(sw, r.cand1_actual, r.cand2_actual)
    r["pm"] = (d - rp) / (d + rp) * 100; r["am"] = (da - ra) / (da + ra) * 100
    r["days"] = (r.electiondate - r.polldate).dt.days
    r = r[(r.days >= 0) & (r.days <= 21)].dropna(subset=["pm", "am"])
    rows = []
    for (loc, yr, td), g in r.groupby(["location", "year", "type_detail"]):
        g = g.sort_values("polldate").groupby("pollster").tail(1)
        t1 = g[g.grade.isin(T1)]; t2 = g[g.grade.isin(T2)]
        if len(t1) >= 2: use, rule = t1, "tier1"
        elif len(t1) + len(t2) >= 1: use, rule = pd.concat([t1, t2]), ("thin" if len(t1) + len(t2) == 1 else "tier1+2")
        else: continue
        w = np.sqrt(use.samplesize.fillna(use.samplesize.median() if use.samplesize.notna().any() else 600))
        rows.append(dict(state=loc, year=int(yr), race=RACE[td], poll_margin=round(float(np.average(use.pm, weights=w)), 2),
                         actual_margin=round(float(use.am.iloc[0]), 2), n_polls=len(use), rule_used=rule))
    h = pd.DataFrame(rows).sort_values(["year", "race", "state"])
    h = h[h.state.str.fullmatch(r"[A-Z]{2}")]                         # drop national / district rows (e.g. NE-02)
    h.to_csv(out, index=False); return h


if __name__ == "__main__":
    h = main(sys.argv[1], sys.argv[2], *(sys.argv[3:4] or []))
    print(len(h), "rows"); print(h.groupby(["year", "race"]).size().unstack(fill_value=0)); print(h.rule_used.value_counts())
