"""
Count Georgia's per-county absentee voter files into early.csv (counts only; no voter data is kept).

    python ga_voterfile.py DIR_WITH_COUNTY_CSVS

Each file is one county's rows from https://mvp.sos.ga.gov/s/voter-absentee-files . Only these columns
are read: County, Ballot Status, Ballot Style, Ballot Return Date. A ballot counts as returned when its
status is 'A' (accepted). 'I' (issued, mail not back yet) is the outstanding-mail count.
Never commit the raw county files: they contain voter names and addresses.
"""
import glob
import os
import sys

import pandas as pd

from model import norm_name

COLS = ["County", "Ballot Status", "Ballot Style", "Ballot Return Date"]


def count_file(path):
    d = pd.read_csv(path, dtype=str, usecols=COLS)
    if d.empty:
        return None
    inperson = d["Ballot Style"].eq("EARLY IN-PERSON")
    acc = d["Ballot Status"].eq("A")
    last = pd.to_datetime(d["Ballot Return Date"], errors="coerce", format="%m/%d/%Y").max()
    return dict(county=d["County"].iloc[0].title(), abs_accepted=int((acc & ~inperson).sum()),
                inperson_accepted=int((acc & inperson).sum()),
                abs_outstanding=int((d["Ballot Status"].eq("I") & ~inperson).sum()), last_return=last)


if __name__ == "__main__":
    rows = [r for r in (count_file(p) for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.csv")))) if r]
    d = pd.DataFrame(rows)
    base = pd.read_csv("data/GA/governor/counties.csv")
    keys = {norm_name(c): c for c in base["county"]}
    d["county"] = d["county"].map(lambda c: keys.get(norm_name(c), c))
    missing = sorted(set(keys.values()) - set(d["county"]))
    d["early_returned"] = d["abs_accepted"] + d["inperson_accepted"]
    print(f"{len(d)} county files; newest ballot return in the files: {d['last_return'].max().date()}")
    print(f"combined {d.early_returned.sum():,}  (absentee {d.abs_accepted.sum():,}, in-person {d.inperson_accepted.sum():,})")
    if missing:
        sys.exit(f"{len(missing)} counties missing, nothing written: {missing[:8]}...")
    d["d_reg"] = d["r_reg"] = d["o_reg"] = ""
    for race in ("governor", "u-s-senate"):
        d[["county", "early_returned", "d_reg", "r_reg", "o_reg"]].to_csv(f"data/GA/{race}/early.csv", index=False)
    print("wrote early.csv for both Georgia races")
