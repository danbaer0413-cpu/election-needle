# Data-collection prompts

Paste into a research tool that can browse AND run code (Claude with web search + code, ChatGPT with
browsing + data analysis, etc.). The tool must download the official files and build the CSVs in code,
not type numbers from memory. Check the totals it prints against certified results before using anything.

Years: 2016, 2018, 2020, 2022, 2024 (two midterms + three presidential years, so the midterm electorate
is in there). Optional analog: 2006, the last midterm with a lame-duck president at a low approval
rating. 2006 is for the county lean pattern and poll error, NOT for turnout (population has changed).

Where files go:
- history_results.csv  -> `python build_baseline.py history_results.csv --state GA --race "Governor"`
- early_2026.csv       -> data/<ST>/<race>/early.csv (re-pull daily)
- rcv_history.csv      -> data/ME/rcv_history.csv or data/AK/rcv_history.csv
- poll_error_history.csv (Prompt B) -> data/poll_error_history.csv
- poll_inputs_2026.csv (Prompt D)   -> data/poll_inputs_2026.csv (the needle reads each race's poll from it)
Then run `python validate.py`.

POLLSTER QUALITY RULE used in Prompts B and D (same rule both times, so history and today match):
- Ratings: Silver Bulletin's pollster ratings (latest annual update; letter grade from Predictive
  Plus-Minus; the "Pollster Stats Full" Excel is downloadable from natesilver.net). Use FiveThirtyEight's
  archived pollster-ratings.csv (on DataHub) for pollsters missing from Silver Bulletin and for pre-2016 polls.
- Tier 1 = grade B+ or better. Tier 2 = grade B or B-. Anything lower, unrated, or banned is excluded.
- Exclude polls sponsored by campaigns, parties or partisan groups.
- Caveat: today's ratings are computed using past polls, so applying them to old races flatters the
  top-rated pollsters a little. Fine for a quality filter; don't treat the history as a clean out-of-sample test.

---

## PROMPT A  (one run per state: AK FL GA IA KS ME MI MN MS NE NH NV OH SC TX WI)

```
Task: collect election data for [STATE] and output ready-to-use CSV files for an election-night model.

RULES
- Use official sources only: the state's elections office / Secretary of State, county clerks, MIT Election
  Data and Science Lab, OpenElections. No news articles, no numbers from memory.
- DOWNLOAD the real files and build the CSVs with code. If you cannot download a file, give me the exact URL
  and file format and leave that CSV out. Say so plainly.
- After each CSV print: row count, number of distinct units, and for each year+race the statewide total
  Democratic votes and Republican votes, so I can check them against the official certified totals.
- Reporting unit = whatever the state reports results by (counties; boroughs/election districts in Alaska;
  towns in New England if results are by town). Tell me which, and use it consistently in every file.
- Unit names: official name WITHOUT the words "County", "Parish" or "Borough". Same spelling in every file.

FILE 1: history_results.csv
County-level certified GENERAL-election results for every statewide race for President, U.S. Senate (regular
and special) and Governor held in [STATE] in these years: 2016, 2018, 2020, 2022, 2024.
[OPTIONAL, add this line if available: also 2006.]
One row per unit per race.
Columns, exactly and in this order:
state,county,year,race,dem_votes,rep_votes,other_votes,early_votes
- state: 2-letter code. year: 4 digits.
- race: exactly one of  President | U.S. Senate | U.S. Senate (special) | Governor
- dem_votes / rep_votes: votes for the Democratic and Republican nominee. other_votes: all other candidates
  combined (write-ins included). Where ranked-choice was used, give FIRST-ROUND votes.
- early_votes: early in-person plus mail/absentee ballots counted in that unit for that election, if the state
  publishes it. Leave blank if not. Do not estimate.
- If a candidate backed by a major party ran as an independent (or a major party had no candidate), keep the
  columns as the ballot shows them and list those races in a note after the file.
- Flag any unit whose name or boundaries changed between the years.

FILE 2: early_2026.csv
The CURRENT early-voting / absentee ballot return data for the Nov 3, 2026 general election.
Columns, exactly: county,early_returned,d_reg,r_reg,o_reg
- early_returned: total ballots returned/accepted so far in that unit (early in-person + mail combined).
- d_reg / r_reg / o_reg: of those ballots, how many were from voters registered Democratic / Republican /
  other-or-unaffiliated. Leave all three blank if the state does not record party registration.
Also give: the URL of the live source file, its format, the exact column names in it, how often it updates,
and the date/time the data you used was current as of.

FILE 3 (no CSV; answer in a table)
Election night, Nov 3, 2026: the official results page/feed URL; format (CSV/JSON/XML/HTML); whether it is
unit-level; the vendor if visible (Clarity/Scytl, Enhanced Voting, ElectionStats, other); exact field or
column names for unit, Democratic votes, Republican votes and percent reporting; update frequency.
Also: poll closing time(s) with time zone; whether early/mail votes are reported first, last, or mixed;
deadline for mail ballots to be received; whether Senate/governor can go to a runoff (and the threshold) or
use ranked-choice tabulation; whether results are labeled by vote method (early / Election Day / mail).

[ONLY IF STATE IS MAINE OR ALASKA]  FILE 4: rcv_history.csv
Every statewide ranked-choice contest held in [STATE] in 2016, 2018, 2020, 2022 and 2024 (general elections
first; list primaries separately and mark them, because the electorate differs).
Columns, exactly: contest,d_round1,r_round1,other_round1,d_final,r_final
- Statewide totals. d/r = the Democratic-side and Republican-side candidates who reached the final round.
- other_round1 = first-round votes for every other candidate. d_final / r_final = votes in the final round.
- contest = a short label like "2022 AK House special general".

Finish with a checklist: each file -> built from downloaded data / links only / not found, plus any data
quality problems you noticed (missing units, changed unit boundaries, renamed units between years).
```

---

## PROMPT B  (run once, all states): poll error history from top-rated pollsters

```
Task: build poll_error_history.csv, the track record of top-rated pollsters' final polling averages against
certified results for U.S. statewide races in 2016, 2018, 2020, 2022 and 2024 [OPTIONAL: and 2006].

SOURCES
- Poll-level data: Silver Bulletin's raw polls file (natesilver.net, "Rawpolls", 12,300+ polls) and/or
  FiveThirtyEight's archived raw-polls.csv (DataHub). Say which you used for each year.
- Pollster quality: Silver Bulletin's latest pollster ratings (letter grade, "Pollster Stats Full" Excel);
  FiveThirtyEight's archived pollster-ratings.csv for pollsters Silver Bulletin does not rate and for
  pre-2016 polls.
- Certified results: official state sources or MIT Election Data and Science Lab.

RULES
- DOWNLOAD the real data and do everything in code. No numbers from memory. If something is missing, say
  what, and leave it out; do not fill gaps.
- Keep only polls from pollsters graded B+ or better (Tier 1). If a race has fewer than 2 Tier 1 polls in the
  window, also allow grades B and B- (Tier 2). Exclude lower-graded, unrated and banned pollsters and any
  poll sponsored by a campaign, party or partisan group.
- Window: polls whose field dates END within 21 days before the election. Take each pollster's LATEST poll
  in the window, then average them, weighting by square root of sample size (equal weights if sample size
  is missing).
- Convert to the two-party margin: (Dem% - Rep%) / (Dem% + Rep%) * 100. Positive = Democrat ahead.

FILE: poll_error_history.csv
One row per state per statewide race that had qualifying polls: President (2016, 2020, 2024), U.S. Senate
and Governor (every year held in those years; include special elections).
Columns, exactly: state,year,race,poll_margin,actual_margin,n_polls,rule_used
- state: 2-letter code. year: 4 digits. race: President | U.S. Senate | U.S. Senate (special) | Governor
- poll_margin: the weighted two-party margin above. actual_margin: certified result, same form:
  (Dem votes - Rep votes) / (Dem + Rep) * 100.
- n_polls: number of polls averaged. rule_used: tier1 | tier1+2 | thin (thin = only one qualifying poll).
After the file print: row count by year, by race and by rule_used; the rating edition and poll source used
for each year; and the list of state-race-years with no qualifying polls.
```

---

## PROMPT D  (run once, re-run weekly and the day before the election): current polls, top-rated only

```
Task: build poll_inputs_2026.csv, the current polling average for these Nov 3, 2026 races using ONLY
top-rated pollsters.

Races (id: state, race): OH-senate: Ohio, U.S. Senate (special) | OH-governor: Ohio, Governor |
MI-senate | MN-senate | IA-senate | KS-senate | KS-governor | NE-senate | NE-governor | ME-senate |
ME-governor | AK-senate | TX-senate | TX-governor | SC-senate | MS-senate | FL-governor | GA-governor |
GA-senate | NV-governor | WI-governor | NH-senate  (state = the state in the id; race = Senate or Governor)

RULES
- Find the individual public polls for each race (pollster, field start/end dates, sample size, Democratic %,
  Republican %, other %). Cite the page each poll came from. No numbers from memory.
- Pollster quality: Silver Bulletin's latest pollster ratings (letter grade). Keep only grades B+ or better
  (Tier 1); if a race has fewer than 2 Tier 1 polls, also allow B and B- (Tier 2). Exclude lower-graded,
  unrated and banned pollsters, and polls sponsored by campaigns, parties or partisan groups.
- Window: polls with field dates ending in the last 21 days up to today. Use each pollster's latest poll,
  weight by square root of sample size, and average.
- Margin = (Dem% - Rep%) / (Dem% + Rep%) * 100, positive = Democrat ahead. For a race where the main
  Democratic-side candidate is an independent (for example Nebraska Senate), use that candidate and say so.

FILE: poll_inputs_2026.csv
Columns, exactly: id,poll_margin,n_polls,rule_used,pollsters,window_start,window_end
- rule_used: tier1 | tier1+2 | thin (one qualifying poll) | none (leave poll_margin blank)
- pollsters: names separated by semicolons. Dates as YYYY-MM-DD.
After the file print each race with its n_polls and rule_used, and list the individual polls used so I can
spot-check them.
```

---

## OPTIONAL PROMPT C  (replays real election nights; often unavailable)

```
Find any archived, timestamped county-level election-night results for [STATE] for the 2022 or 2024
general election: snapshots or a feed history showing votes counted over time (for example archived
JSON/XML feeds, Wayback Machine captures of the official results site, or published reporting timelines).
Give exact URLs and formats. Do not reconstruct timelines from memory or news stories; if nothing
timestamped exists, say so.
```
