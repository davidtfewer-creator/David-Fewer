"""
Model-fit for the Hybrid10_Feed_new candidates. No pre-fitted params, so robustly optimise
each (full-sample, perturbation-averaged objective + min-trade floor), report in-sample
metrics, then validate the fitted params out-of-sample on 3 unseen tail slices (frozen — no
per-fold refit). Cap = true open (workbook convention). Capital $6M/name (metrics are
scale-invariant; %s reported).
"""
import math, statistics, datetime
from engine import Params, run_model
from optimise_candidates import mp as make_params, optimise, segret as seg_return
from newfeed import load, NEW, NEW_TK


def span_years(dts):
    return (dts[-1] - dts[0]).days / 365.25


def tranche_rets(fr, tkey, C):
    t = fr[tkey]
    eq = [t['AA'][i]*C[i] if t['AE'][i]==1 else t['Y'][i] for i in range(len(C))]
    return [eq[i]/eq[i-1]-1 for i in range(1,len(eq)) if eq[i-1]>0]

def corr(a,b):
    n=min(len(a),len(b)); a,b=a[:n],b[:n]
    if n<3: return 0.0
    ma,mb=statistics.mean(a),statistics.mean(b)
    cov=sum((a[i]-ma)*(b[i]-mb) for i in range(n))
    va=sum((x-ma)**2 for x in a); vb=sum((x-mb)**2 for x in b)
    return cov/math.sqrt(va*vb) if va>0 and vb>0 else 0.0


if __name__ == '__main__':
    new = load(NEW, NEW_TK)
    print(f'{"tick":5s}{"ann%":>7s}{"Sharpe":>8s}{"maxDD%":>8s}{"trades":>8s}{"/yr":>5s}'
          f'{"stops":>7s}{"B-OU":>6s} | {"OOS slice1/2/3 (frozen)":>26s}', flush=True)
    for t in NEW_TK:
        dts,O,H,L,C = new[t]
        yrs = span_years(dts); N=len(C)
        tmpl = Params(capital=6_000_000, comm=0.005, interest=0.0314, stop_days=50,
                      bayes_pct=0.5, years=yrs)
        data = dict(dts=dts,O=O,H=H,L=L,C=C)
        # min-trade floor: at least ~0.5 buys/week over the sample
        floor = max(20, int(0.4*N/5))
        theta = optimise(data, tmpl, 0, N-1, floor, maxiter=10, popsize=8)
        p = make_params(theta, tmpl)
        r = run_model(dts,O,H,L,C,p, collect=True)
        hedge = corr(tranche_rets(r.frames,'t1',C), tranche_rets(r.frames,'t2',C))
        # OOS: frozen fitted params on 3 tail slices
        cuts=[int(N*f) for f in (0.5,0.667,0.833,1.0)]
        oos=[]
        for i in range(3):
            lo,hi=cuts[i],cuts[i+1]-1
            oos.append(seg_return(r.frames['equity'],lo,hi))
        oos_s = '/'.join(f'{x*100:+.0f}%' for x in oos)
        print(f'{t:5s}{r.annual_return*100:>7.0f}{r.sharpe:>8.2f}{r.max_drawdown*100:>8.0f}'
              f'{r.total_buys:>8d}{r.total_buys/yrs:>5.0f}{r.stop_loss_exits:>7d}{hedge:>6.2f} | '
              f'{oos_s:>26s}', flush=True)
