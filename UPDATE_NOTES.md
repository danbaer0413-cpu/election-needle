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
