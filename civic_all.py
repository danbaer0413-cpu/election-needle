"""Everything civicAPI (civicapi.org, free; credit them) has for one election date: every race in every state, each
candidate's votes, and the county / parish / district breakdown.
Writes data/civic_<date>/: races_<ST>.csv, candidates_<ST>.csv, regions_<ST>.csv.gz, and status.json.
States already saved are skipped (pass --force to redo), so a run cut short by its time limit resumes on the next run.
Run by hand through .github/workflows/civic-all.yml.   python civic_all.py --date 2026-11-03 [--states LA,TX] [--force]"""
from __future__ import annotations
import argparse, csv, datetime as dt, gzip, json, os, time
import requests
from civic_results import BASE, UA, _regions, _pairs, _region_pct

STATES = "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
STOP_AFTER_S = 5 * 3600 + 30 * 60   # leave time to commit before the job's 6-hour limit

def get(path, timeout=30):
    for i in range(5):
        try:
            r = requests.get(BASE + path, headers=UA, timeout=timeout)
            if r.status_code == 429:
                time.sleep(15 * (i + 1)); continue
            if r.status_code == 404: return None
            r.raise_for_status(); time.sleep(0.25); return r.json()
        except requests.RequestException:
            if i == 4: raise
            time.sleep(4 * (i + 1))

def search(st, date):
    out, off = [], 0
    while off < 100000:
        js = get(f"/race/search?country=US&province={st}&startDate={date}&endDate={date}&limit=1000&offset={off}") or {}
        races = js.get("races") or []
        out += races
        if len(races) < 1000: break
        off += 1000
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--date", default="2026-11-03"); ap.add_argument("--states", default=""); ap.add_argument("--force", action="store_true")
    a = ap.parse_args(); t0 = time.time()
    out = f"data/civic_{a.date}"; os.makedirs(out, exist_ok=True)
    stp = f"{out}/status.json"; status = json.load(open(stp)) if os.path.exists(stp) else {}
    todo = [s for s in (a.states.split(",") if a.states else STATES) if a.force or s not in status]
    for st in todo:
        if time.time() - t0 > STOP_AFTER_S:
            print("time limit reached; the next run resumes from", st); break
        try:
            races = search(st, a.date)
        except Exception as ex:
            print(f"{st}: search failed ({str(ex)[:80]})"); continue
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
        R, C, G, failed = [], [], [], 0
        for r in races:
            rid = r.get("id")
            try:
                d = get(f"/race/{rid}?data=json") or {}
            except Exception:
                failed += 1; continue
            cands = [c for c in (d.get("candidates") or []) if isinstance(c, dict)]
            cand_party = {str(c.get("name")): c.get("party") for c in cands}
            tot = sum(float(c.get("votes") or 0) for c in cands)
            regs = _regions(d.get("region_results"))
            R.append(dict(race_id=rid, state=st, election_name=d.get("election_name") or r.get("election_name"), election_date=a.date,
                          percent_reporting=d.get("percent_reporting"), called_at=d.get("called_at"), test_data=bool(d.get("test_data")),
                          candidates=len(cands), regions=len(regs), total_votes=int(tot), read_at=now))
            for c in cands:
                v = float(c.get("votes") or 0)
                C.append(dict(race_id=rid, state=st, candidate=c.get("name", ""), party=c.get("party", ""), votes=int(v),
                              pct=round(100 * v / tot, 3) if tot else "", winner=bool(c.get("winner")), incumbent=bool(c.get("incumbent"))))
            for name, payload in regs:
                rtype = payload.get("type", "") if isinstance(payload, dict) else ""
                pr = _region_pct(payload)
                for lab, party, n in _pairs(payload, cand_party):
                    G.append(dict(race_id=rid, region=name, region_type=rtype, percent_reporting=pr, candidate=lab, party=party or "", votes=int(n)))
        for nm, rows in (("races", R), ("candidates", C)):
            with open(f"{out}/{nm}_{st}.csv", "w", newline="") as f:
                if rows: w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        with gzip.open(f"{out}/regions_{st}.csv.gz", "wt", newline="") as f:
            if G: w = csv.DictWriter(f, fieldnames=list(G[0])); w.writeheader(); w.writerows(G)
        status[st] = dict(races=len(R), candidates=len(C), region_rows=len(G), failed=failed, read_at=now)
        json.dump(status, open(stp, "w"), indent=1)
        print(f"{st}: {len(R)} races, {len(C)} candidates, {len(G)} region rows, {failed} failed  ({(time.time() - t0) / 60:.0f} min)")
    left = [s for s in STATES if s not in status]
    print(f"done {len(status)} states; left: {left}")

if __name__ == "__main__":
    main()
