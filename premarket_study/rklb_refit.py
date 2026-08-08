"""
Is RKLB's walk-forward failure a fact about RKLB, or about the fitter used to test it?

reconcile_basis.py established two things that make the question urgent:

  1. RKLB's DEPLOYED vector, scored on the three walk-forward fold windows, returns
     +452.9% / +52.6% / -7.8%. The REFITTED vector on the identical windows returns
     +174.7% / -35.1% / -57.7%. The deployed vector wins every fold. A good RKLB
     configuration plainly exists.
  2. RKLB's deployed psi is 0.1130. The optimiser's BOUNDS cap psi at 0.1000. The known-good
     configuration is OUTSIDE the search space, so no refit anywhere in the walk-forward could
     ever have rediscovered it.

That is enough to suspect the fitter rather than the name, but not enough to prove it, because
two things are confounded: the bound, and the search budget. differential_evolution at
maxiter=6, popsize=6 over ten dimensions is roughly 420 evaluations -- thin enough that a bad
draw is a live explanation on its own.

Three regimes, first half only, then scored frozen on the unseen half. Any improvement is
attributable because only one thing changes at a time:

  A  BOUNDS as used, budget as used            the walk-forward's own fitter
  B  psi widened to 0.25, budget as used       isolates the bound
  C  psi widened to 0.25, heavy budget         isolates the search effort

The deployed vector is scored on the same windows as the reference line. If C approaches it,
the walk-forward result was an artefact and RKLB should not be dropped on it. If C still fails
while the deployed vector succeeds, then the deployed vector is benefiting from having seen the
whole sample and the caution about RKLB stands.

A control name is run identically. VRT is chosen because it showed the other instability
symptom -- a fitted take-profit premium swinging from 0.63% to 4.73% between adjacent training
windows -- so if the fitter is the problem, VRT should move too.

Run:  python3 rklb_refit.py
"""
import multiprocessing as mp_pool

import numpy as np

import admit_candidates as A
import planned_return as P
import ramp_premium as R
from engine import Params, run_model
from optimise_candidates import BOUNDS, NAMES, bvec, mp

UP = '/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402'
LIVE = f'{UP}/8d17afe4-TradingExcel_5stock_live.xlsx'
TARGETS = ('RKLB', 'VRT')
CAPITAL = 1_000_000
SLICE, FOLDS = 100, 3

WIDE = list(BOUNDS)
WIDE[2] = (0.001, 0.25)          # psi: deployed RKLB sits at 0.1130, above the 0.1000 cap

REGIMES = (
    ('A  as-used', BOUNDS, dict(maxiter=6, popsize=6)),
    ('B  psi wide', WIDE, dict(maxiter=6, popsize=6)),
    ('C  psi wide + heavy', WIDE, dict(maxiter=30, popsize=18)),
)


def fit_with(bars, chk, t, lo, hi, floor, bounds, opt):
    from scipy.optimize import differential_evolution
    res = differential_evolution(
        lambda v: -A.robust(bars, chk, v, t, lo, hi, floor), bounds,
        seed=42, tol=0.01, mutation=(0.5, 1.0), recombination=0.7,
        polish=False, init='sobol', workers=1, **opt)
    return list(res.x)


def job(arg):
    name, ri = arg
    label, bounds, opt = REGIMES[ri]
    bars, _dv, idx = A.five_min(P.PATHS[name])
    d, O, H, L, C = bars
    chk = R.make_checker(idx, d, O)
    n = len(d)
    iS = n - FOLDS * SLICE
    t0 = Params(capital=CAPITAL, years=1.0)
    vec = fit_with(bars, chk, t0, 0, iS - 1, 8, bounds, opt)
    f_ret, _b, _dd, _e = A.score(bars, chk, vec, t0, 0, iS - 1)
    t_ret, t_buys, t_dd, _e = A.score(bars, chk, vec, t0, iS, n - 1)
    folds = []
    for k in range(FOLDS):
        lo = n - (FOLDS - k) * SLICE
        hi = n - (FOLDS - k - 1) * SLICE - 1
        folds.append(A.score(bars, chk, vec, t0, lo, hi)[0])
    return dict(name=name, ri=ri, label=label, vec=vec, fitted=f_ret, tested=t_ret,
                buys=t_buys, dd=t_dd, folds=folds)


def deployed_line(name):
    bars, _dv, idx = A.five_min(P.PATHS[name])
    d, O, H, L, C = bars
    chk = R.make_checker(idx, d, O)
    n = len(d)
    iS = n - FOLDS * SLICE
    yrs = (d[-1] - d[0]).days / 365.25
    p, cached = R.load_params(name, path=LIVE, years=yrs)
    r = run_model(d, O, H, L, C, p, ou_sigma=cached['ou_sigma'],
                  same_day_exit=chk, collect=True)
    eq = r.frames['equity']

    def an(lo, hi):
        y = (d[hi] - d[lo]).days / 365.25
        return (eq[hi] / eq[lo]) ** (1 / y) - 1 if eq[lo] > 0 else float('nan')
    folds = [an(n - (FOLDS - k) * SLICE, n - (FOLDS - k - 1) * SLICE - 1)
             for k in range(FOLDS)]
    return dict(name=name, label='deployed (in-sample)', vec=bvec(p),
                fitted=an(0, iS - 1), tested=an(iS, n - 1), folds=folds)


def main():
    jobs = [(n, ri) for n in TARGETS for ri in range(len(REGIMES))]
    print(f'{len(jobs)} fits on 4 processes; regime C is ~15x the budget of A/B',
          flush=True)
    with mp_pool.Pool(4) as pool:
        got = list(pool.imap_unordered(job, jobs))
    res = {(r['name'], r['ri']): r for r in got}
    dep = {n: deployed_line(n) for n in TARGETS}

    for n in TARGETS:
        print(f'\n\n=== {n} ===\n')
        print(f"{'regime':22s} {'fitted':>9s} {'TESTED':>9s} {'spread':>9s} "
              f"{'f1':>8s} {'f2':>8s} {'f3':>8s} {'psi':>7s}")
        d = dep[n]
        print(f"{d['label']:22s} {100*d['fitted']:8.1f}% {100*d['tested']:8.1f}% "
              f"{100*abs(d['tested']-d['fitted']):8.1f}pp "
              + ' '.join(f'{100*x:7.1f}%' for x in d['folds'])
              + f" {d['vec'][2]:7.4f}")
        for ri in range(len(REGIMES)):
            r = res[(n, ri)]
            print(f"{r['label']:22s} {100*r['fitted']:8.1f}% {100*r['tested']:8.1f}% "
                  f"{100*abs(r['tested']-r['fitted']):8.1f}pp "
                  + ' '.join(f'{100*x:7.1f}%' for x in r['folds'])
                  + f" {r['vec'][2]:7.4f}")

    print('\n\n=== fitted vectors, regime C against deployed ===\n')
    for n in TARGETS:
        print(f'{n}')
        print(f"  {'param':10s} {'deployed':>10s} {'regime C':>10s} {'bound hi':>10s}")
        for i, nm in enumerate(NAMES):
            print(f"  {nm:10s} {dep[n]['vec'][i]:10.4f} "
                  f"{res[(n, 2)]['vec'][i]:10.4f} {WIDE[i][1]:10.4f}")

    print('\n\n=== reading ===\n')
    for n in TARGETS:
        a, c, d = res[(n, 0)]['tested'], res[(n, 2)]['tested'], dep[n]['tested']
        print(f'  {n}: as-used {100*a:+.1f}%  ->  widened+heavy {100*c:+.1f}%  '
              f'(deployed, in-sample: {100*d:+.1f}%)')
    print('\n  a large A->C move means the walk-forward was measuring the fitter, not the name.')
    print('  a small one means the name really does resist being fitted out of sample.')


if __name__ == '__main__':
    main()
