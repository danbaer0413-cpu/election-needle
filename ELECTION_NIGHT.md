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
| fmt | csv, json, xml or xlsx |
| json_records | for json: path to the list of counties, e.g. `data.counties` (blank if the file is a plain list) |
| json_explode | for json where each county has a nested list of candidates: the name of that list, e.g. `candidates` |
| county_col, dem_col, rep_col | only if auto-detect guesses wrong. Wide feed = one row per county. |
| cand_col, votes_col, party_col | long feed = one row per county x candidate. Party column is used if present |
| dem_name, rep_name | long feed without a party column: the two candidate names exactly as shown |
| pct_col | optional "percent reporting"; 100 marks a county final |

Most states fill in automatically (county, candidate, votes, party columns are detected). Georgia, Texas, Florida,
Ohio, Michigan, Wisconsin, Nevada, Maine, New Hampshire, Alaska... each differs, so check each one.

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
Maine and Alaska first-round counts exclude ranked-choice transfers; the needle shows the model's estimate of them.
