# Election Needle

    pip install -r requirements.txt
    streamlit run app.py

1. Pick State -> Level (Federal / State / Local) -> Race in the sidebar.
2. `python new_race.py NC "U.S. Senate"` creates `data/NC/u-s-senate/` with blank CSVs and NOTES.md
   (where each column comes from). The app auto-loads that folder.
3. Before Election Day: update `early.csv` daily from the state's ballot-return file. The needle
   moves off the polling prior using early/mail returns (party registration where the state has
   it, geography everywhere).
4. Election Night: use Live feed (see `feeds.py`; write a column mapping per state) or drop in
   `results.csv`.

Test first: `python backtest.py` (synthetic) and the Replay demo in the app.
Before trusting it: replay last cycle's same race with real timestamped county returns and tune
`early_gap`, `party_bias`, and the noise settings.

Files: model.py (core), synthetic.py (test data), backtest.py, feeds.py (scraper helpers, untested
against live feeds), states.py (state/race registry), charts.py, app.py, new_race.py.

## Poll-error history (optional, recommended)
`python poll_error.py history.csv` or load it in the app sidebar (Historical poll error).
Columns: state, year, race, poll_margin, actual_margin (D-R). Use the final polling average and
the certified result for as many past statewide races as you can (Senate, governor, president).
Output per state: shrunk bias, spread, plus a pooled common-year spread and skew shape.
Past misses have not always repeated, so bias is shrunk hard; treat it as a nudge, not a rule.

## Run it on GitHub (no Claude needed on election night)
1. Create a GitHub repo and push this folder. Settings -> Actions -> General -> Workflow
   permissions: "Read and write".
2. Add each race to `config/races.json` (copy from `config/races.example.json`) and commit its
   `data/<ST>/<race>/counties.csv`. Set `poll_margin` and `params` there.
3. `.github/workflows/update.yml` runs `run_update.py` every 12 hours, then every 10 minutes from
   Nov 3 evening to Nov 4 morning (UTC cron; GitHub can start runs a few minutes late). It commits
   `data/latest.json` and `data/needle_log.csv`. Use Actions -> update-needle -> "Run workflow"
   to test by hand.
4. Deploy `app.py` (e.g. Streamlit Cloud) and choose "Latest published (GitHub)". Local: leave the
   URL blank. Hosted separately: paste the raw GitHub URL of data/latest.json.
5. After election week, disable the workflow.
Test locally: `python run_update.py` then `streamlit run app.py`.

## Ballot rules, ranked-choice and the explanation panels
- Georgia (majority required): `runoff_rule` simulates the chance nobody clears 50% of ALL ballots
  (needs `third_share`, the other candidates' first-round share) and the runoff itself
  (`runoff_shift`, `runoff_sd`). Win chance = win outright + runoff x chance of winning it.
- Maine and Alaska (ranked-choice): `rcv` moves other candidates' ballots to D and R using
  `rcv_to_d` / `rcv_to_r`. Calibrate from past ranked-choice contests with `python rcv.py
  rcv_history.csv` (columns: contest, d_round1, r_round1, other_round1, d_final, r_final); the app
  and `run_update.py` (config key `rcv_history`) do it automatically. Needle shows first-round and
  after-transfer numbers. Alaska reports by election district and late ballots keep counting after
  election night, so treat early Alaska numbers as first-round counts only.
- `third_share` defaults in states.RULES are placeholders. Set them from polls or past results.
- The app's "What's moving the needle" panel shows which evidence drives the swing estimate and
  net votes by Solid/Lean/Toss-up tier (the "firewall"). "What's been inputted" lists every
  assumption and warns about missing data. Same text is built in explain.py.

## Getting the data in
`PROMPTS.md` has the research prompts (one per state, one for poll history). They ask for CSVs in the
exact formats below. Then:
1. `python build_baseline.py history_results.csv --state GA --race "Governor"` builds counties.csv from
   ten years of county results (weights and growth are options; prints statewide margins to check).
2. Save the early-vote pull as `data/<ST>/<race>/early.csv`; poll history as `data/poll_error_history.csv`;
   Maine/Alaska ranked-choice history as `data/<ST>/rcv_history.csv`.
3. `python validate.py` flags missing columns, mismatched unit names and odd numbers before you rely on them.
Unit names are matched ignoring case, "County/Parish/Borough", "Saint/St." and hyphens.

## Years and pollster quality
- History years: 2016, 2018, 2020, 2022, 2024. Midterm years (2018, 2022) carry the most weight in
  `build_baseline.py` (default margin weights `2024:0.2,2022:0.3,2020:0.1,2018:0.25,2016:0.05`; turnout
  weights use midterms only). The poll-error expander has a "Years to include" filter.
- Optional 2006 analog (last lame-duck-president midterm at low approval): add it to the history file and
  pass e.g. `--margin-weights "2024:0.2,2022:0.3,2020:0.1,2018:0.25,2016:0.05,2006:0.1"`. Use it for county
  lean only, not turnout. County and poll data for 2006 may be sparse.
- Polling averages: PROMPTS.md Prompt B (history) and Prompt D (2026) use only top-rated pollsters
  (Silver Bulletin grade B+ or better; B/B- only if fewer than 2 qualify). Save Prompt D's output as
  `data/poll_inputs_2026.csv`; `run_update.py` uses it for any race without its own `poll_margin`.
