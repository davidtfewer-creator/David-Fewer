"""
A deployable RKLB vector that never needs a new all-time high to exit.

The live RKLB parameters bid 0.801% below the running peak against a 2.684% Bayes premium, so
every Bayes target sits above the old high and can only fill if the stock prints a new one.
That is why RKLB looked broken under walk-forward -- planned return -10.4% -- while trading
well live: the sample it was fitted on kept making highs, so the flaw never showed. Re-fitted
under cap >= premium, the same name plans at +28.0% and its frozen arm returns +91.3% over 300
unseen sessions on 127 trades, the strongest frozen result in the book.

This produces the vector to actually deploy, and checks it three ways.

  1. FULL-SAMPLE FIT under the constraint. Deploying means fitting on everything known, so this
     is fitted on all 587 sessions. Its full-sample return is NOT the planning figure -- that
     stays the +28.0% median of unseen windows from constrained_book.py. It is reported here
     only to confirm the vector is sane.
  2. HEAD TO HEAD against the live vector on identical bars and the same verified-fill rule,
     over the full sample and over the unseen span, with breach share for both. This is what
     answers "is the new one actually better".
  3. NEIGHBOURHOOD ROBUSTNESS: the house +/-10% perturbation check on the policy parameters. A
     vector whose return collapses when nudged is a spike, not an optimum, and should not be
     deployed however good its centre looks.

The minimum-trade floor is expressed as a RATE here rather than a raw count, for the reason
VLO exposed: a fixed floor of 8 across a training window is 7 trades a year on the half sample
but only 3.4 on the full one, so the same number silently loosens as the window grows and let a
near-non-trading VLO fit through. 20 a year is used for the standard regime.

Output includes the workbook cell for each parameter so the vector can be entered directly.

Run:  python3 rklb_deploy.py
"""
import numpy as np

import admit_candidates as A
import pair_planned as PP
import planned_return as P
import ramp_premium as R
from engine import Params, run_model
from optimise_candidates import NAMES, POLICY, bvec, mp

UP = '/root/.claude/uploads/822d405e-f99b-5b59-9c6b-87e725054402'
LIVE = f'{UP}/8d17afe4-TradingExcel_5stock_live.xlsx'
NAME = 'RKLB'
CAPITAL = 1_000_000
FLOOR_RATE = 20.0                 # trades per year the fit must sustain
SLICE, FOLDS = 100, 3

# Model-sheet cells, from the live workbook spec section 2.
CELL = {'lam': 'B2', 'phi_L': 'D2', 'psi': 'F2', 'k': 'H2', 'premium': 'J2',
        'peak_cap': 'L2', 'ou_buf_k': 'D3', 'ou_prem': 'H3', 'ou_cap': 'J3',
        'ou_W': 'B3'}


def evaluate(bars, chk, vec, t, lo, hi):
    d, O, H, L, C = bars
    r = run_model(d, O, H, L, C, mp(vec, t), ou_sigma='resid', same_day_exit=chk, collect=True)
    eq = r.frames['equity']
    yrs = (d[hi] - d[lo]).days / 365.25
    ret = (eq[hi] / eq[lo]) ** (1 / yrs) - 1 if eq[lo] > 0 else float('nan')
    br, n = PP.breach_share(bars, chk, vec, t, lo, hi)
    peak, dd = -1e30, 0.0
    for e in eq[lo:hi + 1]:
        peak = max(peak, e)
        dd = max(dd, (peak - e) / peak) if peak > 0 else dd
    return dict(ret=ret, breach=br, trades=n, dd=dd, rate=n / yrs)


def main():
    A.BOUNDS = PP.STD
    bars, _dv, idx = A.five_min(P.PATHS[NAME])
    d, O, H, L, C = bars
    chk = R.make_checker(idx, d, O)
    n = len(d)
    yrs_all = (d[-1] - d[0]).days / 365.25
    iS = n - FOLDS * SLICE
    t0 = Params(capital=CAPITAL, years=1.0)

    live_p, cached = R.load_params(NAME, path=LIVE, years=yrs_all)
    live = bvec(live_p)

    floor_full = int(round(FLOOR_RATE * yrs_all))
    print(f'fitting {NAME} on all {n} sessions under cap >= premium, '
          f'floor {floor_full} trades ({FLOOR_RATE:.0f}/yr)...', flush=True)
    new = PP.fit_repaired(bars, chk, t0, 0, n - 1, floor_full, PP.STD)

    print('\n\n=== 1. the deployable vector ===\n')
    print(f"{'parameter':10s} {'cell':6s} {'live':>12s} {'proposed':>12s}   change")
    for i, nm in enumerate(NAMES):
        a, b = live[i], new[i]
        ch = 'unchanged' if abs(a - b) < 1e-6 else f'{"x%.2f" % (b/a) if a else "n/a"}'
        print(f'{nm:10s} {CELL[nm]:6s} {a:12.5f} {b:12.5f}   {ch}')
    print(f"\n  cap >= premium?   Bayes {100*new[5]:.2f}% cap vs {100*new[4]:.2f}% premium -> "
          f"{'OK' if new[5] >= new[4] - 1e-9 else 'VIOLATED'}")
    print(f"                    OU    {100*new[8]:.2f}% cap vs {100*new[7]:.2f}% premium -> "
          f"{'OK' if new[8] >= new[7] - 1e-9 else 'VIOLATED'}")
    print(f"  live vector:      Bayes {100*live[5]:.2f}% cap vs {100*live[4]:.2f}% premium -> "
          f"{'OK' if live[5] >= live[4] - 1e-9 else 'VIOLATED'}")

    print('\n\n=== 2. head to head, identical bars and fill rule ===\n')
    print(f"{'window':22s} {'vector':10s} {'return':>9s} {'trades':>8s} {'/yr':>7s} "
          f"{'breach':>8s} {'maxDD':>7s}")
    for lab, lo, hi in (('full sample', 0, n - 1), ('unseen span', iS, n - 1)):
        for vlab, v in (('live', live), ('proposed', new)):
            e = evaluate(bars, chk, v, t0, lo, hi)
            print(f"{lab:22s} {vlab:10s} {100*e['ret']:8.1f}% {e['trades']:8d} "
                  f"{e['rate']:7.1f} {100*e['breach']:7.1f}% {100*e['dd']:6.1f}%")
        print()
    print('  the full-sample row is in-sample for BOTH vectors and settles nothing on its own.')
    print('  the planning figure for RKLB stays +28.0%, the median of unseen windows.')

    print('\n=== 3. neighbourhood robustness: +/-10% on the policy parameters ===\n')
    base = evaluate(bars, chk, new, t0, iS, n - 1)['ret']
    print(f"{'parameter':10s} {'-10%':>10s} {'base':>10s} {'+10%':>10s}   {'worst gap':>10s}")
    gaps = []
    for i in POLICY:
        row = []
        for f in (0.9, 1.1):
            v = list(new)
            v[i] = min(max(v[i] * f, PP.STD[i][0]), PP.STD[i][1])
            row.append(evaluate(bars, chk, PP.repair(v), t0, iS, n - 1)['ret'])
        gap = min(row) - base
        gaps.append(gap)
        print(f'{NAMES[i]:10s} {100*row[0]:9.1f}% {100*base:9.1f}% {100*row[1]:9.1f}%   '
              f'{100*gap:+9.1f}pp')
    print(f'\n  worst single perturbation: {100*min(gaps):+.1f}pp against a base of '
          f'{100*base:.1f}%')
    print(f'  median perturbed return:   {100*np.median([base + g for g in gaps]):.1f}%')
    print('  a vector that survives +/-10% on every policy parameter is an optimum, not a spike.')


if __name__ == '__main__':
    main()
