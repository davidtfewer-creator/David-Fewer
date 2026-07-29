"""
All-ten clean tiebreaker. Per fold, per name, three OOS numbers on the same unseen slice:
  frozen-close  : the deployed incumbent (full-history params, no per-fold tuning)
  reopt-close   : close signal re-optimised on train only
  reopt-open    : open signal re-optimised on train only (OU anchor=open, Bayes->open, free gain)
Objective = maximise train annual return with a trade-count floor. No robustness term (both
arms identical; the walk-forward is the overfitting judge). Decision metric = reopt-open vs
frozen-close incumbent.
"""
import json
from scipy.optimize import differential_evolution
from engine import Params, run_model
from multi_stock import load_stock, STOCKS

PJSON = json.load(open('params_all.json'))
PKEYS = ['lam','phi_L','psi','k','premium','peak_cap','ou_buf_k','ou_prem','ou_cap','ou_W']


def base_vec(s):
    p = PJSON[s]; return [p[k] for k in PKEYS]


def bounds_for(s, with_gain):
    b = []
    for key, v in zip(PKEYS, base_vec(s)):
        b.append((max(15, round(0.5*v)), round(1.7*v)) if key == 'ou_W' else (0.4*v, 2.5*v))
    if with_gain: b.append((0.0, 1.0))
    return b


def mk_params(s, vec):
    p = PJSON[s]
    return Params(lam=vec[0],phi_L=vec[1],psi=vec[2],k=vec[3],premium=vec[4],peak_cap=vec[5],
                  ou_buf_k=vec[6],ou_prem=vec[7],ou_cap=vec[8],ou_W=int(round(vec[9])),
                  comm=p['comm'],capital=p['capital'],interest=p['interest'],
                  stop_days=int(p['stop']),bayes_pct=p['bayes_pct'])


def seg(eq, lo, hi):
    return -1.0 if eq[lo] <= 0 else eq[hi]/eq[lo] - 1.0


def evaluate(s, data, vec, lo, hi, is_open):
    dates,O,H,L,C,_ = data
    if is_open:
        r = run_model(dates,O,H,L,C, mk_params(s,vec), ou_anchor=list(O),
                      bayes_signal=list(O), bayes_gain=vec[10], collect=True)
    else:
        r = run_model(dates,O,H,L,C, mk_params(s,vec), collect=True)
    z=r.frames['t1']['Z']; g=r.frames['t2']['Z']
    return seg(r.frames['equity'],lo,hi), sum(z[lo:hi+1])+sum(g[lo:hi+1])


def optimize(s, data, lo, hi, floor, is_open):
    bnd = bounds_for(s, is_open); x0 = base_vec(s) + ([0.5] if is_open else [])
    def neg(v):
        ret, buys = evaluate(s, data, v, lo, hi, is_open)
        return -((-5.0 + buys*0.001) if buys < floor else ret)
    return differential_evolution(neg, bnd, x0=x0, init='sobol', seed=42, maxiter=15,
        popsize=8, mutation=(0.5,1.0), recombination=0.7, tol=1e-4, polish=False,
        updating='immediate', workers=1).x


if __name__ == '__main__':
    print('ALL-TEN CLEAN TIEBREAKER  (frozen-close incumbent | reopt-close | reopt-open)\n')
    agg = {'fz':0.0,'rc':0.0,'ro':0.0}
    open_beats_incumbent_folds = 0; total_folds = 0
    open_wins_names = 0
    for s in STOCKS:
        data = load_stock(s); dates = data[0]; N = len(dates)
        cuts = [int(N*f) for f in (0.5,0.667,0.833,1.0)]
        folds = [(0,cuts[i]-1,cuts[i],cuts[i+1]-1) for i in range(3)]
        frozen = run_model(dates,data[1],data[2],data[3],data[4], mk_params(s, base_vec(s)), collect=True)
        eqf = frozen.frames['equity']
        name_fz=name_rc=name_ro=0.0; name_open_beats=0
        rows=[]
        for (trlo,trhi,telo,tehi) in folds:
            _, bb = evaluate(s, data, base_vec(s), trlo, trhi, False)
            floor = max(8, int(0.6*bb))
            tc = optimize(s, data, trlo, trhi, floor, False)
            to = optimize(s, data, trlo, trhi, floor, True)
            fz = seg(eqf, telo, tehi)
            rc,_ = evaluate(s, data, tc, telo, tehi, False)
            ro,_ = evaluate(s, data, to, telo, tehi, True)
            rows.append((telo,tehi,fz,rc,ro))
            name_fz+=fz; name_rc+=rc; name_ro+=ro
            total_folds+=1
            if ro>fz: open_beats_incumbent_folds+=1; name_open_beats+=1
        print(f'=== {s} ===')
        for (telo,tehi,fz,rc,ro) in rows:
            print(f'   [{telo:>3d}:{tehi:<3d}]  frozen={fz*100:6.1f}%  reopt-close={rc*100:6.1f}%  '
                  f'reopt-open={ro*100:6.1f}%   {"OPEN" if ro>fz else "incumbent"}')
        print(f'   avg: frozen={name_fz/3*100:.1f}%  reopt-close={name_rc/3*100:.1f}%  '
              f'reopt-open={name_ro/3*100:.1f}%   open>incumbent {name_open_beats}/3\n')
        agg['fz']+=name_fz/3; agg['rc']+=name_rc/3; agg['ro']+=name_ro/3
        if name_ro>name_fz: open_wins_names+=1
    n=len(STOCKS)
    print('='*70)
    print(f'OVERALL avg OOS ({n} names):  frozen-close={agg["fz"]/n*100:.1f}%   '
          f'reopt-close={agg["rc"]/n*100:.1f}%   reopt-open={agg["ro"]/n*100:.1f}%')
    print(f'reopt-open beats FROZEN incumbent in {open_beats_incumbent_folds}/{total_folds} folds '
          f'and {open_wins_names}/{n} names (on avg).')
