import json
from engine import Params, run_model
from multi_stock import params_for
import verify_all_ladder as V

pj=json.load(open('params_all.json'))
q=V.srcdo['Query']; i=V.STOCKS.index('RKLB')
dts,O,H,L,C=[],[],[],[],[]
for row in q.iter_rows(min_row=2, values_only=True):
    d=V.to_date(row[0]); o=row[1+4*i]
    if d is None or not isinstance(o,(int,float)) or o<=0: continue
    dts.append(d);O.append(o);H.append(row[2+4*i]);L.append(row[3+4*i]);C.append(row[4+4*i])
p=params_for('RKLB',pj)
f=run_model(dts,O,H,L,C,p,collect=True).frames
Lvl,Slp,W,G=f['Lvl'],f['Slp'],f['W'],f['G']
N=len(C); k,pc,prem,comm,rate,stop=p.k,p.peak_cap,p.premium,p.comm,p.interest,p.stop_days
m=[1.0,1.3,1.7]; w=[0.80,0.15,0.05]

# EXACT copy of ladder_engine._tranche fill logic, with per-day fill recording
fund=p.capital*p.bayes_pct; shares=0.0; cost_px=0.0; filled=set(); incyc=False; bd=None
budgets=None; ENG=[]
for idx in range(N):
    if idx>0: fund += fund*rate*(dts[idx]-dts[idx-1]).days/365.0
    if idx>=1:
        fair=Lvl[idx-1]+Slp[idx-1]; sig=W[idx-1]; peak=G[idx-1]*(1-pc)
        rp=[min(fair-mm*k*sig,O[idx],peak) for mm in m]
        if not incyc:
            budgets=[fund*ww for ww in w]; filled=set(); anchor=0.0
        fills=[0,0,0]
        for j,price in enumerate(rp):
            if j in filled or price is None or price<=0: continue
            bj=budgets[j]
            if L[idx]<=price and fund>=bj-1e-9 and bj>0:
                sh=bj/(price+comm); shares+=sh; cost_px+=sh*price; fund-=bj
                anchor=max(anchor,price); filled.add(j); fills[j]=1
                if not incyc: incyc=True; bd=dts[idx]
        if incyc and shares>0:
            ref=anchor; tgt=ref+C[idx-1]*prem
            held=(dts[idx]-bd).days>=stop
            sell=tgt if H[idx]>=tgt else (O[idx] if held else None)
            if sell is not None:
                fund+=shares*(sell-comm); shares=0.0; cost_px=0.0; filled=set(); incyc=False; bd=None
        ENG.append((idx,fills,round(fund,2),round(shares,2),list(budgets) if budgets else None))
    else:
        ENG.append((idx,[0,0,0],round(fund,2),0,None))

# mirror (guarded) fills for same region
from mirror_ladder import mirror
mir=mirror(dts,O,H,L,C,p)
# find first day where engine cumulative buys diverge from mirror by inspecting fund
for idx in range(385,398):
    print('i=%d date=%s ENGfills=%s ENGfund=%.2f ENGsh=%.2f | MIRfund=%.2f MIRsh=%.2f'%(
        idx, dts[idx], ENG[idx][1], ENG[idx][2], ENG[idx][3], mir['FUND'][idx], mir['SH'][idx]))
print('ENG total buys=', sum(sum(e[1]) for e in ENG), ' MIR buys=', mir['buys'])
