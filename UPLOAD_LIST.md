# What to upload

Upload everything in this zip. It already leaves out files your GitHub runs create
(data/latest.json, needle_log.csv, polls_all.csv, poll_inputs_auto.csv, poll_average.json, polls_raw/, bsky_*, votehub_*)
and your hand-typed data/poll_inputs_2026.csv, so uploading cannot overwrite them.

New or changed in this round:
- poll_error_fit.py, POLL_ERROR.md, config/poll_error.json (new); run_update.py, check_setup.py, README.md (changed)
- backtest_poll_average.py (new, optional), config/fundamentals.json (sd_fund 12), POLL_ERROR.md, FUNDAMENTALS.md (changed)
- probe_portals.py, config/results_portals.csv, .github/workflows/probe-portals.yml (new); config/feeds.csv (portal notes added), ELECTION_NIGHT.md (changed)
- maps.py, build_geo.py, .github/workflows/build-geo.yml (new); app.py (Race/Map switch), README.md (changed). After uploading run Actions -> build-geo once so the county map has outlines.
- config/races.json (ME-governor now plurality; AK-governor now ranked-choice), ELECTION_NIGHT.md (changed)
- votehub.py (now archives every VoteHub post to data/votehub_raw.jsonl), votehub_samples.py and .github/workflows/votehub-samples.yml (new), .github/workflows/update.yml (commits the archive)
Earlier round:
- fundamentals.py, check_setup.py (new)
- FUNDAMENTALS.md, UPLOAD_LIST.md, README.md
- config/fundamentals.json, data/fundamentals_inputs.csv, data/fundamentals.csv, data/midterm_analogs.csv (new)
- model.py, run_update.py, app_advanced.py (changed)
- .github/workflows/update.yml (preflight step, safer push)

Then: Actions -> update-needle -> Run workflow.
Before Nov 1: update generic_ballot_margin_dem and generic_ballot_asof in config/fundamentals.json,
and refresh data/poll_inputs_2026.csv from Silver Bulletin.


## Final round (consolidated zip)
Unzip over your repo (replace files). New/changed: feeds.py, check_readers.py, probe_ne.py, config/feeds.csv, config/results_portals.csv, LINKS.md, ELECTION_NIGHT.md, UPLOAD_LIST.md, .github/workflows/rehearse-readers.yml and update.yml, requirements-runner.txt.
Then run Actions -> rehearse-readers once and send me data/rehearsal.txt and data/portal_ne.txt.
