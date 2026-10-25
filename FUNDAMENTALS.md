# Fundamentals prior

An independent, structure-only estimate of each race, entered into the model as one more precision-weighted
observation (label "fundamentals"). Not copied from any forecaster. Every input is below with its source.

## Formula
`fund_margin = 2024 presidential margin (state) + k x (0.85 x generic ballot - 2024 national margin) + approval adjustment`

| Piece | Value | Source |
|---|---|---|
| Generic ballot | D+9.1 | Silver Bulletin average, updated Oct 23, 2026 (Pew RV poll D+8, Oct 8, as cross-check) |
| 2024 national margin | R+1.5 (two-party) | Harris 48.3, Trump 49.8 |
| Expected House margin | D+7.7 | 0.85 x the generic ballot: late averages overstated the final House vote in some wave years (2006 by ~3) |
| National swing | +9.2 toward D | difference from 2024 |
| k (pass-through into statewide races) | 0.75 | 0.5 pooled backtest, raised to the midpoint of 0.5 and 1.0 because the swing is wave-sized, as in 2018 (judgment, see analogs) |
| State lean | each state's own 2024 presidential result | data/*/history_results.csv |
| Approval adjustment | 0.10 x gap, capped at +/-2 | Civiqs state Trump net approval (Newsweek, Oct 20 and Oct 6, 2026) vs what 2024 lean predicts |

## Backtest (2018 and 2022 competitive statewide races, n=54)
* Prior presidential margin plus the actual House swing misses by **10.5 points RMSE out of sample** (leave-one-year-out).
* The swing passed through unevenly: 2018 about 1:1 (Dems gained 6.8 vs a 6.5 national swing), 2022 almost none (Republicans gained 0.4 vs a 7.3 national swing). With only two midterms, k is uncertain (0.05 to 1.05 depending on the year left out). I use the pooled 0.5.
* Polls in the same races missed by about 3.8 points. Blending showed the best result at roughly 10% fundamentals weight. With sd_poll 5.0 and sd_fund 10.5 the model gives it about 18% where polls are normal and more where they are thin.
* Not validated: the approval adjustment (no state approval history exists for 2018/2022). It moves races by 1.4 points at most.

## What the environment says (sources)
* Generic ballot D+9.1 (Silver Bulletin); Pew D+8.
* Democrats beat their 2024 presidential margins by about 11 points on average in 2026 special elections (The Downballot).
* Gallup (Oct 13): Democratic Party favorable 43%, Republican Party 35%; Democrats preferred on the economy 51-37.
* Economy: CPI 3.7% in September, gasoline +34.2% on the year (BLS); unemployment 4.2%, payrolls +29,000; UMich sentiment 46.3 (October prelim).
* Trump net approval fell by about 25 to 30 points in nearly every state since January 2025 (Civiqs via Newsweek), so the state differences are mostly already in the 2024 lean.
* Governor approval: only IA (Reynolds -6), AK (Dunleavy -11), IN (Braun +4) were found (Morning Consult, Feb 2026). Too thin and stale to use. Congressional and court approval were not modeled.
* Party control and incumbency are NOT in the numbers: no validated size could be backtested, and polls already contain them.

## Historical analogs (data/midterm_analogs.csv)
| Midterm | President (approval) | Out-party House vote | President's party House / Senate seats |
|---|---|---|---|
| 1982 | Reagan (42%) | about D+11 | -26 / ~0 |
| 1994 | Clinton (46%) | about R+7 | -53 / -8 |
| 2006 | Bush (38%) | about D+8 | -30 / -6 |
| 2010 | Obama (45%) | about R+7 | -63 / -6 |
| 2018 | Trump (44%) | D+8.6 | -40 / +2 |
| 2022 | Biden (40%) | R+2.8 | -9 / +1 |
Approval and seat counts: Gallup and Dave Manuel. House-vote margins are from memory and unverified.
Read: presidents under 50% lose ~37 House seats on average. Senate results follow the map (2006 flipped Montana, a Bush +20 state; 2018 flipped none of the Trump-won states and lost three), which is why the Trump +10 states stay long shots with correlated outcomes.

## The other side
* Thune and others argue polls under-reflect Republican support (Axios, Oct 10). Silver notes polls underestimated Trump in 2016, 2020 and 2024, but 2018 and 2022 congressional polls showed little bias. Our poll-error history gives a midterm bias of about -0.3 and an error SD of about 4.4.
* The fundamentals prior leans more Republican than the polls in most red-lean states, so it acts as a partial hedge against that risk.

## Output (data/fundamentals.csv)
| Race | 2024 lean | National shift | Approval adj | Fundamentals |
|---|---|---|---|---|
| OH-senate | -11.3 | +5.3 | +0.4 | **-5.6** |
| OH-governor | -11.3 | +5.3 | +0.4 | **-5.6** |
| MI-senate | -1.4 | +5.3 | +0.1 | **+4.0** |
| MN-senate | +4.3 | +5.3 | +0.1 | **+9.8** |
| IA-senate | -13.4 | +5.3 | +0.7 | **-7.5** |
| KS-senate | -16.4 | +5.3 | -1.4 | **-12.5** |
| KS-governor | -16.4 | +5.3 | -1.4 | **-12.5** |
| NE-governor | -20.8 | +5.3 | -0.4 | **-15.9** |
| ME-senate | +6.6 | +5.3 | -0.2 | **+11.7** |
| AK-senate | -13.7 | +5.3 | -0.3 | **-8.7** |
| TX-senate | -13.9 | +5.3 | +0.6 | **-7.9** |
| TX-governor | -13.9 | +5.3 | +0.6 | **-7.9** |
| SC-senate | -18.1 | +5.3 | -0.1 | **-13.0** |
| MS-senate | -23.1 | +5.3 | +0.6 | **-17.3** |
| FL-governor | -13.2 | +5.3 | +0.2 | **-7.8** |
| GA-governor | -2.2 | +5.3 | -0.0 | **+3.1** |
| NV-governor | -3.2 | +5.3 | -0.1 | **+2.0** |
| WI-governor | -0.9 | +5.3 | -0.5 | **+4.0** |
| GA-senate | -2.2 | +5.3 | -0.0 | **+3.1** |
| ME-governor | +6.6 | +5.3 | -0.2 | **+11.7** |
| NH-senate | +2.8 | +5.3 | +0.4 | **+8.5** |
| FL-senate | -13.2 | +5.3 | +0.2 | **-7.8** |
| SC-governor | -18.1 | +5.3 | -0.1 | **-13.0** |
| IA-governor | -13.4 | +5.3 | +0.7 | **-7.5** |
| AK-governor | -13.7 | +5.3 | -0.3 | **-8.7** |
| MI-governor | -1.4 | +5.3 | +0.1 | **+4.0** |
| MN-governor | +4.3 | +5.3 | +0.1 | **+9.8** |
| NH-governor | +2.8 | +5.3 | +0.4 | **+8.5** |

NE-senate is excluded (independent Osborn on the ballot makes the presidential lean invalid).
Update `generic_ballot_margin_dem` and `generic_ballot_asof` in config/fundamentals.json before election week (the run warns after 14 days). Rerun any time with `python fundamentals.py`; `python check_setup.py` is the preflight. To switch it off, set `sd_fund` to 1000000 in config/fundamentals.json.
