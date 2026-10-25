"""Scaffold data/<ST>/<race>/ with blank CSV headers.

Usage: python new_race.py NC "U.S. Senate"
The app auto-loads counties.csv / early.csv from that folder when you pick the race.
"""
import os
import sys

import pandas as pd

from states import STATES, race_dir

COLS = {
    "counties.csv": ["county", "region", "base_margin", "exp_votes", "exp_early_share"],
    "early.csv": ["county", "early_returned", "d_reg", "r_reg", "o_reg"],
}

NOTES = """# Where to get each file
counties.csv   One row per reporting unit.
  base_margin      two-party margin (D-R, pts) in a comparable past contest, same unit.
                   Statewide: county returns from the state elections site or MIT Election Lab.
                   District/local: precinct returns from the state or county clerk, re-aggregated
                   to the CURRENT boundaries.
  exp_votes        expected two-party votes (past turnout for this kind of election, adjusted).
  exp_early_share  share cast early/by mail in the comparable past contest.
  region           any grouping that moves together (metro, rural north, ...).
early.csv      From the state's ballot-return file (daily). party columns only where the state
               records party registration; leave blank otherwise.
results.csv    From the election-night feed; see feeds.py.
Calibrate early_gap and party_bias by replaying last cycle's same race.
"""

if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1].upper() not in STATES:
        sys.exit('usage: python new_race.py <ST> "<race name>"')
    abbr, race = sys.argv[1].upper(), sys.argv[2]
    d = race_dir(abbr, race)
    os.makedirs(d, exist_ok=True)
    for f, cols in COLS.items():
        path = os.path.join(d, f)
        if not os.path.exists(path):
            pd.DataFrame(columns=cols).to_csv(path, index=False)
    with open(os.path.join(d, "NOTES.md"), "w") as fh:
        fh.write(NOTES)
    print("created", d)
