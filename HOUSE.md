# House live progress (election night)

What it does: reads each U.S. House district's "% counted" from the page(s) in config/house_sources.csv, turns that into a county "% counted"
with data/house/crosswalk.csv, and hands it to statewide mode. It never changes a vote count; it only tells statewide mode WHERE the counted
vote sits when a race has a statewide total but no county counts. Typed reporting.csv entries and real county counts always win.

Off by default: config/switches.json -> "house": false.

## Before the polls close (Nov 2)
Actions -> rehearse-readers -> look at data/house_check.txt (it reads the pages now; pages will show no votes yet, so expect little or nothing).

## Election night, once the first House results appear (~7 pm ET)
1. Locally or in a Codespace:  python check_house.py   (reads every row of config/house_sources.csv, writes nothing)
2. Compare the printout to the page. If the percents match for the districts you can see, edit config/switches.json on GitHub: "house": true
3. If they do not match, leave it off and type district percents instead:  python house_pct.py MI-senate 13=85 12=60 11=70 --keep
4. electionhub.org is a slow second source (30 minutes) and relays AP/Decision Desk calls as a backup: it is off ("electionhub": false). Leave it off.

Ohio is not supported (its crosswalk is on the old lines). Florida and Texas split-county shares are partly missing, so their county percents are rough.
Counts only go up: a district's percent never drops once saved (data/house/live.csv). Delete that file to reset.
