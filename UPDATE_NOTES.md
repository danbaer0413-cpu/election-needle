# Updates, Oct 27-29 (upload all of these, keep the folder structure, then run Actions -> update)

Model and ratings
- model.py: caps on early-vote evidence (1.5 pts each), 6.5-pt uncertainty floor, data-driven early/Election Day gap, per-county over/under-performance columns
- config/poll_error.json: new `race_bias` section (candidate-specific poll miss, e.g. Collins; ME-senate = 0.0 until you set it)
- config/fundamentals.json: generic ballot shrink 0.85 -> 0.70
- run_update.py: reads race_bias; writes the House lean file

App screens
- app.py, charts.py, maps.py, explain.py, changes.py: ratings in words, D+/R+ everywhere, "What's behind this number", over/under line under the needle, county-map color switch, Senate and House views, error boxes on the maps
- senate_view.py, config/senate_seats.json, data/senate_called.csv: Senate seat chart
- house_lean.py, house_view.py, data/house/*: House lean map, seat chart, slider (called.csv is empty and config/house_totals.json holds the called-seat counts, both included because no House calls had been typed)

Data and calls
- civic_early.py, config/civic_early.json: civicAPI early vote (all auto)
- auto_calls.py, config/call_accounts.json: automatic calls, two sources must agree (check the Bluesky handles)
- civic_probe.py + workflows: election-day readiness probe (run Nov 2 and Nov 3)
- .github/workflows/update.yml: includes the civicAPI step, the push fix and the automatic-calls step

First run: run the update workflow by hand. Auto calls should print "0 called".

## All needles tab (Oct 30)
New "All needles" view: every race's needle in one instrument-cluster grid (cluster_view.py + one line set in app.py).
Filters: All / Senate / Governor; order: closest first / by state / most Dem first; 2-4 dials per row. Hover for numbers.

## Needle restyle, no-zoom, national needle (Oct 30)
- charts.py: Race-tab needle restyled (white needle, bright 80% / faint 90% bands, tick labels, dark dial face); touch no longer zooms or drags it.
- cluster_view.py: All needles tab, now with the National environment needle at the top and zoom locked.
- national_env.py (new) + run_update.py: writes a "national" block to data/latest.json (model assumption D+6.4, moved by races with 20%+ counted).
- app.py: passes the national block to the All needles tab.
Upload: charts.py, cluster_view.py, national_env.py, run_update.py, app.py, UPDATE_NOTES.md. Then run Actions -> update.

## Cook House ratings refresh (Oct 30)
data/house/ratings_2026.csv now has 85 non-safe seats (was 81). config/house_totals.json solid_D 186, solid_R 164.
Moved: OH-09, PA-08 Toss-up -> Leans Dem; CO-05, PA-01, SC-01 Leans Rep -> Toss-up; FL-07, FL-09, IN-05 Likely Rep -> Leans Rep.
Added (were Solid R): NC-05, NC-09, NJ-02, WA-05 as Likely Rep.
