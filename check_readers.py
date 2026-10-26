"""
Rehearsal: run each automatic reader against a PAST general election and compare to data/<STATE>/history_results.csv.
Run on GitHub (Actions -> rehearse-readers) or anywhere with internet:  python check_readers.py
PASS means the reader found the right race, read every county, and the totals match the certified history.
A FAIL shows which county names did not line up, so you can fix names before election night.
Florida, Ohio and South Carolina cannot be rehearsed this way (no past election is posted in the same place); check_feeds.py covers them.
"""
import sys
import pandas as pd
from feeds import load_feed
from model import norm_name

TESTS = [
    dict(label="Texas 2024 US Senate", state="TX", year=2024, race="U.S. Senate",
         row=dict(id="TX-senate", url="https://results.texas-election.com", fmt="texas", sheet="49664", cand_col=r"U\. ?S\. SENATOR")),
    dict(label="Georgia 2024 President", state="GA", year=2024, race="President",
         row=dict(id="GA-senate", url="https://results.sos.ga.gov", fmt="georgia", sheet="2024NovGen", cand_col=r"^President")),
    dict(label="Iowa 2024 President", state="IA", year=2024, race="President",
         row=dict(id="IA-senate", url="https://electionresults.iowa.gov/IA", fmt="soe", sheet="year:2024", cand_col=r"President")),
    dict(label="North Carolina 2024 President (state results file)", state="NC", year=2024, race="President",
         row=dict(id="NC-senate", fmt="ncsbe", sheet="2024_11_05", cand_col=r"PRESIDENT")),
    dict(label="Florida 2024 President (election-night file)", state="FL", year=2024, race="President",
         row=dict(id="FL-senate", fmt="flfile", sheet="20241105", cand_col=r"President")),
    dict(label="Alaska 2024 President (by House district)", state="AK", year=2024, race="President",
         row=dict(id="AK-senate", fmt="alaska", sheet="24GENR", cand_col=r"President")),
]


def compare(got: pd.DataFrame, hist: pd.DataFrame):
    g = got.assign(k=got["county"].map(norm_name)).groupby("k")[["dem", "rep"]].sum()
    h = hist.assign(k=hist["county"].map(norm_name)).groupby("k")[["dem_votes", "rep_votes"]].sum()
    both = g.index.intersection(h.index)
    miss_g, miss_h = sorted(set(g.index) - set(h.index)), sorted(set(h.index) - set(g.index))
    tot_g, tot_h = g[["dem", "rep"]].sum(), h[["dem_votes", "rep_votes"]].sum()
    d_dem = abs(tot_g["dem"] - tot_h["dem_votes"]) / max(tot_h["dem_votes"], 1)
    d_rep = abs(tot_g["rep"] - tot_h["rep_votes"]) / max(tot_h["rep_votes"], 1)
    return dict(n_reader=len(g), n_hist=len(h), matched=len(both), miss_reader=miss_g, miss_hist=miss_h,
                tot_reader=(int(tot_g["dem"]), int(tot_g["rep"])), tot_hist=(int(tot_h["dem_votes"]), int(tot_h["rep_votes"])),
                d_dem=d_dem, d_rep=d_rep)


def main():
    bad = 0
    for t in TESTS:
        print(f"\n== {t['label']} ==")
        try:
            got = load_feed(t["row"])
            hist = pd.read_csv(f"data/{t['state']}/history_results.csv")
            hist = hist[(hist.year == t["year"]) & (hist.race == t["race"])]
            r = compare(got, hist)
            ok = r["matched"] >= 0.98 * r["n_hist"] and r["d_dem"] < 0.005 and r["d_rep"] < 0.005
            print(f"  counties: reader {r['n_reader']}, history {r['n_hist']}, matched {r['matched']}")
            print(f"  totals  : reader D {r['tot_reader'][0]:,} R {r['tot_reader'][1]:,} | history D {r['tot_hist'][0]:,} R {r['tot_hist'][1]:,}")
            print(f"  total difference: D {r['d_dem']:.3%}, R {r['d_rep']:.3%}")
            if r["miss_reader"] or r["miss_hist"]:
                print(f"  names only in reader: {r['miss_reader'][:10]}\n  names only in history: {r['miss_hist'][:10]}")
            print("  PASS" if ok else "  FAIL")
            bad += (not ok)
        except Exception as ex:
            print(f"  ERROR: {type(ex).__name__}: {str(ex)[:300]}")
            bad += 1
    print(f"\n{len(TESTS) - bad} of {len(TESTS)} passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
