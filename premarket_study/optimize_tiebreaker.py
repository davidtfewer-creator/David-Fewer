"""
Clean tiebreaker: close-signal vs open-signal, BOTH re-optimised per training fold
(neither peeks at test), judged out-of-sample. Removes the incumbent's full-history
advantage. Objective = maximise train annual return with a trade-count floor (profit +
buys). Robustness term dropped for speed — both arms get identical treatment and the
walk-forward itself is the overfitting judge.
"""
import json
import numpy as np
from scipy.optimize import differential_evolution
from engine import Params, run_model
from multi_stock import load_stock

PJSON = json.load(open('params_all.json'))
NAMES = ['NVDA', 'AVGO', 'SPOT']
PKEYS = ['lam','phi_L','psi','k','premium','peak_cap','ou_buf_k','ou_prem','ou_cap','ou_W']


def base_vec(s):
    p = PJSON[s]
    return [p['lam'],p['phi_L'],p['psi'],p['k'],p['premium'],p['peak_cap'],
            p['ou_buf_k'],p['ou_prem'],p['ou_cap'],p['ou_W']]


def bounds_for(s, with_gain):
    b = []
    for i, key in enumerate(PKEYS):
        v = base_vec(s)[i]
        if key == 'ou_W':
            b.append((max(15, round(0.5*v)), round(1.7*v)))
        else:
            b.append((0.4*v, 2.5*v))
    if with_gain:
        b.append((0.0, 1.0))
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
    bnd = bounds_for(s, is_open)
    x0 = base_vec(s) + ([0.5] if is_open else [])
    def neg(v):
        ret, buys = evaluate(s, data, v, lo, hi, is_open)
        return -((-5.0 + buys*0.001) if buys < floor else ret)
    res = differential_evolution(neg, bnd, x0=x0, init='sobol', seed=42, maxiter=15,
        popsize=8, mutation=(0.5,1.0), recombination=0.7, tol=1e-4, polish=False,
        updating='immediate', workers=1)
    return res.x


if __name__ == '__main__':
    print('CLEAN TIEBREAKER — both signals re-optimised per fold, judged OOS\n')
    grand = {'close':0,'open':0}
    for s in NAMES:
        data = load_stock(s)
        dates = data[0]; N = len(dates)
        cuts = [int(N*f) for f in (0.5, 0.667, 0.833, 1.0)]
        folds = [(0,cuts[i]-1,cuts[i],cuts[i+1]-1) for i in range(3)]
        print(f'=== {s}  (N={N}) ===')
        print(f'  {"fold":4s}{"test":>13s}{"reopt-close":>14s}{"reopt-open":>13s}   winner')
        wins = {'close':0,'open':0}; tot = {'close':0.0,'open':0.0}
        for k,(trlo,trhi,telo,tehi) in enumerate(folds,1):
            _, bb = evaluate(s, data, base_vec(s), trlo, trhi, False)
            floor = max(8, int(0.6*bb))
            tc = optimize(s, data, trlo, trhi, floor, is_open=False)
            to = optimize(s, data, trlo, trhi, floor, is_open=True)
            rc,_ = evaluate(s, data, tc, telo, tehi, False)
            ro,ob = evaluate(s, data, to, telo, tehi, True)
            w = 'open' if ro > rc else 'close'; wins[w]+=1
            tot['close']+=rc; tot['open']+=ro
            print(f'  {k:<4d}[{telo:>3d}:{tehi:<3d}]{rc*100:>13.1f}%{ro*100:>12.1f}%   {w}'
                  f'  (open gain={to[10]:.2f})')
        print(f'  -> {s}: reopt-open beats reopt-close in {wins["open"]}/3 folds; '
              f'avg OOS close={tot["close"]/3*100:.1f}%  open={tot["open"]/3*100:.1f}%\n')
        grand['close']+=tot['close']/3; grand['open']+=tot['open']/3
        if wins['open']>=2: grand.setdefault('open_names',0)
    n=len(NAMES)
    print(f'OVERALL avg OOS across {n} names:  reopt-close={grand["close"]/n*100:.1f}%  '
          f'reopt-open={grand["open"]/n*100:.1f}%')
