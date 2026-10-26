# Election night guide (paste and screenshot races)

For every race below, send me a screenshot (or numbers) and I return the files, or run `night.py` yourself (see its header).

- Statewide totals -> `statewide.csv` (dem, rep, pct_in). Counties you can read -> `reporting.csv` (county, pct_in, optional dem, rep).
- Statewide-only numbers carry about one county's worth of evidence in the model; the more counties you can add, the more the model trusts it.
- Counties with real counts (feed, paste file or reporting.csv) are used exactly as given.

| Race | Folder | Automatic? | Best link / what to screenshot |
|---|---|---|---|
| OH-senate | data/OH/u-s-senate-special | yes (ohio) | Ohio JSON API (found by probe); contest found by name; portal https://liveresults.ohiosos.gov; Secretary of |
| OH-governor | data/OH/governor | yes (ohio) | Ohio JSON API (found by probe); contest found by name; portal https://liveresults.ohiosos.gov; Secretary of |
| MI-senate | data/MI/u-s-senate | no - screenshots | https://www.michigan.gov/sos/elections/election-results-and-data |
| MN-senate | data/MN/u-s-senate | no - screenshots | https://electionresults.sos.mn.gov/Results/Index?ersElectionId=<general id>&scenario=USSenate (intermittent Ra |
| IA-senate | data/IA/u-s-senate | yes (soe) | Iowa SOE Software JSON (found by probe); uses a normal headless browser if the site's invisible check blocks p |
| KS-senate | data/KS/u-s-senate | no - screenshots | https://sos.ks.gov/elections/election-results.html (Power BI report, refreshed rarely): paste |
| KS-governor | data/KS/governor | no - screenshots | https://sos.ks.gov/elections/election-results.html : paste |
| NE-senate | data/NE/u-s-senate | no - screenshots | https://electionresults.nebraska.gov/resultsSW.aspx?type=SW&map=CTY (data service neresultswebservice.azureweb |
| NE-governor | data/NE/governor | no - screenshots | https://electionresults.nebraska.gov/resultsSW.aspx?type=SW&map=CTY |
| ME-senate | data/ME/u-s-senate | no - screenshots | https://www.maine.gov/sos/elections-voting/election-results-data (xlsx files posted after the election): paste |
| AK-senate | data/AK/u-s-senate | yes (alaska) | Alaska precinct CSV results/26GENR/ENRbyPrecinct.csv, added up to House districts; page https://www.elections. |
| TX-senate | data/TX/u-s-senate | yes (texas) | Texas static JSON (found by browser probe); race and 2026 election id found automatically; portal https://res |
| TX-governor | data/TX/governor | yes (texas) | Texas static JSON (found by browser probe); race and 2026 election id found automatically; portal https://res |
| SC-senate | data/SC/u-s-senate | yes (soe) | South Carolina SOE Software (same platform as Iowa); works once the 2026 general is listed |
| MS-senate | data/MS/u-s-senate | no - screenshots | https://www.sos.ms.gov/elections-voting/election-results : paste |
| FL-governor | data/FL/governor | yes (florida) | Florida Election Watch county table |
| GA-governor | data/GA/governor | yes (georgia) | Georgia SOS API (found by probe); race and county breakdown read automatically |
| NV-governor | data/NV/governor | no - screenshots | S Clark https://elections.clarkcountynv.gov/ElectionResultsTV/ |
| WI-governor | data/WI/governor | no - screenshots | S Dane https://elections.countyofdane.com/Election-Result/197 |
| GA-senate | data/GA/u-s-senate | yes (georgia) | Georgia SOS API (found by probe); race and county breakdown read automatically |
| ME-governor | data/ME/governor | no - screenshots | https://www.maine.gov/sos/elections-voting/election-results-data : paste on the night |
| NH-senate | data/NH/u-s-senate | no - screenshots | https://www.sos.nh.gov/2026-election-results (Akamai blocks bots: paste |
| FL-senate | data/FL/u-s-senate-special | yes (florida) | Florida Election Watch county table |
| SC-governor | data/SC/governor | yes (soe) | South Carolina SOE Software (same platform as Iowa); works once the 2026 general is listed |
| IA-governor | data/IA/governor | yes (soe) | Iowa SOE Software JSON (found by probe); uses a normal headless browser if the site's invisible check blocks p |
| AK-governor | data/AK/governor | yes (alaska) | Alaska precinct CSV results/26GENR/ENRbyPrecinct.csv, added up to House districts; page https://www.elections. |
| MI-governor | data/MI/governor | no - screenshots | https://www.michigan.gov/sos/elections/election-results-and-data |
| MN-governor | data/MN/governor | no - screenshots | https://electionresults.sos.mn.gov/Results/Index?ersElectionId=<general id>&scenario=Governor (statewide total |
| NH-governor | data/NH/governor | no - screenshots | https://www.sos.nh.gov/2026-election-results (Akamai blocks bots: paste) |
| NC-senate | data/NC/u-s-senate | yes (ncsbe) | https://er.ncsbe.gov/?election_dt=11/03/2026&county_id=0&office=FED&contest=0 (NC State Board of Elections res |

Automatic races fall back to screenshots the same way if their feed fails.
