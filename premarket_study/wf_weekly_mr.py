"""Walk-forward the weekly MR parameters on minute-verified fills."""
import statistics, math
from scipy.optimize import differential_evolution
from weekly_mr import WS, DTS, C, run_tranche, P, verify_same_day
import weekly_mr as W

# re-run a tranche but scoring only a window of weeks
def seg_run(p, w0, w1, mode='verified', capital=1.0):
    import numpy as np
    fund=capital; shares=0.0; holding=False; buy=tgt=None; trades=0
    ath=max(W.H[i] for i in WS[w0]['idxs'])
    for wi in range(w0+1, w1+1):
        prev,cwk=WS[wi-1],WS[wi]; ath=max(ath,prev['h'])
        if not holding:
            days=(DTS[cwk['idxs'][-1]]-DTS[prev['idxs'][-1]]).days
            fund+=fund*W.INTEREST*days/365.0
        rng=prev['h']-prev['l']
        if rng<=0: continue
        Lp=min(statistics.mean([p['m']*(prev['h']+prev['l'])/2, prev['c']*p['w']])
               + math.log10(rng)*p['g'], cwk['o'])
        if not holding:
            buy=min(Lp, ath*(1-p['cap'])); tgt=buy+prev['c']*p['prem']
        idxs=cwk['idxs']
        if not holding:
            bd=None
            for k,i in enumerate(idxs):
                if W.L[i]<=buy: bd=k; break
            if bd is None: continue
            shares=fund/(buy+W.COMM); fund=0.0; holding=True
            for k in range(bd,len(idxs)):
                i=idxs[k]
                if W.H[i]>=tgt:
                    if k==bd and mode=='verified':
                        v=verify_same_day(i,buy,tgt)
                        if v is False: continue
                    fund=shares*(tgt-W.COMM); shares=0.0; holding=False; trades+=1; break
        else:
            for i in idxs:
                if W.H[i]>=tgt:
                    fund=shares*(tgt-W.COMM); shares=0.0; holding=False; trades+=1; break
    final=fund+(shares*C[idxs[-1]] if holding else 0.0)
    return final-1.0, trades

KEYS=['w','cap','prem','g','m']
B=[(0.98,1.03),(0.03,0.20),(0.010,0.080),(0.5,4.0),(0.9,1.4)]
def vec2p(v): return dict(zip(KEYS,v))

def score(v,w0,w1,floor):
    r,t=seg_run(vec2p(v),w0,w1)
    return -5.0+t*1e-3 if t<floor else r
def robust(v,w0,w1,floor):
    base=score(v,w0,w1,floor); sm=[]
    for i in range(len(KEYS)):
        for f in (0.97,1.03):
            u=list(v); u[i]=min(max(u[i]*f,B[i][0]),B[i][1]); sm.append(score(u,w0,w1,floor))
    return 0.5*base+0.5*sum(sm)/len(sm)

N=len(WS)
cuts=[int(N*f) for f in (0.5,0.667,0.833,1.0)]
print(f'{"fold":5s}{"train wks":>12s}{"test wks":>11s}{"reopt OOS":>11s}{"workbook OOS":>14s}{"winner":>9s}',flush=True)
print('-'*63,flush=True)
wins=0; diffs=[]; picks=[]
x0=[P[k] for k in KEYS]
for k in range(3):
    trhi=cuts[k]; telo,tehi=cuts[k],cuts[k+1]-1
    _,tt=seg_run(P,1,trhi-1)
    floor=max(4,int(0.4*tt))
    res=differential_evolution(lambda v:-robust(v,1,trhi-1,floor),B,x0=x0,init='sobol',seed=42,
        maxiter=8,popsize=6,mutation=(0.5,1.0),recombination=0.7,tol=1e-3,polish=False,
        disp=False,updating='immediate',workers=1)
    th=vec2p(list(res.x)); picks.append(th)
    a,_=seg_run(th,telo,tehi); b,_=seg_run(P,telo,tehi)
    wins+=(a>b); diffs.append((a-b)*100)
    print(f'{k+1:<5d}{f"1-{trhi-1}":>12s}{f"{telo}-{tehi}":>11s}{a*100:>10.1f}%{b*100:>13.1f}%'
          f'{("reopt" if a>b else "workbook"):>9s}',flush=True)
print('-'*63,flush=True)
print(f'reopt beats the workbook params OOS in {wins}/3 folds; mean {statistics.mean(diffs):+.1f}pp',flush=True)
print('\nfitted params per fold:',flush=True)
for i,th in enumerate(picks,1):
    print(f'  fold {i}: '+'  '.join(f'{k}={th[k]:.4f}' for k in KEYS),flush=True)
print('  workbook: '+'  '.join(f'{k}={P[k]:.4f}' for k in KEYS),flush=True)
print('DONE',flush=True)
