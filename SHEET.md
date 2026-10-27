# Election-night sheet

One table for everything you read off screenshots or sites. The update run turns it into each race's statewide.csv and reporting.csv.

Columns: race, county, dem, rep, pct_in, as_of, source, force, minutes   (see data/election_night_EXAMPLE.csv; DO NOT put the example rows in the real file)
- race: the race id (MI-senate, WI-governor ...). county: blank or STATE = the statewide total. dem/rep: vote counts. pct_in: % counted.
- as_of: when you read it (Eastern), e.g. 2026-11-03 21:40. source: free text. force=yes: beats scraped numbers for `minutes` (default 60).

Two ways to use it (both work at the same time):
A. Google Sheet: make a sheet with those column headings -> File > Share > Publish to web > choose the sheet tab and "CSV" > copy the link
   into config/sheet.json  {"url": "<link>", "file": "data/election_night.csv"}. Publish-to-web copies refresh about every 5 minutes.
   The link is public to anyone who has it, so put nothing private in the sheet.
B. The file data/election_night.csv in the repo: edit it on GitHub (pencil icon), add rows, commit.

Tips: one row per place and time; adding a newer row is fine (the row with the most votes / highest % wins, a forced row wins inside its window).
Send me screenshots and I will give you rows to paste. A race that has no rows in the sheet is left alone.

Early vote: a file named early_<anything>.csv in data/night/ with columns race,county,early_returned,d_reg,r_reg,o_reg is merged into that race's early.csv (a county is replaced only if the new returned count is at least the old one). See data/night/early_EXAMPLE.csv.txt.

Batches: every *.csv file in data/night/ is read as well. When I turn your screenshots into rows I give you a file (e.g. night_2140.csv):
upload it to data/night/ on GitHub (Add file > Upload files) and start the update run. Nothing has to be merged into an existing file.
