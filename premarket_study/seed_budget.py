"""
How much of the planned-return table is signal, and does more search buy any of it back?

The attribution run measured the noise floor and it is large: TSM, held at a configuration
where two arms should have agreed exactly, varied 32.1pp across three seeds. VRT and RKLB
varied 58pp. Nine of ten measured effects in that run were smaller than their own noise band,
which means the constrained table cannot rank names -- VRT 75.3 down to FSLR 31.4 is one noise
band wide, and a 30% admission threshold drawn inside it decides by coin flip.

The suspected cause is search budget. differential_evolution at maxiter=6, popsize=6 over ten
dimensions is about 420 evaluations, which is thin enough that each seed lands somewhere
different. This tests that directly by crossing seeds with budget:

  B1   maxiter  6, popsize  6     ~420 evaluations   the setting every table so far used
  B2   maxiter 20, popsize 12    ~2520 evaluations
  B3   maxiter 40, popsize 12    ~4920 evaluations

Five seeds per cell, because a spread computed from three points is barely a spread.

FOUR THINGS ARE READ OFF IT, and the fourth is the one that decides what to do.

  SPREAD      max minus min across seeds, by budget. If it collapses as budget rises, the
              table is fixable by spending compute and everything gets re-run.
  LEVEL       median across seeds, by budget. A low-budget median that sits systematically
              above the high-budget one means the cheap fits were not merely noisy but
              optimistically biased -- the published figures would be too high, not just
              uncertain.
  PARAMETERS  do the high-budget fits agree with each other on what the optimum IS? Returns can
              agree while parameters do not, which would mean the surface has many equally good
              peaks and no single vector is "the" answer.
  OVERFITTING fitted half alongside the frozen unseen half. More search can buy a better
              in-sample number and a worse out-of-sample one -- RKLB already showed exactly
              that once, at 398% fitted against 19% tested. If the spread only shrinks because
              every seed converges on the same overfitted peak, that is worse than noise, not
              better, and the answer is to simplify the model rather than search it harder.

Run on the settled configuration: widened psi and cap bounds, cap >= premium, 20 trades/yr
floor, verified fills, residual OU sigma. Three names spanning the cases -- TSM as the control,
VRT as the worst-behaved of the compliant names, RKLB as the live decision.

Roughly two to two and a half hours on four processes.

Run:  python3 seed_budget.py [nproc]
"""
import multiprocessing as mp_pool
import sys

import numpy as np

import admit_candidates as A
import pair_planned as PP
import planned_return as P
import ramp_premium as R
from engine import Params
from optimise_candidates import NAMES as PNAMES, POLICY

TARGETS = ('TSM', 'VRT', 'RKLB')
SEEDS = (42, 7, 123, 2024, 999)
BUDGETS = (('B1 maxiter6 pop6', 6, 6),
           ('B2 maxiter20 pop12', 20, 12),
           ('B3 maxiter40 pop12', 40, 12))
CAPITAL = 1_000_000
SLICE, FOLDS = 100, 3
FLOOR_RATE = 20.0
BOUNDS = PP.STD


def job(arg):
    name, bi, seed = arg
    label, maxiter, popsize = BUDGETS[bi]
    A.BOUNDS = BOUNDS
    bars, _dv, idx = A.five_min(P.PATHS[name])
    d, O, H, L, C = bars
    chk = R.make_checker(idx, d, O)
    n = len(d)
    iS = n - FOLDS * SLICE
    t0 = Params(capital=CAPITAL, years=1.0)
    floor = int(round(FLOOR_RATE * (d[iS - 1] - d[0]).days / 365.25))

    from scipy.optimize import differential_evolution
    res = differential_evolution(
        lambda v: -A.robust(bars, chk, PP.repair(v), t0, 0, iS - 1, floor), BOUNDS,
        maxiter=maxiter, popsize=popsize, seed=seed, tol=0.01, mutation=(0.5, 1.0),
        recombination=0.7, polish=False, init='sobol', workers=1)
    vec = PP.repair(list(res.x))

    f_ret, _fr, _fd, _ = A.score(bars, chk, vec, t0, 0, iS - 1)
    t_ret, rate, dd, _ = A.score(bars, chk, vec, t0, iS, n - 1)
    br, tr = PP.breach_share(bars, chk, vec, t0, iS, n - 1)
    return dict(name=name, bi=bi, seed=seed, fitted=f_ret, tested=t_ret,
                trades=tr, breach=br, dd=dd, vec=vec,
                evals=popsize * len(BOUNDS) * (maxiter + 1))


def main():
    nproc = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    jobs = [(n, bi, s) for n in TARGETS for bi in range(len(BUDGETS)) for s in SEEDS]
    print(f'{len(jobs)} fits ({len(TARGETS)} names x {len(BUDGETS)} budgets x '
          f'{len(SEEDS)} seeds) on {nproc} processes', flush=True)
    print('cheapest first so the baseline lands early\n', flush=True)
    jobs.sort(key=lambda t: t[1])
    with mp_pool.Pool(nproc) as pool:
        got = []
        for r in pool.imap_unordered(job, jobs):
            got.append(r)
            print(f"  {r['name']:5s} {BUDGETS[r['bi']][0]:20s} seed {r['seed']:<5d} "
                  f"tested {100*r['tested']:+7.1f}%  fitted {100*r['fitted']:+7.1f}%",
                  flush=True)
    D = {(r['name'], r['bi'], r['seed']): r for r in got}

    def col(n, bi, key='tested'):
        return [D[(n, bi, s)][key] for s in SEEDS]

    print('\n\n=== 1. does the spread shrink with budget? ===\n')
    print(f"{'name':6s} {'budget':20s} {'evals':>7s} " +
          ' '.join(f'{"s"+str(s):>8s}' for s in SEEDS) + f"{'median':>9s} {'SPREAD':>9s}")
    for n in TARGETS:
        for bi, (lab, _m, _p) in enumerate(BUDGETS):
            v = col(n, bi)
            ev = D[(n, bi, SEEDS[0])]['evals']
            print(f'{n:6s} {lab:20s} {ev:7d} ' + ' '.join(f'{100*x:7.1f}%' for x in v)
                  + f' {100*np.median(v):8.1f}% {100*(max(v)-min(v)):8.1f}pp')
        print()

    print('=== 2. does the level shift? (cheap fits optimistic, or just noisy?) ===\n')
    print(f"{'name':6s} " + ' '.join(f'{lab.split()[0]+" med":>12s}' for lab, _m, _p in BUDGETS)
          + f"{'B1-B3':>9s}")
    for n in TARGETS:
        meds = [np.median(col(n, bi)) for bi in range(len(BUDGETS))]
        print(f'{n:6s} ' + ' '.join(f'{100*m:11.1f}%' for m in meds)
              + f' {100*(meds[0]-meds[-1]):+8.1f}pp')

    print('\n\n=== 3. do the fits agree on the PARAMETERS at high budget? ===')
    print('    max/min across seeds for each policy parameter, budget B3\n')
    print(f"{'name':6s} " + ' '.join(f'{PNAMES[i]:>10s}' for i in POLICY) + f"{'worst':>9s}")
    for n in TARGETS:
        rat = []
        for i in POLICY:
            c = [D[(n, len(BUDGETS) - 1, s)]['vec'][i] for s in SEEDS]
            rat.append(max(c) / max(min(c), 1e-9))
        print(f'{n:6s} ' + ' '.join(f'{r:9.1f}x' for r in rat) + f'{max(rat):8.1f}x')
    print('\n  returns can agree while parameters do not. if these ratios stay large the')
    print('  surface has many equally good peaks and no single vector is THE answer.')

    print('\n\n=== 4. is extra search buying fit or buying edge? ===\n')
    print(f"{'name':6s} {'budget':20s} {'fitted med':>11s} {'tested med':>11s} "
          f"{'gap':>9s} {'trades':>7s} {'breach':>7s}")
    for n in TARGETS:
        for bi, (lab, _m, _p) in enumerate(BUDGETS):
            fm = np.median(col(n, bi, 'fitted'))
            tm = np.median(col(n, bi))
            trm = int(np.median([D[(n, bi, s)]['trades'] for s in SEEDS]))
            brm = np.median([D[(n, bi, s)]['breach'] for s in SEEDS])
            print(f'{n:6s} {lab:20s} {100*fm:10.1f}% {100*tm:10.1f}% '
                  f'{100*(fm-tm):8.1f}pp {trm:7d} {100*brm:6.1f}%')
        print()
    print('  a widening fitted-minus-tested gap as budget rises is the search finding')
    print('  in-sample structure that does not exist out of sample.')

    print('\n=== verdict ===\n')
    for n in TARGETS:
        s1 = max(col(n, 0)) - min(col(n, 0))
        s3 = max(col(n, len(BUDGETS) - 1)) - min(col(n, len(BUDGETS) - 1))
        g1 = np.median(col(n, 0, 'fitted')) - np.median(col(n, 0))
        g3 = (np.median(col(n, len(BUDGETS) - 1, 'fitted'))
              - np.median(col(n, len(BUDGETS) - 1)))
        print(f'  {n:6s} spread {100*s1:5.1f}pp -> {100*s3:5.1f}pp   '
              f'overfit gap {100*g1:6.1f}pp -> {100*g3:6.1f}pp')
    print('\n  spread down and gap flat  -> raise the budget and re-run every table.')
    print('  spread down and gap up     -> the seeds are agreeing on an overfitted peak;')
    print('                                simplify the model instead of searching harder.')
    print('  spread flat                -> budget is not the problem; too many free')
    print('                                parameters for the data to identify.')


if __name__ == '__main__':
    main()
