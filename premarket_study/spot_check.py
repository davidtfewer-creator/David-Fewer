"""
SPOT re-examined on the corrected basis.

SPOT was rejected in the admission run at a tested half of -26.8%, the worst of the nine
candidates in that batch. Standing policy is that a material engine change triggers a re-test,
and four have landed since that verdict, every one of which moved other names materially:

  * the psi cap of 0.1000, which was pinning fitters at a boundary -- freeing it moved VRT's
    planned return by +46.5pp and FSLR's by -23.1pp;
  * the peak-cap ceiling of 0.07, which made cap >= premium unsatisfiable, so fits were free to
    place sell targets above the running all-time high and bank profit that only exists while a
    name keeps printing highs -- imposing it moved RKLB by +38.4pp and VRT by -45.9pp;
  * the minimum-trade floor, now a rate rather than a raw count, after a fixed count let VLO
    fit a near-non-trading solution;
  * planned return itself, which is now the median of tested windows rather than a single
    half-sample score -- and a single split is exactly what rejected SPOT.

So SPOT's -26.8% was produced by a fitter searching a truncated space, allowed to assume
breach-dependent exits, and judged on one window. None of those three is still true. This runs
it through the identical pipeline the twelve-name book now uses, so the result is directly
comparable rather than merely suggestive.

Nothing here is special to SPOT: constrained_book.one is called unmodified, with SPOT patched
into the shared path and group tables so it takes exactly the same code path as every other
name.

Run:  python3 spot_check.py
"""
import numpy as np

import admit_candidates as A
import constrained_book as CB
import planned_return as P

NAME = 'SPOT'
# Prior verdicts for this name, for the before/after line.
OLD_TESTED = -26.8          # admission run, single half-sample split, pre-fix engine
OLD_CORR = 0.187


def main():
    P.PATHS[NAME] = A.CAND[NAME]
    P.GROUP[NAME] = 'candidate'
    print(f'{NAME}: 3 repaired fits under cap >= premium, '
          f'floor {CB.FLOOR_RATE:.0f} trades/yr...', flush=True)
    r = CB.one(NAME)

    print(f'\n\n=== {NAME} on the corrected basis ===\n')
    print(f"  PLANNED RETURN      {100*r['planned']:+.1f}%   "
          f"(median of {r['nkeep']} tested windows carrying >= {CB.MIN_FOLD} trades)")
    print(f"  unseen trades       {r['frozen_trades']:d}  "
          f"({r['frozen_rate']:.1f}/yr frozen, {r['refit_rate']:.1f}/yr refit)")
    print(f"  worst window        {100*r['worst']:+.1f}%")
    print(f"  windows positive    {r['npos']}/{r['nkeep']}")
    print(f"  max drawdown        {100*r['dd']:.1f}%")
    print(f"  breach share        {100*r['breach']:.1f}%")
    print(f"  fitted half         {100*r['fitted']:+.1f}%   "
          f"frozen unseen span {100*r['half']:+.1f}%")
    if r['dropped']:
        print(f"  windows dropped     {','.join(r['dropped'])} (too few trades to be evidence)")

    print(f'\n  premium {100*r["prem"]:.2f}% against a {100*r["cap"]:.2f}% peak cap; '
          f'OU {100*r["ou_prem"]:.2f}% against {100*r["ou_cap"]:.2f}%')

    print(f'\n\n=== the tested windows ===\n')
    for f in r['folds']:
        print(f"  fold {f['k']}  {f['lo']} .. {f['hi']}   "
              f"{100*f['ret']:+8.1f}%   {f['raw']:3d} trades")
    print(f"  frozen    whole unseen span      {100*r['half']:+8.1f}%   "
          f"{r['frozen_trades']:3d} trades")

    print(f'\n\n=== against the earlier rejection ===\n')
    print(f"  admission run, single split, pre-fix engine:  {OLD_TESTED:+.1f}%")
    print(f"  corrected basis, median of unseen windows:    {100*r['planned']:+.1f}%")
    print(f"  movement:                                     "
          f"{100*r['planned']-OLD_TESTED:+.1f}pp")

    print(f'\n\n=== against the bar ===')
    print('    planned >= 30%, worst window >= -15%, at least 3 of 4 windows positive,')
    print('    and enough unseen trades to be evidence\n')
    why = []
    if r['planned'] < 0.30:
        why.append(f"planned {100*r['planned']:.0f}% < 30%")
    if r['worst'] < -0.15:
        why.append(f"worst window {100*r['worst']:.0f}% < -15%")
    if r['npos'] < 3:
        why.append(f"only {r['npos']}/{r['nkeep']} windows positive")
    if r['frozen_trades'] < 30:
        why.append(f"{r['frozen_trades']} unseen trades < 30")
    print(f"  {NAME}: " + ('ADMIT' if not why else 'REJECT  (' + '; '.join(why) + ')'))
    print(f"\n  for reference, correlation to the AI factor was {OLD_CORR:.3f} -- low, but that")
    print('  binds on nothing: AI weighting is a judgement call, not an admission test.')


if __name__ == '__main__':
    main()
