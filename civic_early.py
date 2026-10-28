"""Pulls early vote from civicAPI (https://civicapi.org, free, no key; credit: civicAPI) and writes data/night/early_civic.csv for sheet_inbox.
Per state it reads /api/v2/early-vote/{ST}/returned (mail) and /inperson, adds them (that is the state's early vote), sums party where the state reports it.
Modes in config/civic_early.json. Failures never stop the run. Run before run_update.py."""
import csv, datetime as dt, json, os, sys
import pandas as pd
import requests

BASE = "https://civicapi.org/api/v2/early-vote"
H = {"User-Agent": "election-needle/1.0 (personal project; data from civicAPI, civicapi.org)"}
CFG = "config/civic_early.json"
OUT = "data/night/early_civic.csv"
LOG = "data/civic_early_log.csv"


def fetch(st: str, cat: str):
    try:
        r = requests.get(f"{BASE}/{st}/{cat}", headers=H, timeout=30)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as ex:
        print(f"  {st}/{cat}: {str(ex)[:80]}")
        return None


def regions_total(js):
    """{region: {'tot':n,'D':n,'R':n,'O':n,'party':bool}} from one category payload."""
    out = {}
    for name, parties in (js.get("regions") or {}).items():
        t = d = rr = o = 0.0
        known = False
        for p, v in (parties or {}).items():
            n = float((v or {}).get("votes") or 0)
            t += n
            if p == "Democratic":
                d += n; known = True
            elif p == "Republican":
                rr += n; known = True
            elif p != "Unspecified":
                o += n; known = True
        out[name] = {"tot": t, "D": d, "R": rr, "O": o, "party": known}
    return out


def combine(a: dict, b: dict) -> dict:
    out = {}
    for k in set(a) | set(b):
        x, y = a.get(k), b.get(k)
        out[k] = {f: (x[f] if x else 0) + (y[f] if y else 0) for f in ("tot", "D", "R", "O")}
        out[k]["party"] = bool((x and x["party"]) or (y and y["party"]))
    return out


def our_total(folder):
    p = os.path.join(folder, "early.csv")
    try:
        return float(pd.to_numeric(pd.read_csv(p)["early_returned"], errors="coerce").sum())
    except Exception:
        return 0.0


def main(fetch_fn=fetch, today=None):
    cfg = json.load(open(CFG))
    races = json.load(open("config/races.json"))["races"]
    from model import norm_name
    today = today or dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).date()
    rows, logrows = [], []
    for st, mode in cfg["states"].items():
        if mode == "off":
            continue
        sr = [r for r in races if r.get("state") == st]
        if not sr:
            continue
        ret, inp = fetch_fn(st, "returned"), fetch_fn(st, "inperson")
        if not ret and not inp:
            print(f"{st}: no civicAPI early vote data")
            continue
        snap = (ret or inp).get("snapshot_date")
        try:
            age = (today - dt.date.fromisoformat(str(snap)[:10])).days
        except Exception:
            age = 99
        reg = combine(regions_total(ret) if ret else {}, regions_total(inp) if inp else {})
        total = sum(v["tot"] for v in reg.values())
        rtot = sum(v["tot"] for v in regions_total(ret).values()) if ret else 0
        itot = sum(v["tot"] for v in regions_total(inp).values()) if inp else 0
        ours = our_total(sr[0].get("dir", f"data/{sr[0]['id']}"))
        note = ""
        use = mode
        if age > cfg.get("max_age_days", 2):
            use, note = "log_only", f"stale ({snap})"
        if total <= 0:
            use, note = "log_only", "zero total"
        # match regions to our counties
        counties = None
        try:
            c = pd.read_csv(os.path.join(sr[0].get("dir", f"data/{sr[0]['id']}"), "counties.csv"))
            counties = {norm_name(x): x for x in c["county"].astype(str)}
        except Exception:
            pass
        matched = sum(v["tot"] for k, v in reg.items() if counties and norm_name(k) in counties)
        county_ok = counties is not None and total > 0 and matched / total >= 0.95
        party_ok = sum(v["D"] + v["R"] for v in reg.values()) > 0.5 * total and all(v["party"] for v in reg.values() if v["tot"] > 0)
        print(f"{st}: civic {total:,.0f} (mail {rtot:,.0f} + in-person {itot:,.0f}) as of {snap}; ours {ours:,.0f}; "
              f"{len(reg)} regions, {matched / total * 100 if total else 0:.0f}% match counties; party {'yes' if party_ok else 'no'}; mode {use} {note}")
        logrows.append([dt.datetime.utcnow().isoformat(timespec="minutes"), st, snap, round(rtot), round(itot), round(total), use, note])
        if use == "log_only":
            continue
        for r in sr:
            if use == "auto" and county_ok:
                for k, v in reg.items():
                    if norm_name(k) in counties:
                        rows.append([r["id"], counties[norm_name(k)], round(v["tot"]),
                                     round(v["D"]) if party_ok else "", round(v["R"]) if party_ok else "", round(v["O"]) if party_ok else ""])
            else:
                D = sum(v["D"] for v in reg.values()); R = sum(v["R"] for v in reg.values()); O = sum(v["O"] for v in reg.values())
                rows.append([r["id"], "STATE", round(total), round(D) if party_ok else "", round(R) if party_ok else "", round(O) if party_ok else ""])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["race", "county", "early_returned", "d_reg", "r_reg", "o_reg"])
        w.writerows(rows)
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts_utc", "state", "snapshot_date", "mail", "in_person", "total", "mode", "note"])
        w.writerows(logrows)
    print(f"civicAPI early vote: {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"civic early vote skipped ({str(ex)[:150]})")
