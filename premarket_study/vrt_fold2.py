"""
Why VRT's second walk-forward fold books 155 buys a year when its other folds book 40-53.

Z is not a signal counter. The engine sets Z[i]=1 only when the sleeve was FLAT the previous
session AND the low actually reached the bid, so every Z is a filled purchase and the count
cannot be inflated by repeated signals while holding. That rules out the obvious bug and leaves
turnover: a sleeve that exits the same day is flat again tomorrow and free to re-buy, so a small
enough take-profit premium converts one sleeve into a near-daily trader.

This refits VRT on the fold-2 training window and takes the run apart:

  * buys per sleeve, so a single runaway sleeve is visible;
  * same-day round trips as a share of buys -- the mechanism that frees the sleeve to re-buy;
  * holding days, which is the direct constraint on how many buys a 100-session window can hold;
  * the take-profit premium each sleeve was fitted to, against the same name's other folds;
  * profit per trade, since high turnover at a thin margin is a different animal from the same
    return earned in fewer, larger trades.

The comparison folds are refitted too, so the premium and turnover figures are like-for-like.

Run:  python3 vrt_fold2.py
"""
import numpy as np

import admit_candidates as A
import planned_return as P
import ramp_premium as R
from engine import Params, run_model
from optimise_candidates import mp

NAME = 'VRT'
CAPITAL = 1_000_000
SLICE, FOLDS = 100, 3


def dissect(bars, chk, vec, t, lo, hi, label):
    d, O, H, L, C = bars
    p = mp(vec, t)
    r = run_model(d, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk, collect=True)
    fr = r.frames
    yrs = (d[hi] - d[lo]).days / 365.25
    out = dict(label=label, yrs=yrs, prem=vec[4], ou_prem=vec[7])
    tot_b = tot_sd = tot_hold = 0
    for s in ('t1', 't2'):
        f = fr[s]
        Z = f['Z'][lo:hi + 1]
        AD = f['AD'][lo:hi + 1]          # same-day exit taken
        AE = f['AE'][lo:hi + 1]          # carried overnight
        b = int(sum(Z))
        sd = int(sum(1 for i in range(len(Z)) if Z[i] == 1 and AD[i] == 1))
        out[s] = dict(buys=b, sameday=sd, hold_days=int(sum(AE)))
        tot_b += b
        tot_sd += sd
        tot_hold += int(sum(AE))
    eq = fr['equity']
    out.update(buys=tot_b, sameday=tot_sd, hold=tot_hold,
               sessions=hi - lo + 1,
               ret=(eq[hi] / eq[lo]) ** (1 / yrs) - 1 if eq[lo] > 0 else float('nan'),
               raw=eq[hi] / eq[lo] - 1.0 if eq[lo] > 0 else float('nan'))
    out['per_yr'] = tot_b / yrs
    out['ppt'] = (out['raw'] * CAPITAL / tot_b) if tot_b else float('nan')
    return out


def main():
    bars, dv, idx = A.five_min(P.PATHS[NAME])
    d, O, H, L, C = bars
    chk = R.make_checker(idx, d, O)
    n = len(d)
    t0 = Params(capital=CAPITAL, years=1.0)
    bounds = [(n - (FOLDS - k) * SLICE, n - (FOLDS - k - 1) * SLICE - 1)
              for k in range(FOLDS)]

    rows = []
    for k, (lo, hi) in enumerate(bounds, 1):
        print(f'fitting fold {k} (train 0..{lo-1})...', flush=True)
        vec = A.fit(bars, chk, t0, 0, lo - 1, floor=8)
        rows.append(dissect(bars, chk, vec, t0, lo, hi, f'fold {k}'))
        r = rows[-1]
        print(f"  {r['label']}  {r['buys']:3d} buys in {r['sessions']} sessions "
              f"= {r['per_yr']:5.1f}/yr", flush=True)

    print(f'\n\n=== {NAME}: what drives the buy count ===\n')
    print(f"{'fold':7s} {'buys':>5s} {'/yr':>6s} {'sleeve 1':>9s} {'sleeve 2':>9s} "
          f"{'same-day':>9s} {'sd share':>9s} {'hold days':>10s} {'return':>9s}")
    for r in rows:
        print(f"{r['label']:7s} {r['buys']:5d} {r['per_yr']:6.1f} "
              f"{r['t1']['buys']:9d} {r['t2']['buys']:9d} {r['sameday']:9d} "
              f"{100*r['sameday']/max(r['buys'],1):8.0f}% {r['hold']:10d} "
              f"{100*r['ret']:+8.1f}%")

    print(f'\n=== the fitted take-profit premium, which sets the turnover ===\n')
    print(f"{'fold':7s} {'Bayes prem':>11s} {'OU prem':>9s} {'profit/trade':>14s} "
          f"{'raw return':>11s}")
    for r in rows:
        print(f"{r['label']:7s} {100*r['prem']:10.2f}% {100*r['ou_prem']:8.2f}% "
              f"{r['ppt']:>13,.0f} {100*r['raw']:+10.1f}%")

    b = [r['buys'] for r in rows]
    print(f'\n=== reading ===\n')
    print(f'  a sleeve can buy on a session only if it was flat the session before, so the')
    print(f'  ceiling for two sleeves over {rows[0]["sessions"]} sessions is '
          f'{2*rows[0]["sessions"]} buys. fold 2 used '
          f'{100*b[1]/(2*rows[0]["sessions"]):.0f}% of it, folds 1 and 3 '
          f'{100*b[0]/(2*rows[0]["sessions"]):.0f}% and '
          f'{100*b[2]/(2*rows[0]["sessions"]):.0f}%.')
    print(f'  the count is bounded and internally consistent; the question is only whether the')
    print(f'  fitted premium that produced it is one you would deploy.')


if __name__ == '__main__':
    main()
