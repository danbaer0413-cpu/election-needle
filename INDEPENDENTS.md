# Independents / other voters: working theory (written 2026-10-26)

What the model does with it: `other_lean` (default +4) = how many points MORE Democratic unaffiliated/other registrants are than the early pool overall,
`sd_other` (default 5) = uncertainty on that. It only enters the early party-registration signal, so it matters where party registration of returned ballots
is loaded (FL, IA now; NC, NV and others if the Monday early-vote pass includes party splits). Polls already contain independents' opinions.
Alaska's party split is kept out (more than half "other").

Theory: independents are leaning Democratic and will not wash out, but the lean is not as extreme as a raw independents crosstab suggests.
1. Direction is clear. Trump's approval among independents was about 24% (CNN/SSRS, Jul 23-27) and 19% (Economist/YouGov, Jul 25-27; his lowest with them
   in the second term). Emerson (Jan 2026, national) had independents D 50 - R 28 with 22% undecided. In 2025 independents swung toward Democrats in Virginia
   and New Jersey (CBS exit polls; no numbers in the text I could read).
2. Size: exit polls had independents D 54-R 42 in 2018 (overall House vote about D+8.6) and D 49-R 47 in 2022 (overall about R+2.8): roughly 3 to 5 points
   MORE Democratic than the overall vote in both years. With a D+9 to D+9.5 environment now (Silver Bulletin D+9.5; Reuters/Ipsos likely voters 53-44 on Oct 26)
   and worse approval with independents than in 2018, I use +4, not a wash and not the raw +20s: many "independents" are leaners who vote like partisans,
   and undecided independents break late, usually toward the out-party but not all the way.
3. Turnout helps Democrats: likely voters ran 1 to 2.5 points bluer than registered voters in seven surveys this year (Verasight/G. Elliott Morris, Jul 22),
   about a third of the Democratic swing being turnout.
Uncertainty: no 2026 independent-only vote-intent poll newer than Emerson's January survey turned up in my search; the exit-poll gap is from two cycles; so
sd 5 points. Try 0 (wash) and +8 in the app sidebar to see the range.
Sources: CNN 2022 exit-poll analysis (cnn.com/2022/11/09 ...independent-vote); Newsweek summary of CNN/SSRS and Economist/YouGov (Jul 2026); Emerson via Daily Caller (Jan 22, 2026);
Gallup/Barclays on party leanings (Q2 2026: 49% D-leaning vs 39% R-leaning of adults, similar to 2006); G. Elliott Morris/Verasight (Jul 22, 2026); Politicalwire on Reuters/Ipsos (Oct 26, 2026).

## State-by-state leans (config/other_lean.csv; update run applies them)
Rule: lean = 4 + 0.1 x (how much worse Trump's net approval in the state is than -20, Civiqs via Newsweek, data/fundamentals_inputs.csv), capped 0 to 8.
So independents lean a bit more Democratic in NH, MN, ME, MI (Trump deeply negative) and less in KS, SC, MS, FL (Trump near even or only modestly negative).
Judgment adjustments (uncertainty 6 instead of 5): Nebraska Senate +3 (Osborn is an independent), Alaska Senate +1.5 (Peltola's crossover appeal), Maine Senate -2 (Collins runs ahead with independents).
This is a rule of thumb, not a measured state number: nobody publishes state-level independent vote intent this late. Edit config/other_lean.csv to override any race;
a race that sets other_lean in config/races.json params keeps that value instead.
