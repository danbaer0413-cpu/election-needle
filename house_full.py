"""All 435 House races of Nov 3, 2026 from civicAPI (civicapi.org, free; credit them): every candidate's votes, percent
reporting and civicAPI's winner flag. Writes data/house/house_2026_all.csv (one row per candidate).
Run by hand through .github/workflows/house-full.yml; not part of the election-night loop."""
from __future__ import annotations
import csv, datetime as dt, sys, time
import requests
import house_results as hr

STATES = "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
SEATS = dict(AL=7, AK=1, AZ=9, AR=4, CA=52, CO=8, CT=5, DE=1, FL=28, GA=14, HI=2, ID=2, IL=17, IN=9, IA=4, KS=4, KY=6, LA=6, ME=2, MD=8, MA=9, MI=13, MN=8,
             MS=4, MO=8, MT=2, NE=3, NV=4, NH=2, NJ=12, NM=3, NY=26, NC=14, ND=1, OH=15, OK=5, OR=6, PA=17, RI=2, SC=7, SD=1, TN=9, TX=38, UT=4, VT=1,
             VA=11, WA=10, WV=2, WI=8, WY=1)

def get(path, timeout=20):
    for i in range(4):
        try:
            r = requests.get(hr.BASE + path, headers=hr.UA, timeout=timeout)
            if r.status_code == 429:
                time.sleep(10 * (i + 1)); continue
            r.raise_for_status(); time.sleep(0.4); return r.json()
        except requests.RequestException:
            if i == 3: raise
            time.sleep(3 * (i + 1))

def main(out="data/house/house_2026_all.csv"):
    rows, missing = [], []
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    for st in STATES:
        try:
            ids = hr.district_ids(st, get)
        except Exception as ex:
            print(f"{st}: search failed ({str(ex)[:80]})"); ids = {}
        want = ["AL"] if SEATS[st] == 1 else [str(i) for i in range(1, SEATS[st] + 1)]
        for k in want:
            rid = ids.get(k) or (ids.get("1") if k == "AL" else None) or (ids.get("AL") if SEATS[st] == 1 else None)
            if rid is None:
                missing.append(f"{st}-{k}"); continue
            try:
                d = get(f"/race/{rid}?data=json&light=true") or {}
            except Exception as ex:
                missing.append(f"{st}-{k} ({str(ex)[:40]})"); continue
            if d.get("test_data"):
                missing.append(f"{st}-{k} (test data)"); continue
            cands = [c for c in (d.get("candidates") or []) if isinstance(c, dict)]
            tot = sum(float(c.get("votes") or 0) for c in cands)
            for c in sorted(cands, key=lambda c: -float(c.get("votes") or 0)):
                v = float(c.get("votes") or 0)
                rows.append(dict(state=st, district="0" if k == "AL" else k, candidate=c.get("name", ""), party=c.get("party", ""),
                                 votes=int(v), pct=round(100 * v / tot, 2) if tot else "", winner=bool(c.get("winner")),
                                 pct_in=d.get("percent_reporting"), race_id=rid, race_name=d.get("election_name") or "", as_of=now))
        print(f"{st}: {sum(1 for r in rows if r['state'] == st)} candidate rows")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"{len({(r['state'], r['district']) for r in rows})} districts, {len(rows)} candidates; missing {len(missing)}: {missing}")

if __name__ == "__main__":
    main(*sys.argv[1:])
