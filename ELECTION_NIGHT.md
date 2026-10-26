# Election night: plug and play

The GitHub job already runs every 10 minutes from 7pm ET Nov 3. For each race it reads, in this order:
1. the URL in `config/feeds.csv` (one row per race)
2. `data/<race folder>/results.csv` (pasted or hand-made; also the automatic fallback if the URL fails)
3. nothing yet -> keeps showing the pre-election needle

## Step 0: let GitHub look for the feeds (new)
`config/results_portals.csv` holds the official results portal for each state (from your spreadsheet). On GitHub go to
Actions -> probe-portals -> Run workflow. In about a minute it saves `data/portal_probe.txt`: for each portal, the data-looking
links (.json/.csv/.xml, /api/, download) found in the page and its scripts. Send me that file and I will fill in `config/feeds.csv`.
Portals that load their tables in the browser (single-page apps) will say so; use the Network-tab method below for those.
Only the portals marked Yes in the `verified` column were confirmed to exist; the rest are from memory, so click them first.
Wisconsin has no state-run live feed (results are on county clerk sites), so WI-governor will need the paste fallback or a few county feeds.
The Alaska portal folder for 2026 is unconfirmed; Michigan's statewide page only fills in once all counties report.

## Nov 2 (or any time the state results pages are live): find the feeds
For each race, open the state's results page in Chrome/Safari, open developer tools -> Network -> reload,
filter by Fetch/XHR, and look for the file that returns county-level numbers (.json, .csv, .xml).
Right-click -> copy link address. (If the page offers a "Download" button for county results, copy that link.)
Put it in `config/feeds.csv` (edit the file on GitHub with the pencil icon):

| column | what to put |
|---|---|
| url | the link (or leave blank) |
| fmt | csv, json, xml, xlsx or **html** (a results web page with a county table) |
| json_records | for json: path to the list of counties, e.g. `data.counties` (blank if the file is a plain list) |
| json_explode | for json where each county has a nested list of candidates: the name of that list, e.g. `candidates` |
| county_col, dem_col, rep_col | only if auto-detect guesses wrong. Wide feed = one row per county. |
| cand_col, votes_col, party_col | long feed = one row per county x candidate. Party column is used if present |
| dem_name, rep_name | long feed without a party column: the two candidate names exactly as shown |
| pct_col | optional "percent reporting"; 100 marks a county final |

Most states fill in automatically (county, candidate, votes, party columns are detected). Georgia, Texas, Florida,
Ohio, Michigan, Wisconsin, Nevada, Maine, New Hampshire, Alaska... each differs, so check each one.

### Results web pages (fmt = html)
If a state only has a normal web page with a county table (no data file), put the page address in `url` and `html` in `fmt`.
The reader finds the table whose first column matches our baseline counties and picks the Democrat's and Republican's vote
columns by candidate last name (from config/candidates.csv, or `dem_name` / `rep_name` if you fill them in). It copes with
two-row headers, percent columns, commas, a Total row and tables printed sideways. A page that builds its table in the
browser (JavaScript) will not work; look for its data file instead (probe-deep helps), or use the paste fallback.

## Test it
    python check_feeds.py            # all races with a URL
    python check_feeds.py --id TX-senate
It shows rows found, counties matched to your baseline, and statewide D/R. Any county named in red text
("IN FEED BUT NOT BASELINE") is a spelling mismatch to fix. Early in the night most counties are
simply not reporting yet; that is fine.
You can run this on the Actions page too if you add a step, but the easiest test is on your laptop.

## If a feed breaks or does not exist (paste fallback)
Copy the county table from the state page, then:
    python paste_results.py TX-senate --cols dem,rep,pct   # paste, then Ctrl-D
or create `data/<race folder>/results.csv` on GitHub with columns `county,dem,rep,final` (final = TRUE once
a county is done). The next 10-minute run picks it up. You can also send me the table and I will do it.

## Priority order
GA, MI, NV, WI, TX, OH, NH, ME, AK, IA, KS, NE, then the safe races.

## What I could not test
No feed has been tried against a live state site. The adapter has been tested with fake wide CSV, long CSV
(with party) and nested JSON files, and the paste tool with a fake table, all through the full model.
Alaska reports by election district; the baseline units are those districts, so match on those names.
Ranked-choice: Maine uses it for the Senate general only (the governor general is plurality, so ME-governor has no transfers). Alaska uses it for both Senate and governor. First-round counts exclude transfers; the needle shows the model's estimate of them, and Alaska's tabulation is scheduled for Nov 18 if no one tops 50%. Alaska Ballot Measure 2 (repeal of RCV) is on the ballot but does not change how this election is counted.

## fmt=browser (page reader for sites with no data feed)
Use it for government or county results pages that draw their numbers with scripts, so a plain download shows an empty page.
In `config/feeds.csv` set `url` to the page, `fmt` to `browser`, and (optional) `sheet` to the text of a tab or link to press first, such as `Governor`.
It opens the page in a headless browser, waits for the numbers, then reads the county table the same way `fmt=html` does.
If a page shows a bot check (Minnesota, Nevada, New Hampshire so far) it stops with a "paste this race instead" message; it never tries to get past a check.
It is slower than a data feed (about 15 to 30 seconds per page), so use it only where no feed exists. Test it against last cycle's results page first.

## Automatic readers (config/feeds.csv `fmt`)
Set `url` to the site root; leave `sheet` blank unless noted. A reader that cannot find the 2026 general yet fails cleanly and the paste file is used instead.
- `texas` (TX): results.texas-election.com static JSON, county level. Appears once the state lists the Nov 3 general.
- `ohio` (OH): liveresults.ohiosos.gov API. Shows mock data until election day.
- `georgia` (GA): results.sos.ga.gov Enhanced Voting API, slug 11032026GeneralAndSpecialElection.
- `soe` (IA, SC): SOE Software ENR (sum.json/details.json). For a rehearsal on 2024 use `sheet=year:2024`.
- `florida` (FL): floridaelectionwatch.gov race pages, county tables. Results start after 8 PM ET.
- `alaska` (AK): results/26GENR/ENRbyPrecinct.csv, added up to House districts. The big absentee count lands days later.
- `browser`: any county-table page, rendered headless. Stops with "paste this race instead" on a bot check.

Everything else (MI, MN, NV, WI, NH, ME, KS, MS, NE) is paste. Best links are in config/feeds.csv notes, config/results_portals.csv and LINKS.md.

## Rehearsal
Actions -> rehearse-readers. It runs each reader on 2024 results and compares to our history files (PASS = 98% of counties match and totals within 0.5%). It also scans Nebraska's service (data/portal_ne.txt).

### More readers
- `ncsbe` (NC): NCSBE election-night precinct file `results_pct_20261103.zip` (tab-delimited), added up to counties. Set in feeds.csv. Rehearsed on 2024.
- `flfile` (FL): the Division of Elections election-night text file; a second source for Florida in config/sources.csv (the larger county count wins). Rehearsed on 2024.
- `probe_files.py` (runs with rehearse-readers): checks which result files exist for NC, FL, MI, KS, NH, ME, MN, MS, WI, NE and shows past-file layouts in data/portal_files.txt.
