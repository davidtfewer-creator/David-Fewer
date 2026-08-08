"""
Why did the planned returns move? Bounds, constraint, or optimiser noise.

The constrained run reported large moves against the unconstrained one -- VRT -19.4pp, MU
-22.7pp, CF -16.9pp -- and those moves were attributed to the no-all-time-high-breach
constraint. That attribution is not safe, because three things changed at once:

  1. the cap bounds were widened, peak_cap from a 7% ceiling to 25% and ou_cap from 12% to 25%,
     so the constraint could be satisfied at a 10% premium;
  2. the constraint cap >= premium was imposed;
  3. nothing was done about optimiser noise, which a floor change alone was later shown to be
     worth up to 28pp on RKLB.

The widening was not incidental. Two thirds of the constrained fits chose values impossible
under the old ceilings -- peak_cap above 7% for VRT, MU, AMD, CF, VLO and ARM, ou_cap above 12%
for eight of twelve names -- so every earlier figure came from a fitter pinned at a ceiling,
the same defect as the old psi cap. Meanwhile the constraint is plainly INACTIVE on most normal
premia: VRT chose a 13.43% cap against a 2.44% premium, five times the minimum it was forced
to clear. A constraint that is not binding cannot be what moved the number.

So the two effects are separated by changing one thing at a time, with seeds repeated so the
noise band is visible rather than confounding:

  A  cap bounds as originally shipped (7% / 12%), no constraint
  B  cap bounds widened to 25% / 25%, no constraint          -- isolates the BOUNDS
  C  cap bounds widened, constraint cap >= premium imposed   -- isolates the CONSTRAINT

psi stays widened in all three arms: that fix is settled and holding it constant keeps it out
of the comparison. The trade floor is the same 20/yr rate everywhere for the same reason.

Names are chosen to span the cases. TSM is the control -- it chose 6.82% and 7.81%, inside both
old ceilings, so arms A and B should agree and any gap between them is pure noise. VRT, MU and
AMD all hit old ceilings and all moved double digits. RKLB is the name whose live vector
violates the constraint outright, so it is the one place the constraint should genuinely bite.

Scored on the frozen unseen span only: fit on the first 287 sessions, freeze, score the
remaining 300. One fit per cell rather than three, because the question is attribution, not
another planned return.

Run:  python3 attribution.py [nproc]
"""
import multiprocessing as mp_pool
import sys

import numpy as np

import admit_candidates as A
import pair_planned as PP
import planned_return as P
import ramp_premium as R
from engine import Params
from optimise_candidates import BOUNDS as SHIPPED

NAMES = ('TSM', 'VRT', 'MU', 'AMD', 'RKLB')
SEEDS = (42, 7, 123)
CAPITAL = 1_000_000
SLICE, FOLDS = 100, 3
FLOOR_RATE = 20.0

NARROW = list(P.WIDE)                      # psi already 0.25; cap ceilings as shipped
NARROW[5] = SHIPPED[5]                     # peak_cap (0.002, 0.07)
NARROW[8] = SHIPPED[8]                     # ou_cap   (0.005, 0.12)
WIDECAP = list(PP.STD)                     # peak_cap and ou_cap both (.., 0.25)

ARMS = (('A shipped caps', NARROW, False),
        ('B wide caps', WIDECAP, False),
        ('C wide + constraint', WIDECAP, True))


def fit_arm(bars, chk, t, lo, hi, floor, bounds, seed, use_repair):
    from scipy.optimize import differential_evolution
    fix = PP.repair if use_repair else (lambda v: list(v))
    res = differential_evolution(
        lambda v: -A.robust(bars, chk, fix(v), t, lo, hi, floor), bounds,
        maxiter=6, popsize=6, seed=seed, tol=0.01, mutation=(0.5, 1.0),
        recombination=0.7, polish=False, init='sobol', workers=1)
    return fix(list(res.x))


def job(arg):
    name, ai, seed = arg
    label, bounds, use_repair = ARMS[ai]
    A.BOUNDS = bounds
    bars, _dv, idx = A.five_min(P.PATHS[name])
    d, O, H, L, C = bars
    chk = R.make_checker(idx, d, O)
    n = len(d)
    iS = n - FOLDS * SLICE
    t0 = Params(capital=CAPITAL, years=1.0)
    floor = int(round(FLOOR_RATE * (d[iS - 1] - d[0]).days / 365.25))

    vec = fit_arm(bars, chk, t0, 0, iS - 1, floor, bounds, seed, use_repair)
    ret, rate, dd, _ = A.score(bars, chk, vec, t0, iS, n - 1)
    br, tr = PP.breach_share(bars, chk, vec, t0, iS, n - 1)
    pin = (vec[5] >= bounds[5][1] - 0.02 * (bounds[5][1] - bounds[5][0])
           or vec[8] >= bounds[8][1] - 0.02 * (bounds[8][1] - bounds[8][0]))
    return dict(name=name, ai=ai, seed=seed, ret=ret, trades=tr, breach=br, dd=dd,
                prem=vec[4], cap=vec[5], ou_prem=vec[7], ou_cap=vec[8], pinned=pin)


def main():
    nproc = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    jobs = [(n, ai, s) for n in NAMES for ai in range(len(ARMS)) for s in SEEDS]
    print(f'{len(jobs)} fits ({len(NAMES)} names x {len(ARMS)} arms x {len(SEEDS)} seeds) '
          f'on {nproc} processes...', flush=True)
    with mp_pool.Pool(nproc) as pool:
        got = list(pool.imap_unordered(job, jobs))
    R_ = {(r['name'], r['ai'], r['seed']): r for r in got}

    def cell(n, ai):
        return [R_[(n, ai, s)]['ret'] for s in SEEDS]

    print('\n\n=== frozen unseen span, by arm, across three seeds ===\n')
    print(f"{'name':6s} {'arm':22s} " + ' '.join(f'{"seed "+str(s):>10s}' for s in SEEDS)
          + f"{'median':>10s} {'spread':>9s}")
    for n in NAMES:
        for ai, (lab, _b, _r) in enumerate(ARMS):
            v = cell(n, ai)
            print(f'{n:6s} {lab:22s} ' + ' '.join(f'{100*x:9.1f}%' for x in v)
                  + f' {100*np.median(v):9.1f}% {100*(max(v)-min(v)):8.1f}pp')
        print()

    print('=== attribution: median across seeds ===\n')
    print(f"{'name':6s} {'A shipped':>10s} {'B wide':>10s} {'C +constr':>10s}   "
          f"{'bounds A->B':>12s} {'constraint B->C':>16s} {'noise band':>12s}")
    for n in NAMES:
        a, b, c = (np.median(cell(n, i)) for i in range(3))
        noise = max(max(cell(n, i)) - min(cell(n, i)) for i in range(3))
        print(f'{n:6s} {100*a:9.1f}% {100*b:9.1f}% {100*c:9.1f}%   '
              f'{100*(b-a):+11.1f}pp {100*(c-b):+15.1f}pp {100*noise:11.1f}pp')

    print('\n  read each effect against the noise band on the same row. an A->B or B->C move')
    print('  smaller than the band is not distinguishable from the optimiser wandering.')

    print('\n\n=== was the fitter pinned at a cap ceiling? ===\n')
    print(f"{'name':6s} {'arm':22s} {'peak cap':>9s} {'ou cap':>8s} {'premium':>8s} "
          f"{'pinned':>7s} {'breach':>7s} {'trades':>7s}")
    for n in NAMES:
        for ai, (lab, _b, _r) in enumerate(ARMS):
            r = R_[(n, ai, SEEDS[0])]
            print(f"{n:6s} {lab:22s} {100*r['cap']:8.2f}% {100*r['ou_cap']:7.2f}% "
                  f"{100*r['prem']:7.2f}% {'YES' if r['pinned'] else '-':>7s} "
                  f"{100*r['breach']:6.1f}% {r['trades']:7d}")
        print()
    npin = sum(1 for r in got if r['ai'] == 0 and r['pinned'])
    print(f'  arm A pinned in {npin} of {len(NAMES)*len(SEEDS)} fits. every pinned fit is a')
    print('  parameter the shipped ceiling would not let the fitter reach.')

    print('\n\n=== verdict ===\n')
    for n in NAMES:
        a, b, c = (np.median(cell(n, i)) for i in range(3))
        noise = max(max(cell(n, i)) - min(cell(n, i)) for i in range(3))
        bits = []
        bits.append(f'bounds {100*(b-a):+.0f}pp'
                    + ('' if abs(b - a) > noise else ' (within noise)'))
        bits.append(f'constraint {100*(c-b):+.0f}pp'
                    + ('' if abs(c - b) > noise else ' (within noise)'))
        print(f'  {n:6s} noise {100*noise:5.1f}pp   ' + '   '.join(bits))


if __name__ == '__main__':
    main()
