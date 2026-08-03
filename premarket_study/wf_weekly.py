"""Walk-forward the WEEKLY model on verified fills: 3 expanding folds, refit per fold on train
only, scored on the unseen slice against the DAILY model (verified) over the same slice."""
import statistics, sys
from scipy.optimize import differential_evolution
from stop_sweep import load_book
from engine import Params, run_model
from weekly_engine import run_weekly, week_groups
from five_min import make_checker as fm
from minute_engine import make_checker as nv

data, params, cached = load_book()
ALL = ['NVDA','SOFI','SPOT','AVGO','TSLA','PLTR']
T = [a for a in sys.argv[1:] if a in ALL] or ALL
CHK = {s: (nv(*(data[s][0], data[s][1]))[0] if s=='NVDA' else fm(s, data[s][0], data[s][1])[0]) for s in T}
NM=['lam','phi_L','psi','k','premium','peak_cap','ou_buf_k','ou_prem','ou_cap','ou_W']
B=[(0.2,1.6),(0.1,1.0),(0.001,0.1),(0.3,3.0),(0.005,0.20),(0.002,0.07),(0.1,2.5),(0.005,0.20),(0.005,0.12),(30,150)]
POL=[3,4,6,7]; PERT=[0.97,1.03]; CUTS=(0.5,0.667,0.833,1.0)

def bv(p): return [p.lam,p.phi_L,p.psi,p.k,p.premium,p.peak_cap,p.ou_buf_k,p.ou_prem,p.ou_cap,p.ou_W]
def mp(v,t): return Params(lam=v[0],phi_L=v[1],psi=v[2],k=v[3],premium=v[4],peak_cap=v[5],
    ou_buf_k=v[6],ou_prem=v[7],ou_cap=v[8],ou_W=int(round(v[9])),comm=t.comm,capital=t.capital,
    interest=t.interest,stop_days=t.stop_days,bayes_pct=t.bayes_pct,years=t.years)

def wk_eq(s,v):
    d,O,H,L,C=data[s]
    return run_weekly(d,O,H,L,C,mp(v,params[s]),checker=CHK[s])['equity']
def dl_eq(s):
    d,O,H,L,C=data[s]
    return run_model(d,O,H,L,C,params[s],collect=True,same_day_exit=CHK[s]).frames['equity']
def sg(eq,lo,hi): return eq[hi]/eq[lo]-1 if eq[lo]>0 else -1.0

def robust(s,v,lo,hi,floor):
    def one(x):
        d,O,H,L,C=data[s]
        r=run_weekly(d,O,H,L,C,mp(x,params[s]),checker=CHK[s])
        n=sum(1 for g in week_groups(d) if g and lo<=g[0]<=hi)
        return sg(r['equity'],lo,hi) if r['trades']>=floor else -5.0+r['trades']*1e-3
    base=one(v); sm=[]
    for i in POL:
        for f in PERT:
            w=list(v); w[i]=min(max(w[i]*f,B[i][0]),B[i][1]); sm.append(one(w))
    return 0.5*base+0.5*sum(sm)/len(sm)

print(f'{"stock":6s}{"fold":>5s}{"weekly OOS":>12s}{"daily OOS":>11s}{"winner":>9s}{"prem*":>9s}')
print('-'*52)
wins=tot=0; diffs=[]
for s in T:
    N=len(data[s][4]); cuts=[int(N*f) for f in CUTS]; de=dl_eq(s)
    for k in range(3):
        trhi=cuts[k]; telo,tehi=cuts[k],cuts[k+1]-1
        x0=[min(max(v,B[i][0]),B[i][1]) for i,v in enumerate(bv(params[s]))]
        res=differential_evolution(lambda v:-robust(s,v,0,trhi-1,10),B,x0=x0,init='sobol',seed=42,
            maxiter=6,popsize=6,mutation=(0.5,1.0),recombination=0.7,tol=1e-3,polish=False,
            disp=False,updating='immediate',workers=1)
        th=list(res.x)
        w=sg(wk_eq(s,th),telo,tehi); d=sg(de,telo,tehi)
        wins+=(w>d); tot+=1; diffs.append((w-d)*100)
        print(f'{s:6s}{k+1:>5d}{w*100:>11.1f}%{d*100:>10.1f}%{("weekly" if w>d else "daily"):>9s}{mp(th,params[s]).premium:>9.4f}',flush=True)
print('-'*52)
print(f'weekly beats daily OOS in {wins}/{tot} folds; mean {statistics.mean(diffs):+.1f}pp, median {statistics.median(diffs):+.1f}pp')
print('DONE')
