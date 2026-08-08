"""
Expanding walk-forward on the admission survivors: AMD, HOOD, FSLR, ARM.

Why this exists. The admission screen rested on a single half-sample split, and the house
elimination standard does not accept that: "multiple folds, not a single split", "pattern, not
just sign", and reject only when the failure is repeated, material, explicable, and survives
BOTH frozen and refitted parameters. HOOD is the recorded case of a single split producing a
wrong elimination -- eliminated at -6%, then +95/+72/+64/-22/+36 over five folds.

Design, following the recorded mechanics:
  * EXPANDING folds -- fit on everything up to the fold boundary, freeze, score the next unseen
    slice, roll forward;
  * the filter always runs from the first session, so each slice carries its full warm-up: the
    model has read all prior bars, it simply did not trade the scored window;
  * both arms reported. REFIT re-optimises on each expanding train. FROZEN fits once on the
    first train and never again. The elimination criterion needs both to fail.

Reading it, per the house rules: with five folds 5/5 positive is meaningful (sign test p ~ 0.03)
and 3/5 is no evidence either way; with three folds even 3/3 is only p ~ 0.125, so magnitude and
the frozen arm carry more of the weight. Trade count per fold is the most-overlooked number -- a
fold under 20 trades is absence of evidence, not evidence of failure. Scattered negatives are
noise; consecutive and deepening negatives are decay. The four names are shown fold by fold so a
common-mode window -- everything failing at once -- is visible rather than mistaken for four
independent failures.

Verified fills and residual OU sigma throughout, matching the live book and the admission run.

Run:  python3 walk_forward_admit.py [folds] [slice]     # default 3 folds of 100 sessions
"""
import sys

import numpy as np

import admit_candidates as A
import ramp_premium as R
from engine import Params, run_model
from optimise_candidates import mp

NAMES = ('AMD', 'HOOD', 'FSLR', 'ARM')
CAPITAL = 1_000_000

# Folds and slice length are arguments because the two are a direct trade-off and the first
# run showed which way it binds. Five slices of 58 sessions put only 4-17 buys in each fold,
# below the 20-trade floor at which a fold counts as evidence at all, so every magnitude was
# uninterpretable. Three slices of 100 sessions give roughly 15-30 buys per fold: fewer signs
# to read, but each one means something.
FOLDS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
SLICE = int(sys.argv[2]) if len(sys.argv) > 2 else 100


def slice_return(bars, chk, vec, t, lo, hi):
    """Raw ratio over [lo,hi] plus the buys inside it. The engine runs from session zero, so
    the filter is fully warmed; only the scored window is attributed."""
    d, O, H, L, C = bars
    r = run_model(d, O, H, L, C, mp(vec, t), ou_sigma='resid',
                  same_day_exit=chk, collect=True)
    fr = r.frames
    eq = fr['equity']
    ret = eq[hi] / eq[lo] - 1.0 if eq[lo] > 0 else float('nan')
    buys = sum(fr['t1']['Z'][lo:hi + 1]) + sum(fr['t2']['Z'][lo:hi + 1])
    return ret, buys


def main():
    t0 = Params(capital=CAPITAL, years=1.0)
    results = {}
    for name in NAMES:
        bars, dv, idx = A.five_min(A.CAND[name])
        d = bars[0]
        chk = R.make_checker(idx, d, bars[1])
        n = len(d)
        step = SLICE
        bounds = [(n - (FOLDS - k) * step, n - (FOLDS - k - 1) * step - 1)
                  for k in range(FOLDS)]
        if bounds[0][0] < 200:
            raise SystemExit(f'initial train only {bounds[0][0]} sessions - too short to fit')
        print(f'\n=== {name} ===', flush=True)
        print(f'  {n} sessions; {FOLDS} slices of {step} (~{100*step/n:.0f}%); '
              f'initial train {bounds[0][0]} sessions', flush=True)

        first_vec = None
        rows = []
        for k, (lo, hi) in enumerate(bounds, 1):
            vec = A.fit(bars, chk, t0, 0, lo - 1, floor=8)
            if first_vec is None:
                first_vec = vec
            r_re, b_re = slice_return(bars, chk, vec, t0, lo, hi)
            r_fr, b_fr = slice_return(bars, chk, first_vec, t0, lo, hi)
            rows.append((k, d[lo], d[hi], r_re, b_re, r_fr, b_fr))
            print(f'  fold {k}  {d[lo]} .. {d[hi]}   refit {100*r_re:+8.1f}% '
                  f'({b_re:3d} buys)   frozen {100*r_fr:+8.1f}% ({b_fr:3d} buys)', flush=True)
        results[name] = rows

    print(f'\n\n=== summary ({FOLDS} folds of {SLICE} sessions) ===\n')
    print(f"{'name':6s} {'refit folds+':>12s} {'refit stitched':>15s} "
          f"{'frozen folds+':>13s} {'frozen stitched':>16s} {'min buys/fold':>14s}")
    for name in NAMES:
        rows = results[name]
        re = [r[3] for r in rows]
        fr = [r[5] for r in rows]
        st_re = np.prod([1 + x for x in re]) - 1
        st_fr = np.prod([1 + x for x in fr]) - 1
        minb = min(min(r[4] for r in rows), min(r[6] for r in rows))
        print(f'{name:6s} {sum(1 for x in re if x > 0):>7d}/{FOLDS:<4d} '
              f'{100*st_re:>14.1f}% {sum(1 for x in fr if x > 0):>8d}/{FOLDS:<4d} '
              f'{100*st_fr:>15.1f}% {minb:>14d}')

    print('\n=== common-mode check: the same fold across all four names ===\n')
    print(f"{'fold':5s} {'window':26s} " + ' '.join(f'{n:>9s}' for n in NAMES))
    for k in range(FOLDS):
        w = f'{results[NAMES[0]][k][1]} .. {results[NAMES[0]][k][2]}'
        cells = ' '.join(f'{100*results[n][k][3]:>8.1f}%' for n in NAMES)
        allneg = all(results[n][k][3] < 0 for n in NAMES)
        print(f'{k+1:<5d} {w:26s} {cells}' + ('   <- all four negative' if allneg else ''))

    print(f'\nreading: with {FOLDS} folds the sign test is weak on its own -- 3/3 is p ~ 0.125 --')
    print('so magnitude and the frozen arm carry more of the weight than they did at five folds.')
    print('a fold under 20 buys is still absence of evidence, not evidence of failure.')
    print('elimination requires the failure to be repeated, material, explicable, and to')
    print('survive BOTH the refit and frozen arms.')


if __name__ == '__main__':
    main()
