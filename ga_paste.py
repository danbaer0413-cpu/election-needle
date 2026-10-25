"""
Turn text copied from Georgia's Election Data Hub tables into the Georgia early.csv files.

    python ga_paste.py absentee.txt inperson.txt

absentee.txt : the "Ballots Issued and Accepted by County" table, copied as text (county then 7+ numbers per line).
inperson.txt : the "Ballots to Date by County" table (county then one number per line).
Works with tab- or space-separated text. Writes data/GA/early_<today>.csv and both races' early.csv,
and prints sums so you can compare them with the dashboard's totals.
"""
import datetime as dt
import re
import sys

import pandas as pd

from model import norm_name


def read_lines(path, n_numbers):
    out = {}
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.replace("\t", " ").strip()
        m = re.match(r"^([A-Za-z .'-]+?)\s+((?:[\d,.]+%?\s*)+)$", line)
        if not m:
            continue
        nums = [x for x in m.group(2).split() if not x.endswith("%")]
        nums = [int(float(x.replace(",", ""))) for x in nums]
        if len(nums) >= n_numbers and m.group(1).strip().upper() not in ("TOTALS", "TOTAL"):
            out[m.group(1).strip().upper()] = nums
    return out


if __name__ == "__main__":
    ab = read_lines(sys.argv[1], 7)     # requested, issued, returned, accepted, rejected, other, outstanding
    ip = read_lines(sys.argv[2], 1)
    base = pd.read_csv("data/GA/governor/counties.csv")
    keys = {norm_name(c): c for c in base["county"]}
    rows, missing = [], []
    for k, c in keys.items():
        a = next((v for n, v in ab.items() if norm_name(n) == k), None)
        i = next((v for n, v in ip.items() if norm_name(n) == k), None)
        if a is None or i is None:
            missing.append(c)
            continue
        rows.append(dict(county=c, abs_accepted=a[3], abs_outstanding=a[6], inperson_accepted=i[0]))
    d = pd.DataFrame(rows)
    d["early_returned"] = d["abs_accepted"] + d["inperson_accepted"]
    d["d_reg"] = d["r_reg"] = d["o_reg"] = ""
    print(f"{len(d)} of {len(keys)} counties read. Missing: {missing or 'none'}")
    print(f"absentee accepted {d.abs_accepted.sum():,}  in-person {d.inperson_accepted.sum():,}  combined {d.early_returned.sum():,}")
    if missing:
        sys.exit("Not writing files until every county is present.")
    d.to_csv(f"data/GA/early_{dt.date.today()}.csv", index=False)
    for race in ("governor", "u-s-senate"):
        d[["county", "early_returned", "d_reg", "r_reg", "o_reg"]].to_csv(f"data/GA/{race}/early.csv", index=False)
    print("wrote early.csv for both Georgia races")
