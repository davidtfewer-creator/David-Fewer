"""
Thorough optimisation of the weekly mean-reversion parameters, then walk-forward.

The earlier test used a light budget (maxiter=8, popsize=6, single seed), which may have
under-fitted and understated what re-optimisation can achieve. Here:

  Stage 1  full-sample optimise with a large budget and several seeds, to establish whether the
           workbook parameters are in fact well placed.
  Stage 2  walk-forward at the SAME budget: fit on train weeks only, score unseen weeks against
           the workbook parameters.

All runs are minute-verified. Objective is the robust one used throughout: half the raw score
plus half the mean over +/-3% perturbations of each parameter, with a minimum-trade floor.
"""
import statistics, math, sys
from scipy.optimize import differential_evolution
from weekly_mr import DTS, O, H, L, C, COMM, INTEREST, P, verify_same_day
from weekly_structure import build_weeks, stats, tranche

WS = [stats(w) for w in build_weeks(0)]
N = len(WS)
KEYS = ['w', 'cap', 'prem', 'g', 'm']
BOUNDS = [(0.97, 1.04), (0.02, 0.25), (0.005, 0.10), (0.2, 5.0), (0.85, 1.45)]
PERT = (0.97, 1.03)


def vec2p(v): return dict(zip(KEYS, v))


def seg(p, w0, w1):
    f, t = tranche(WS, w0, w1, p=p, capital=1.0)
    return f - 1.0, t


def robust(v, w0, w1, floor):
    def one(u):
        r, t = seg(vec2p(u), w0, w1)
        return -5.0 + t*1e-3 if t < floor else r
    base = one(v); sm = []
    for i in range(len(KEYS)):
        for f in PERT:
            u = list(v); u[i] = min(max(u[i]*f, BOUNDS[i][0]), BOUNDS[i][1]); sm.append(one(u))
    return 0.5*base + 0.5*sum(sm)/len(sm)


def optimise(w0, w1, floor, seeds=(1, 7, 42), maxiter=25, popsize=14):
    best = None
    x0 = [P[k] for k in KEYS]
    for sd in seeds:
        res = differential_evolution(lambda v: -robust(v, w0, w1, floor), BOUNDS, x0=x0,
                                     init='sobol', seed=sd, maxiter=maxiter, popsize=popsize,
                                     mutation=(0.5, 1.0), recombination=0.7, tol=1e-4,
                                     polish=True, disp=False, updating='immediate', workers=1)
        if best is None or res.fun < best.fun: best = res
    return vec2p(list(best.x))


def ann(r, w0, w1):
    yrs = (DTS[WS[min(w1, N-1)]['idxs'][-1]] - DTS[WS[w0]['idxs'][0]]).days/365.25
    return (1+r)**(1/yrs) - 1


if __name__ == '__main__':
    _, tt = seg(P, 1, N-1)
    floor = max(10, int(0.4*tt))
    print(f'weeks {N}; workbook trades {tt}; trade floor {floor}\n', flush=True)

    print('=== STAGE 1: thorough full-sample optimisation (3 seeds, maxiter 25, popsize 14) ===',
          flush=True)
    rw, tw = seg(P, 1, N-1)
    print(f'workbook params : {ann(rw,1,N-1)*100:5.1f}% ann, {tw} trades', flush=True)
    th = optimise(1, N-1, floor)
    ro, to = seg(th, 1, N-1)
    print(f'optimised       : {ann(ro,1,N-1)*100:5.1f}% ann, {to} trades', flush=True)
    print('  ' + '  '.join(f'{k}: {P[k]:.4f} -> {th[k]:.4f}' for k in KEYS), flush=True)

    print('\n=== STAGE 2: walk-forward at the same budget ===', flush=True)
    cuts = [int(N*f) for f in (0.5, 0.667, 0.833, 1.0)]
    print(f'{"fold":5s}{"train":>10s}{"test":>10s}{"reopt OOS":>12s}{"workbook OOS":>15s}{"winner":>10s}',
          flush=True)
    print('-'*62, flush=True)
    wins = 0; d = []; picks = []
    for k in range(3):
        trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
        _, t_tr = seg(P, 1, trhi-1)
        f_ = max(4, int(0.4*t_tr))
        thk = optimise(1, trhi-1, f_)
        picks.append(thk)
        a, _ = seg(thk, telo, tehi)
        b, _ = seg(P, telo, tehi)
        wins += (a > b); d.append((a-b)*100)
        print(f'{k+1:<5d}{f"1-{trhi-1}":>10s}{f"{telo}-{tehi}":>10s}{a*100:>11.1f}%{b*100:>14.1f}%'
              f'{("reopt" if a > b else "workbook"):>10s}', flush=True)
    print('-'*62, flush=True)
    print(f'reopt beats workbook OOS in {wins}/3 folds; mean {statistics.mean(d):+.1f}pp', flush=True)
    print('\nfitted per fold:', flush=True)
    for i, t in enumerate(picks, 1):
        print(f'  fold {i}: ' + '  '.join(f'{k}={t[k]:.4f}' for k in KEYS), flush=True)
    print('  workbook: ' + '  '.join(f'{k}={P[k]:.4f}' for k in KEYS), flush=True)
    # stability of each parameter across folds
    print('\nspread across folds (max/min):', flush=True)
    for i, k in enumerate(KEYS):
        vals = [t[k] for t in picks]
        print(f'  {k:5s} {min(vals):.4f} - {max(vals):.4f}   ratio {max(vals)/max(min(vals),1e-9):.2f}x',
              flush=True)
    print('DONE', flush=True)
