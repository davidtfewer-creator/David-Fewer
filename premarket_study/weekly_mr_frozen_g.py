"""
Re-fit the weekly MR model with the volatility coefficient g FROZEN.

The full five-parameter walk-forward lost 3/3 folds, but the fold-by-fold parameter table split
cleanly: w, prem, cap and m each landed within 16% across all three folds and all three disagreed
with the workbook in the SAME direction, while g spanned 6x (0.59-3.53). That points at g as the
parameter absorbing the noise.

Hypothesis: hold g at the workbook value and fit only the other four, and the surviving corrections
should carry out of sample.

Same budget and same objective as the five-parameter run, so the comparison is like for like:
  Stage 1  full-sample fit, 3 seeds, maxiter 25, popsize 14, robust perturbation objective
  Stage 2  expanding walk-forward at the same budget, scored on unseen weeks against the workbook
  Stage 3  a g sensitivity sweep -- if g really is noise, the frozen level should barely matter
"""
import statistics
from scipy.optimize import differential_evolution
from weekly_mr import DTS, P
from weekly_structure import build_weeks, stats, tranche
from weekly_mr_optimise import WS, N, ann

KEYS4 = ['w', 'cap', 'prem', 'm']                       # g excluded
BOUNDS4 = [(0.97, 1.04), (0.02, 0.25), (0.005, 0.10), (0.85, 1.45)]
PERT = (0.97, 1.03)


def vec2p(v, g):
    d = dict(zip(KEYS4, v)); d['g'] = g; return d


def seg(p, w0, w1):
    f, t = tranche(WS, w0, w1, p=p, capital=1.0)
    return f - 1.0, t


def robust(v, g, w0, w1, floor):
    def one(u):
        r, t = seg(vec2p(u, g), w0, w1)
        return -5.0 + t*1e-3 if t < floor else r
    base = one(v); sm = []
    for i in range(len(KEYS4)):
        for f in PERT:
            u = list(v); u[i] = min(max(u[i]*f, BOUNDS4[i][0]), BOUNDS4[i][1]); sm.append(one(u))
    return 0.5*base + 0.5*sum(sm)/len(sm)


def optimise(g, w0, w1, floor, seeds=(1, 7, 42), maxiter=25, popsize=14):
    best = None
    x0 = [min(max(P[k], BOUNDS4[i][0]), BOUNDS4[i][1]) for i, k in enumerate(KEYS4)]
    for sd in seeds:
        res = differential_evolution(lambda v: -robust(v, g, w0, w1, floor), BOUNDS4, x0=x0,
                                     init='sobol', seed=sd, maxiter=maxiter, popsize=popsize,
                                     mutation=(0.5, 1.0), recombination=0.7, tol=1e-4,
                                     polish=True, disp=False, updating='immediate', workers=1)
        if best is None or res.fun < best.fun: best = res
    return vec2p(list(best.x), g)


if __name__ == '__main__':
    G = P['g']
    _, tt = seg(P, 1, N-1)
    floor = max(10, int(0.4*tt))
    print(f'weeks {N}; workbook trades {tt}; trade floor {floor}; g frozen at {G:.4f}\n', flush=True)

    print('=== STAGE 1: full-sample fit of w, cap, prem, m (g frozen) ===', flush=True)
    rw, tw = seg(P, 1, N-1)
    print(f'workbook       : {ann(rw,1,N-1)*100:5.1f}% ann, {tw} trades', flush=True)
    fz = optimise(G, 1, N-1, floor)
    rf, tf = seg(fz, 1, N-1)
    print(f'frozen-g fit   : {ann(rf,1,N-1)*100:5.1f}% ann, {tf} trades', flush=True)
    print('  ' + '  '.join(f'{k}: {P[k]:.4f} -> {fz[k]:.4f}' for k in KEYS4), flush=True)

    print('\n=== STAGE 2: walk-forward, g frozen throughout ===', flush=True)
    cuts = [int(N*f) for f in (0.5, 0.667, 0.833, 1.0)]
    print(f'{"fold":5s}{"train":>10s}{"test":>10s}{"frozen-g OOS":>14s}{"workbook OOS":>15s}{"winner":>10s}',
          flush=True)
    print('-'*64, flush=True)
    wins = 0; d = []; picks = []
    for k in range(3):
        trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
        _, t_tr = seg(P, 1, trhi-1)
        thk = optimise(G, 1, trhi-1, max(4, int(0.4*t_tr)))
        picks.append(thk)
        a, _ = seg(thk, telo, tehi)
        b, _ = seg(P, telo, tehi)
        wins += (a > b); d.append((a-b)*100)
        print(f'{k+1:<5d}{f"1-{trhi-1}":>10s}{f"{telo}-{tehi}":>10s}{a*100:>13.1f}%{b*100:>14.1f}%'
              f'{("frozen-g" if a > b else "workbook"):>10s}', flush=True)
    print('-'*64, flush=True)
    print(f'frozen-g beats workbook OOS in {wins}/3 folds; mean {statistics.mean(d):+.1f}pp', flush=True)

    print('\nfitted per fold (g held at workbook):', flush=True)
    for i, t in enumerate(picks, 1):
        print(f'  fold {i}: ' + '  '.join(f'{k}={t[k]:.4f}' for k in KEYS4), flush=True)
    print('  workbook: ' + '  '.join(f'{k}={P[k]:.4f}' for k in KEYS4), flush=True)
    print('\nspread across folds (max/min):', flush=True)
    for k in KEYS4:
        vals = [t[k] for t in picks]
        print(f'  {k:5s} {min(vals):.4f} - {max(vals):.4f}   ratio {max(vals)/max(min(vals),1e-9):.2f}x',
              flush=True)

    # consensus: median of the fold fits, applied to every fold's test window
    cons = {k: statistics.median(t[k] for t in picks) for k in KEYS4}; cons['g'] = G
    print('\n=== STAGE 3: consensus parameters (median of fold fits) on each test window ===',
          flush=True)
    print('  ' + '  '.join(f'{k}={cons[k]:.4f}' for k in KEYS4), flush=True)
    cw = 0; cd = []
    for k in range(3):
        telo, tehi = cuts[k], cuts[k+1]-1
        a, _ = seg(cons, telo, tehi); b, _ = seg(P, telo, tehi)
        cw += (a > b); cd.append((a-b)*100)
        print(f'  fold {k+1}: consensus {a*100:6.1f}%   workbook {b*100:6.1f}%   '
              f'{"consensus" if a > b else "workbook"}', flush=True)
    print(f'  consensus beats workbook in {cw}/3; mean {statistics.mean(cd):+.1f}pp', flush=True)
    rc, tc = seg(cons, 1, N-1)
    print(f'  full sample: {ann(rc,1,N-1)*100:5.1f}% ann, {tc} trades', flush=True)

    print('\n=== STAGE 4: does the frozen level of g matter? (full sample, other four refit) ===',
          flush=True)
    print(f'{"g":>8s}{"annualised":>13s}{"trades":>9s}', flush=True)
    for g in (0.5, 1.0, 2.0374, 3.0, 4.0):
        t_ = optimise(g, 1, N-1, floor)
        r_, n_ = seg(t_, 1, N-1)
        print(f'{g:>8.4f}{ann(r_,1,N-1)*100:>12.1f}%{n_:>9d}', flush=True)
    print('DONE', flush=True)
