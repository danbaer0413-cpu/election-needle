"""Backtest: tier average (needle input) vs own quality-weighted average, as of 9 days before 2016-2024 elections.
usage: python backtest_poll_average.py <dir with Rawpolls_040626.xlsx and Pollster_Stats_Full_2026.xlsx>
Caveat: the pollster ratings include these same elections, so the own-average (B) gets a look-ahead advantage and still does not win."""
import sys
import pandas as pd, numpy as np, math
A=sys.argv[1].rstrip("/")+"/"
r=pd.read_excel(A+"Rawpolls_040626.xlsx"); s=pd.read_excel(A+"Pollster_Stats_Full_2026.xlsx",sheet_name=0).set_index("Pollster Rating ID")
pmcol=[c for c in s.columns if str(c).startswith("Predictive")][0]
r["grade"]=r.pollster_rating_id.map(s["SB Grade"]); r["pm"]=r.pollster_rating_id.map(s[pmcol]); r["mrb"]=r.pollster_rating_id.map(s["Mean-Reverted Bias"])
r["banned"]=r.pollster_rating_id.map(s["Banned by Silver Bulletin"]).astype(str).str.lower().eq("yes")
RACE={"Pres-G":"President","Sen-G":"U.S. Senate","Sen-GS":"U.S. Senate (special)","Gov-G":"Governor"}
r=r[r.type_detail.isin(RACE)&r.year.isin([2016,2018,2020,2022,2024])&r.partisan.isna()&~r.banned&r.grade.notna()&(r.grade!="F")]
ok=r.cand1_party.isin(["DEM","REP"])&r.cand2_party.isin(["DEM","REP"])&(r.cand1_party!=r.cand2_party); r=r[ok].copy()
sw=r.cand1_party.eq("REP"); d=np.where(sw,r.cand2_pct,r.cand1_pct); rp=np.where(sw,r.cand1_pct,r.cand2_pct)
da=np.where(sw,r.cand2_actual,r.cand1_actual); ra=np.where(sw,r.cand1_actual,r.cand2_actual)
r["pmg"]=(d-rp)/(d+rp)*100; r["am"]=(da-ra)/(da+ra)*100
r["mrb"]=r.mrb.astype(float)*np.where(sw,-1,1)*0  # sign unknown -> not used
r["bias_d"]=r.pm  # placeholder
r=r.dropna(subset=["pmg","am","polldate","electiondate"]); r["days"]=(r.electiondate-r.polldate).dt.days
T1={"A+","A","A-","A/B","B+"}; T2={"B","B-"}; AS_OF=9
rows=[]
for (loc,yr,td),g in r.groupby(["location","year","type_detail"]):
    if not (isinstance(loc,str) and len(loc)==2): continue
    g=g[g.days>=AS_OF].copy(); g["age"]=g.days-AS_OF
    if g.empty: continue
    def tier(win,tiers):
        q=g[g.age<=win]; q=q.sort_values("polldate").groupby("pollster").tail(1); q=q[q.grade.isin(tiers)]
        if q.empty: return None
        w=np.sqrt(q.samplesize.fillna(600))*0.5**(np.maximum(0,q.age-14)/14); return np.average(q.pmg,weights=w),len(q)
    est=None;best=None
    for win,tiers in [(21,T1),(35,T1),(35,T1|T2),(60,T1|T2),(90,T1|T2)]:
        t=tier(win,tiers)
        if t and t[1]>=4: est=t;break
        if t and (best is None or t[1]>best[1]): best=t
    A_=est or best
    q=g[g.age<=60].copy()
    if q.empty or A_ is None: continue
    gw=np.where(q.pm.notna(),(4.6/np.maximum(2.5,4.6+q.pm.fillna(0)))**2,0.3)
    n=q.samplesize.fillna(600).clip(lower=1)
    q["w"]=gw*np.clip(np.sqrt(n/600),0.7,1.6)*np.exp(-q.age/10)
    rec=q[q.age<=21].groupby("pollster").size(); q["w"]/=q.pollster.map(lambda k: math.sqrt(max(1,rec.get(k,1))))
    B_=float(np.average(q.pmg,weights=q.w))
    rows.append(dict(state=loc,year=int(yr),race=RACE[td],A=A_[0],nA=A_[1],B=B_,nB=len(q),act=float(g.am.iloc[0])))
h=pd.DataFrame(rows); h["D"]=(h.A+h.B)/2
def rm(x,col): return np.sqrt(((x.act-x[col])**2).mean())
for lab,x in [("midterm 2018/22",h[h.year.isin([2018,2022])]),("midterm competitive |A|<=15",h[h.year.isin([2018,2022])&(h.A.abs()<=15)]),("all years",h),("A<4 polls",h[h.nA<4]),("A>=4 polls",h[h.nA>=4])]:
    print(f"{lab:30} n={len(x):3}  tier A {rm(x,'A'):.2f} | own B {rm(x,'B'):.2f} | blend {rm(x,'D'):.2f} | mean err A {np.mean(x.act-x.A):+.2f} B {np.mean(x.act-x.B):+.2f} | |A-B| {np.mean(abs(x.A-x.B)):.2f}")
x=h[h.year.isin([2018,2022])]
print("corr of (A-B) with (act-A):", round(np.corrcoef(x.B-x.A,x.act-x.A)[0,1],2), " slope", round(np.polyfit(x.B-x.A,x.act-x.A,1)[0],2))
