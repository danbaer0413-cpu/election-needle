# Historical polling error in the model

Built from data/poll_error_history.csv (final poll averages vs certified results, 2016-2024, Senate/governor/president;
errors are actual minus poll, so positive = polls understated Democrats). Refit any time with `python poll_error_fit.py`.

## What is applied (all passed a leave-one-year-out test on 2018 and 2022)
| Piece | Value | Why |
|---|---|---|
| State bias | table below, added to the poll margin | A state's miss persists. Measured as each race's error minus that year's average error for its race type, pooled over all five cycles, shrunk toward zero (prior weight 3 races). Out of sample it cut RMSE from 4.50 to 4.13 (2018) and 4.32 to 3.86 (2022). |
| Global bias | -0.15 | Mean midterm miss (2018 and 2022), halved because there are only two midterms. Presidential years (polls overstated Democrats by 2.5 to 6 points) are excluded. |
| Poll error SD | 4.73 with fewer than 4 polls, 4.0 with 4 or more | Out-of-sample residual SD by number of polls, inflated 10%, floor 4.0. Replaces the flat 5.0. |

Out-of-sample RMSE: 4.4 raw vs 3.99 adjusted.
Races on a hand-typed Silver average count as 4+ polls. NE-senate gets no state bias (independent on the ballot).

## State bias for our states (positive = polls usually understate Democrats)
| State | Bias |
|---|---|
| FL | -2.6 |
| AK | -2.5 |
| SC | -1.5 |
| IA | -1.4 |
| OH | -1.0 |
| KS | -0.7 |
| NE | -0.7 |
| MI | -0.4 |
| WI | -0.1 |
| ME | -0.1 |
| TX | +0.4 |
| GA | +1.0 |
| MN | +1.1 |
| NH | +1.4 |
| NV | +2.5 |
| MS | +2.8 |

## Tested and NOT used
* **Lopsided-race slope** (polls understate how lopsided a race ends up): shows in-sample (t=3.6 inside +/-20) but flips sign between 2018 and 2022 and made out-of-sample error worse.
* **Poll-tier biases** (thin / widened windows): same signs in both years, but adding them raised out-of-sample error.
* **Midterm-only state bias**: no out-of-sample gain; only the version pooled over all cycles helped.
* **Year-wide miss**: midterm years were close to zero (-0.1 and -0.4) but presidential years were -2.5 to -6, so the shared error is unpredictable. It is covered by the SD, not the mean.

## Caveats
Two midterms are a thin base; the SD for 4+ polls rests on 28 races. State bias is largest where history is thinnest, so it is shrunk. Mississippi (+2.7) and Nevada (+2.4) are the biggest pushes toward Democrats, Florida (-2.7) and Alaska (-2.7) the biggest toward Republicans.
