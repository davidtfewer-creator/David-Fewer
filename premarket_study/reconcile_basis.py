"""
Reconcile the live spec's planning figures with the walk-forward figures. They disagree about
RKLB by 167 percentage points, and only one of them can be the admission basis.

THE HYPOTHESIS BEING TESTED. The spec's table is headed "First half / Tested half / Full sample
/ Planning figure = full sample less the haircut". Read carefully, that is not a fit-freeze-
score blade. It scores ONE parameter vector -- the deployed vector, chosen with the whole
sample visible -- on two sub-windows of the data it was fitted on. Both halves are in-sample.
The "tested half" is only tested in the sense that it is later, not in the sense that the
parameters had never seen it.

If that reading is right, running the deployed vectors over the two halves should reproduce the
spec's numbers closely: RKLB 162 / 154 / 158, TSM 34 / 82 / 57, VST 53 / 71 / 62,
VRT -5 / 192 / 67, MU 7 / 142 / 63. If it is wrong, they will not.

WHY IT MATTERS FOR RKLB. The walk-forward refits on each training window and scores the next
unseen slice. For RKLB that produced 307% fitted against 2.2% tested. Those two results are not
in contradiction -- they answer different questions:

    spec           does the DEPLOYED vector work?          (in-sample, but it is what trades)
    walk-forward   would a fitter given only the first     (out-of-sample, but it is testing
                   half have FOUND a working vector?        the fitting procedure, not the name)

RKLB trading well live is evidence for the first and says nothing about the second. Dropping a
name that is working live on the strength of the second question would be a category error.
This script separates them so the decision is made on the right one.

Three things are computed, none of which need a new fit:

  1. deployed vectors scored on both halves and the full sample, against the spec;
  2. deployed vectors scored on the three walk-forward folds, so the deployed vector and the
     refitted vector are compared fold by fold on identical windows;
  3. the same on workbook daily bars and on 5-minute-aggregated bars, to confirm the two bar
     sources agree and that neither table is an artefact of bar construction.

Verified fills and residual OU sigma throughout.

Run:  python3 reconcile_basis.py
"""
import numpy as np

import admit_candidates as A
import planned_return as P
import ramp_premium as R
from engine import Params, run_model
from optimise_candidates import NAMES, BOUNDS, bvec

UP = '/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402'
LIVE = f'{UP}/8d17afe4-TradingExcel_5stock_live.xlsx'
FIVE = ('RKLB', 'TSM', 'VST', 'VRT', 'MU')
CAPITAL = 1_000_000
SLICE, FOLDS = 100, 3

# Section 4.1 of the live workbook spec, 5 August 2026.
SPEC = {'RKLB': (162, 154, 158, 156), 'TSM': (34, 82, 57, 55), 'VST': (53, 71, 62, 60),
        'VRT': (-5, 192, 67, 65), 'MU': (7, 142, 63, 61)}
# Walk-forward refit folds, from planned_return.log, for the fold-by-fold comparison.
REFIT = {'RKLB': (174.7, -35.1, -57.7), 'TSM': (128.7, 47.4, 58.7), 'VST': (143.3, -18.5, 13.5),
         'VRT': (56.3, 131.3, 6.9), 'MU': (54.0, 89.5, 48.1)}


def ann(eq, d, lo, hi):
    yrs = (d[hi] - d[lo]).days / 365.25
    return (eq[hi] / eq[lo]) ** (1 / yrs) - 1 if eq[lo] > 0 and yrs > 0 else float('nan')


def main():
    print('loading...', flush=True)
    out = {}
    for n in FIVE:
        bars5, _dv, idx5 = A.five_min(P.PATHS[n])                  # 5-min aggregated daily
        dw, Ow, Hw, Lw, Cw = R.load_feed(n, path=LIVE)             # workbook daily
        yrs_all = (dw[-1] - dw[0]).days / 365.25
        p, cached = R.load_params(n, path=LIVE, years=yrs_all)
        out[n] = dict(bars5=bars5, idx5=idx5, wb=(dw, Ow, Hw, Lw, Cw),
                      p=p, sig=cached['ou_sigma'])
        print(f"  {n}: deployed vector read, ou_sigma={cached['ou_sigma']}", flush=True)

    print('\n\n=== 1. deployed vectors, scored the way the spec scores them ===')
    print('    one vector chosen on the whole sample, scored on two sub-windows of it\n')
    print(f"{'name':6s} {'first half':>11s} {'tested half':>12s} {'full':>8s}   "
          f"{'SPEC first':>11s} {'SPEC tested':>12s} {'SPEC full':>10s}")
    dep = {}
    for n in FIVE:
        o = out[n]
        d, O, H, L, C = o['bars5']
        chk = R.make_checker(o['idx5'], d, O)
        r = run_model(d, O, H, L, C, o['p'], ou_sigma=o['sig'], same_day_exit=chk, collect=True)
        eq = r.frames['equity']
        iS = next(k for k, x in enumerate(d) if x >= R.SPLIT)
        h1, h2, fu = ann(eq, d, 0, iS - 1), ann(eq, d, iS, len(d) - 1), ann(eq, d, 0, len(d) - 1)
        dep[n] = dict(h1=h1, h2=h2, full=fu, eq=eq, d=d, iS=iS)
        s = SPEC[n]
        print(f'{n:6s} {100*h1:10.1f}% {100*h2:11.1f}% {100*fu:7.1f}%   '
              f'{s[0]:10d}% {s[1]:11d}% {s[2]:9d}%')
    err = [abs(100 * dep[n]['full'] - SPEC[n][2]) for n in FIVE]
    print(f'\n  full-sample agreement with the spec: max error {max(err):.1f}pp, '
          f'mean {np.mean(err):.1f}pp')
    print('  -> if this is close, the spec basis is confirmed: BOTH halves are in-sample.')

    print('\n\n=== 2. deployed vector vs refitted vector, identical windows ===')
    print('    the deployed row is in-sample; the refit row is genuinely unseen\n')
    n0 = FIVE[0]
    d0 = dep[n0]['d']
    b0 = [(len(d0) - (FOLDS - k) * SLICE, len(d0) - (FOLDS - k - 1) * SLICE - 1)
          for k in range(FOLDS)]
    print(f"{'name':6s} {'basis':10s} " + ' '.join(
        f'{"f"+str(k+1)+" "+str(d0[b0[k][0]])[2:]:>16s}' for k in range(FOLDS)))
    for n in FIVE:
        d, eq = dep[n]['d'], dep[n]['eq']
        cells = ' '.join(f'{100*ann(eq, d, lo, hi):15.1f}%' for lo, hi in b0)
        print(f'{n:6s} {"deployed":10s} {cells}')
        print(f'{n:6s} {"refit":10s} ' + ' '.join(f'{x:15.1f}%' for x in REFIT[n]))

    print('\n\n=== 3. bar source: workbook daily vs 5-minute aggregated ===')
    print('    same vector, same verified-fill rule; only the daily bars differ\n')
    print(f"{'name':6s} {'5-min bars':>11s} {'workbook':>10s} {'gap':>8s}")
    for n in FIVE:
        o = out[n]
        dw, Ow, Hw, Lw, Cw = o['wb']
        chkw = R.make_checker(o['idx5'], dw, Ow)
        rw = run_model(dw, Ow, Hw, Lw, Cw, o['p'], ou_sigma=o['sig'],
                       same_day_exit=chkw, collect=True)
        fw = ann(rw.frames['equity'], dw, 0, len(dw) - 1)
        print(f"{n:6s} {100*dep[n]['full']:10.1f}% {100*fw:9.1f}% "
              f"{100*(fw-dep[n]['full']):+7.1f}pp")

    print('\n\n=== 4. are the deployed vectors even inside the search bounds? ===')
    print('    a deployed value outside BOUNDS cannot be rediscovered by any refit\n')
    print(f"{'name':6s} " + '  '.join(f'{x:>9s}' for x in NAMES))
    for n in FIVE:
        v = bvec(out[n]['p'])
        cells = []
        for i, x in enumerate(v):
            lo, hi = BOUNDS[i]
            mark = '*' if (x < lo - 1e-9 or x > hi + 1e-9) else ' '
            cells.append(f'{x:9.4f}{mark}')
        print(f'{n:6s} ' + ' '.join(cells))
    print('\n  * = outside the optimiser BOUNDS used for every refit in the walk-forward.')


if __name__ == '__main__':
    main()
