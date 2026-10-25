# Where to get each file
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
