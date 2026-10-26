# Statewide-totals mode (election night)

Use it for any race where you only have the state's total vote, or where screenshots are the only county detail.

Per race, in its data folder (e.g. data/MI/u-s-senate/):

1. `statewide.csv`  (one row)
       dem,rep,pct_in,as_of
       1523400,1488200,41,2026-11-03 22:15
   dem/rep = votes counted statewide so far. pct_in = the state's "% reporting" (only a sanity check).
2. `reporting.csv`  (optional, from screenshots; any counties you can read)
       county,pct_in,dem,rep
       Wayne,85,,
       Oakland,100,310200,285000
   pct_in alone says how much of that county's expected vote is in. Add dem and rep when the screenshot shows counts;
   those counties are then used as real results.

run_update.py builds the county table itself: counties with counts stay as given, the rest of the statewide total is
spread by pct_in x expected votes, and one common shift to the baseline map makes the Dem total match exactly.
It prints a CHECK line when the percentages and totals disagree. Once a feed, paste or results.csv covers at least the
statewide total, the county data is used as is and these two files are ignored.

Send the screenshots here; I return the two files for each race and you upload them to the repository.

## Several sources per race (config/sources.csv)
List as many pages as you like for one race id. run_update.py reads each one, skips any that fail or show a bot check, keeps the
larger count for each county, takes the largest statewide total, and fills the rest with statewide mode.

    id,name,scope,url,fmt,sheet,...
    WI-governor,Dane County,county:Dane,https://elections.countyofdane.com/Election-Result/197,text,,
    NC-senate,NCSBE,statewide,https://er.ncsbe.gov/...,text,browser,

- scope `counties`: a county table (any feeds.csv format: html, browser, soe, ...).
- scope `statewide`: the page shows the state's D and R totals. fmt `text` finds the Dem and Rep surnames from config/candidates.csv
  followed by the first number of 1,000 or more. sheet `browser` draws the page in headless Chromium first.
- scope `county:<Name>`: same, for a single county's totals.
Government and county pages only. A page with a bot check is skipped, never bypassed. The starter rows are unverified;
rehearse them on the primary pages before the night, and check the log lines in the update run.

## Cross-race adjustment (cross_race.py, config/cross_race.json)
Races with at least 20% counted give a "surprise": current median minus the median the model had before any results. The races
still out get their prior moved by a shrunk, capped average of those surprises (same-state races count more than other states).
Settings: rho_national 0.5, rho_same_state 0.8, k 1.0 (more = more cautious), cap 6 points, skip list (NE races). Each run prints
"cross-race: <race> prior moved +x.x" and stores `cross_race_shift` and `surprise` in data/latest.json. Set "enabled": false to turn it off.

## Range headline, needle wiggle, all-races panel
- The race card now leads with the likely range (80% band), for example "R+0.4 to D+5.1", and the needle's bands narrow as votes come in.
- Toggle "Show the needle moving through its range" for a Play button that moves the needle at random points inside today's range (cosmetic).
- "All races together" (control.py): expected Democratic wins and the chance of more than half, for the Senate and governor races on the site,
  with part of each race's error shared across races (`rho_shared`, config/cross_race.json, default 0.5; 0 = independent races).
- Synthetic replay check (python backtest.py): the 80% band covered the true result 90-97% of the time through 75% counted, and the band
  narrows steadily (6.3 pts at 0% counted, 2.6 at 52%, 0.7 at 89%). That checks consistency, not real-world accuracy.

## How much the model trusts statewide-only numbers
Rows that statewide mode ESTIMATES (not real county counts) carry a `weight` below 1, so their total evidence is about one county's worth
with no county locations, and up to about four with screenshots covering most of the state (K_BASE 1, K_LOC 3 in statewide_mode.py).
Real county counts (feed, paste, or reporting.csv with dem and rep) keep full weight. Effect on a test North Carolina night (46% in, D+5.9
statewide): unweighted the model was far too sure (swing sd 1.1); weighted it is 2.7-2.9, and the polls keep most of the say until real county counts arrive.
`night.py` writes statewide.csv / reporting.csv from the command line; NIGHT_GUIDE.md lists every race's folder and link.

## electiontracker.live (switchable)
Rows in config/sources.csv with `switch=electiontracker` read statewide totals from https://electiontracker.live/results/ (Senate races in TX, ME, MI, OH, GA, NC, NH, IA, AK).
They run whenever config/switches.json has `"electiontracker": true` (now the default; set false to stop them). To switch it on or off, open that file on GitHub, press the pencil, change false/true,
and commit; it applies from the next update run. Safeguards: a vote total must be at least 20,000 (so poll sample sizes are ignored), and the row is skipped if the text
within 400 characters of the numbers mentions AP, Edison, Decision Desk, NBC, CNN, Fox or "licensed". That check cannot see attribution printed elsewhere on the page, so
read the page's own source label on election night and switch it off if the counts come from a licensed provider. The page was an empty placeholder on Oct 26.

## Correcting a scrape with a screenshot (force)
Default rule: the larger count wins, so a newer scrape (for example electiontracker.live) beats an older screenshot automatically.
When a scraped number is WRONG (a typo on a site, a reporting error that later drops), add `force` to statewide.csv:
    dem,rep,pct_in,as_of,as_of_utc,force,force_minutes
    800000,700000,41,2026-11-03 22:15,2026-11-04T03:15:00+00:00,yes,60
For the next 60 minutes (force_minutes) those numbers, and any county counts in reporting.csv, beat scraped ones even if smaller. After that the larger-count rule returns, so a stale
screenshot can never block fresh data. Command line: `python night.py NC-senate --dem 800000 --rep 700000 --force [--minutes 45]`. Send me a screenshot and say "force it" and I will write the files that way.
Numbers you read off CNN, NYT or any site by hand are fine to type in. They are your transcription.
