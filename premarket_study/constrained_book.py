"""
The whole book re-fitted under the no-all-time-high-breach constraint.

WHY ALL TWELVE AND NOT JUST THE FIVE INCUMBENTS. The constraint changes the basis, and the
entire point of this exercise has been that names must be compared on one. Re-fitting only the
incumbents would leave a table where five names are measured one way and seven another, which
is the exact defect the admission work set out to remove. Running all twelve costs the same
wall-clock on four processes as running five, because the fits parallelise.

THE CONSTRAINT. The engine caps each bid at G[i-1]*(1-cap), G being the running maximum high,
and sells at bid + premium*C[i-1]. A target therefore clears the old peak whenever
cap < (C/G)*premium; requiring cap >= premium is sufficient since C never exceeds G. A sleeve
that violates it can only be filled by the stock making a new high, so its exits are
conditional on the trend continuing. The deployed book contains two such Bayes sleeves today --
RKLB, premium 2.684% against a 0.801% cap, and VST, 2.182% against 1.366% -- and those are
precisely the two incumbents that fail on planned return. This run tests whether that is the
explanation.

The cap ceilings are raised from 0.07 and 0.12 to 0.25 so the constraint can be met, and the
repair lifts the cap to meet the premium rather than cutting the premium, so the take-profit
under test stays the one the fitter asked for.

TWO METRIC FIXES, both promised by earlier runs and both applied here.

  1. A fold with no trades is not evidence. NVDA's first high-premium fold returned +17.4% on
     ZERO buys -- a position carried in from before the window marking to market. Windows below
     MIN_FOLD raw trades are excluded from the median and shown struck out. MIN_FOLD is a
     degeneracy filter, not the evidence bar; the house evidence bar is 20 trades per fold and
     almost nothing here reaches it.
  2. Trade counts are reported on ONE arm. The previous table put a refit-arm rate beside a
     frozen-arm count, which invited a comparison the two numbers cannot support. Both the rate
     and the raw count are now reported for the frozen vector over the unseen span, with the
     refit rate shown separately and labelled.

Run:  python3 constrained_book.py [nproc]
"""
import multiprocessing as mp_pool
import sys

import numpy as np

import admit_candidates as A
import pair_planned as PP
import planned_return as P
import ramp_premium as R
from engine import Params

CAPITAL = 1_000_000
SLICE, FOLDS = 100, 3
MIN_FOLD = 5                      # raw trades below which a fold is not evidence of anything
BOUNDS = PP.STD                   # psi 0.25, peak_cap 0.25, ou_cap 0.25
STOP, FLOOR = 50, 8

# Unconstrained planned returns, from planned_return.log, for the before/after column.
PRIOR = {'RKLB': -10.4, 'TSM': 72.6, 'VST': 20.0, 'VRT': 94.7, 'MU': 69.4,
         'GM': 38.1, 'VLO': 38.5, 'CF': 53.1, 'AMD': 30.7, 'HOOD': 26.2,
         'FSLR': 3.4, 'ARM': 0.2}


def one(name):
    A.BOUNDS = BOUNDS
    bars, _dv, idx = A.five_min(P.PATHS[name])
    d, O, H, L, C = bars
    chk = R.make_checker(idx, d, O)
    n = len(d)
    t0 = Params(capital=CAPITAL, years=1.0, stop_days=STOP)
    bnds = [(n - (FOLDS - k) * SLICE, n - (FOLDS - k - 1) * SLICE - 1) for k in range(FOLDS)]
    iS = bnds[0][0]

    folds, vec_a = [], None
    for k, (lo, hi) in enumerate(bnds):
        vec = PP.fit_repaired(bars, chk, t0, 0, lo - 1, FLOOR, BOUNDS)
        if k == 0:
            vec_a = vec
        ret, rate, dd, _ = A.score(bars, chk, vec, t0, lo, hi)
        yrs = (d[hi] - d[lo]).days / 365.25
        folds.append(dict(k=k + 1, lo=d[lo], hi=d[hi], ret=ret, rate=rate,
                          raw=int(round(rate * yrs)), dd=dd, yrs=yrs))

    h_ret, h_rate, h_dd, _ = A.score(bars, chk, vec_a, t0, iS, n - 1)
    f_ret, _fr, _fd, _ = A.score(bars, chk, vec_a, t0, 0, iS - 1)
    yrs_u = (d[n - 1] - d[iS]).days / 365.25
    brc, frozen_trades = PP.breach_share(bars, chk, vec_a, t0, iS, n - 1)

    windows = [dict(tag=f'f{f["k"]}', ret=f['ret'], raw=f['raw']) for f in folds]
    windows.append(dict(tag='half', ret=h_ret, raw=frozen_trades))
    keep = [w for w in windows if w['raw'] >= MIN_FOLD]
    dropped = [w['tag'] for w in windows if w['raw'] < MIN_FOLD]

    return dict(
        name=name, folds=folds, half=h_ret, fitted=f_ret,
        planned=float(np.median([w['ret'] for w in keep])) if keep else float('nan'),
        planned_all=float(np.median([w['ret'] for w in windows])),
        dropped=dropped, npos=sum(1 for w in keep if w['ret'] > 0), nkeep=len(keep),
        worst=float(min(w['ret'] for w in keep)) if keep else float('nan'),
        frozen_rate=h_rate, frozen_trades=frozen_trades,
        refit_rate=sum(f['rate'] * f['yrs'] for f in folds) / yrs_u,
        dd=max([f['dd'] for f in folds] + [h_dd]), breach=brc,
        prem=vec_a[4], cap=vec_a[5], ou_prem=vec_a[7], ou_cap=vec_a[8])


def main():
    nproc = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    print(f'{len(P.ORDER)} names x {FOLDS} repaired fits on {nproc} processes...', flush=True)
    with mp_pool.Pool(nproc) as pool:
        res = {r['name']: r for r in pool.imap_unordered(one, P.ORDER)}
        for n in P.ORDER:
            r = res[n]
            print(f"  {n:5s} planned {100*r['planned']:+7.1f}%  "
                  f"{r['frozen_trades']:3d} unseen trades", flush=True)

    print('\n\n=== PLANNED RETURN under the no-breach constraint ===')
    print(f'    median of tested windows carrying at least {MIN_FOLD} trades\n')
    print(f"{'name':6s} {'group':12s} {'PLANNED':>9s} {'was':>8s} {'delta':>8s} "
          f"{'unseen tr':>10s} {'froz/yr':>8s} {'refit/yr':>9s} {'worst':>9s} "
          f"{'pos':>6s} {'maxDD':>7s}")
    for grp in ('incumbent', 'diversifier', 'candidate'):
        for n in P.ORDER:
            if P.GROUP[n] != grp:
                continue
            r = res[n]
            d = 100 * r['planned'] - PRIOR[n]
            print(f"{n:6s} {grp:12s} {100*r['planned']:+8.1f}% {PRIOR[n]:+7.1f}% "
                  f"{d:+7.1f}pp {r['frozen_trades']:10d} {r['frozen_rate']:8.1f} "
                  f"{r['refit_rate']:9.1f} {100*r['worst']:+8.1f}% "
                  f"{r['npos']:>2d}/{r['nkeep']:<3d} {100*r['dd']:6.1f}%")
        print()

    print('=== the peak cap: is any exit still conditional on a new high? ===\n')
    print(f"{'name':6s} {'premium':>8s} {'peak cap':>9s} {'ou prem':>8s} {'ou cap':>8s} "
          f"{'breach share':>13s}")
    for n in P.ORDER:
        r = res[n]
        print(f"{n:6s} {100*r['prem']:7.2f}% {100*r['cap']:8.2f}% {100*r['ou_prem']:7.2f}% "
              f"{100*r['ou_cap']:7.2f}% {100*r['breach']:12.1f}%")

    print('\n\n=== windows behind each median (struck windows carry too few trades) ===\n')
    print(f"{'name':6s} " + ' '.join(f"{'f'+str(k+1):>15s}" for k in range(FOLDS))
          + f"{'half-sample':>16s}   dropped")
    for n in P.ORDER:
        r = res[n]
        cells = ' '.join(f"{100*f['ret']:+10.1f}% {f['raw']:3d}" for f in r['folds'])
        print(f"{n:6s} {cells} {100*r['half']:+11.1f}% {r['frozen_trades']:3d}   "
              + (','.join(r['dropped']) if r['dropped'] else '-'))
    print('  (annualised return, then RAW trade count in that window)')

    print('\n\n=== did the constraint rescue RKLB and VST? ===\n')
    for n in ('RKLB', 'VST'):
        r = res[n]
        print(f"  {n}: {PRIOR[n]:+.1f}%  ->  {100*r['planned']:+.1f}%   "
              f"({100*r['prem']:.2f}% premium now backed by a {100*r['cap']:.2f}% cap, "
              f"breach {100*r['breach']:.1f}%)")
    print('\n  the deployed vectors bid 0.80% and 1.37% below the peak against premia of 2.68%')
    print('  and 2.18%. if pushing the bid below the peak recovers them, the live parameters')
    print('  are the problem and are fixable. if it does not, the names are.')

    print('\n\n=== ranked ===\n')
    ok = [n for n in P.ORDER if not np.isnan(res[n]['planned'])]
    for n in sorted(ok, key=lambda x: -res[x]['planned']):
        r = res[n]
        print(f"  {n:6s} {100*r['planned']:+7.1f}%   {r['frozen_trades']:3d} unseen trades   "
              f"worst {100*r['worst']:+6.1f}%   {r['npos']}/{r['nkeep']} positive")


if __name__ == '__main__':
    main()
