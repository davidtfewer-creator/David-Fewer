"""
Walk-forward validation of the NO-SAME-DAY re-optimisation.

Question: the wide-premium rebuild looks great in-sample, but does it generalise? Or is it the
usual in-sample mirage? For each name, 3 expanding folds. Each fold RE-OPTIMISES params+premia
on the train window with same_day_exit=False, freezes, and scores the unseen test slice --- also
same_day_exit=False. Compare, on the SAME unseen slice (both no-same-day):
    reopt-nosd  (wide-premium params fit on train)   vs   orig-nosd (current workbook params)
If reopt beats orig out of sample, the honest wide-premium model is worth deploying.
"""
import statistics
from scipy.optimize import differential_evolution
from stop_sweep import load_book
from engine import Params, run_model

data, params, cached = load_book()
STOCKS = list(data)
BOUNDS = [(0.2,1.6),(0.1,1.0),(0.001,0.1),(0.3,3.0),(0.005,0.20),(0.002,0.07),
          (0.1,2.5),(0.008,0.20),(0.005,0.12),(30,150)]
PERT = [0.97, 1.03]
CUTS = (0.5, 0.667, 0.833, 1.0)


def bvec(p): return [p.lam,p.phi_L,p.psi,p.k,p.premium,p.peak_cap,p.ou_buf_k,p.ou_prem,p.ou_cap,p.ou_W]

def mp(vec, t):
    return Params(lam=vec[0],phi_L=vec[1],psi=vec[2],k=vec[3],premium=vec[4],peak_cap=vec[5],
                  ou_buf_k=vec[6],ou_prem=vec[7],ou_cap=vec[8],ou_W=int(round(vec[9])),
                  comm=t.comm,capital=t.capital,interest=t.interest,stop_days=t.stop_days,
                  bayes_pct=t.bayes_pct,years=t.years)

def frames(s, vec, t):
    dts,O,H,L,C = data[s]
    return run_model(dts,O,H,L,C, mp(vec,t), collect=True, same_day_exit=False).frames

def seg(fr, lo, hi):
    eq = fr['equity']
    ret = eq[hi]/eq[lo]-1 if eq[lo] > 0 else -1
    buys = sum(fr['t1']['Z'][lo:hi+1]) + sum(fr['t2']['Z'][lo:hi+1])
    return ret, buys

def robust(s, vec, t, lo, hi, floor):
    def one(v):
        r,b = seg(frames(s, v, t), lo, hi)
        return -5.0 + b*1e-3 if b < floor else r
    base = one(vec); sm=[]
    for i in range(9):
        for f in PERT:
            v=list(vec); v[i]=min(max(v[i]*f,BOUNDS[i][0]),BOUNDS[i][1]); sm.append(one(v))
    return 0.5*base + 0.5*sum(sm)/len(sm)

def optimise(s, t, lo, hi, floor):
    neg = lambda v: -robust(s, v, t, lo, hi, floor)
    x0 = [min(max(v,BOUNDS[i][0]),BOUNDS[i][1]) for i,v in enumerate(bvec(t))]
    res = differential_evolution(neg, BOUNDS, x0=x0, init='sobol', seed=42, maxiter=8, popsize=8,
                                 mutation=(0.5,1.0), recombination=0.7, tol=1e-3, polish=False,
                                 disp=False, updating='immediate', workers=1)
    return list(res.x)


if __name__ == '__main__':
    print('Walk-forward of the no-same-day model: reopt-on-train vs orig, both scored OOS (no same-day)\n', flush=True)
    print(f'{"stock":6s}{"fold":>5s}{"reopt OOS":>11s}{"orig OOS":>10s}{"winner":>9s}{"new prem":>10s}', flush=True)
    print('-'*51, flush=True)
    summary = {}
    for s in STOCKS:
        dts,O,H,L,C = data[s]; N=len(C); t=params[s]
        cuts=[int(N*f) for f in CUTS]
        wins=0; reopts=[]; origs=[]
        for k in range(3):
            trlo,trhi = 0, cuts[k]
            telo,tehi = cuts[k], cuts[k+1]-1
            of = frames(s, bvec(t), t)
            _, otr_buys = seg(of, trlo, trhi-1)
            floor = max(5, int(0.3*otr_buys))
            theta = optimise(s, t, trlo, trhi-1, floor)
            rr,_ = seg(frames(s, theta, t), telo, tehi)
            oo,_ = seg(of, telo, tehi)
            wins += (rr > oo); reopts.append(rr); origs.append(oo)
            print(f'{s:6s}{k+1:>5d}{rr*100:>10.1f}%{oo*100:>9.1f}%{("reopt" if rr>oo else "orig"):>9s}'
                  f'{mp(theta,t).premium:>10.3f}', flush=True)
        summary[s]=(wins, statistics.mean(reopts)*100, statistics.mean(origs)*100)
    print('\n=== SUMMARY (mean per-fold OOS return, no-same-day basis) ===', flush=True)
    print(f'{"stock":6s}{"reopt wins":>12s}{"mean reopt":>12s}{"mean orig":>11s}', flush=True)
    tw=0
    for s in STOCKS:
        w,mr,mo = summary[s]; tw+=w
        print(f'{s:6s}{f"{w}/3":>12s}{mr:>11.1f}%{mo:>10.1f}%', flush=True)
    print(f'\nReopt beats orig OOS in {tw}/30 folds.', flush=True)
    print('SUMMARY DONE', flush=True)
