"""
NVDA and AVGO on the corrected planned-return basis, under both configurations.

These two are not like the other twelve. They were dropped from the deployed book for dragging
it down, then partially rehabilitated on a HIGH-PREMIUM setting: a take-profit of 4-6% instead
of the usual 1.5-2.7%, and a 200-calendar-day stop instead of 50. The thesis is that a name
which trends hard should be asked for a large move and given time to deliver it, rather than
scalped -- which means deliberately fewer, larger trades.

Running them only on the standard bounds would therefore test a configuration nobody proposes
to trade, and running them only on the high-premium bounds would put them on a different
footing from every other name in the table. Both are run:

  STANDARD    identical to the twelve-name table: premium 0.005-0.05, ou_prem 0.008-0.06,
              50-day stop. Answers "how do these two compare on the same basis as everyone
              else".
  HIGH-PREM   premium and ou_prem both confined to 0.040-0.080, 200-day stop. Answers "does
              the configuration that rehabilitated them survive the planned-return method".

Everything else is held identical to planned_return.py -- same three expanding fits, same four
tested windows, same median, same robust objective, same verified fills from 5-minute bars,
same residual OU sigma, same widened psi bound, same minimum-trade floor of 8. The floor is
deliberately NOT relaxed for the high-premium arm: if a configuration cannot manage eight buys
across a 287-session training window it is not a book candidate, and letting it off that would
be exactly the kind of per-name special-casing this exercise exists to remove.

Bounds are set inside the worker rather than at module scope, because the two arms need
different ones and the pool workers are reused across jobs.

Run:  python3 pair_planned.py
"""
import multiprocessing as mp_pool

import numpy as np

import admit_candidates as A
import planned_return as P
import ramp_premium as R
from engine import Params

PAIR = ('NVDA', 'AVGO')
CAPITAL = 1_000_000
SLICE, FOLDS = 100, 3

STD = list(P.WIDE)                       # psi already widened to 0.25
HIGH = list(P.WIDE)
HIGH[4] = (0.040, 0.080)                 # Bayes take-profit premium
HIGH[7] = (0.040, 0.080)                 # OU take-profit premium

REGIMES = (('standard', STD, 50), ('high-prem', HIGH, 200))


def job(arg):
    name, ri = arg
    label, bounds, stop = REGIMES[ri]
    A.BOUNDS = bounds                     # A.fit and A.robust both read this
    bars, _dv, idx = A.five_min(R.FIVE_MIN[name])
    d, O, H, L, C = bars
    chk = R.make_checker(idx, d, O)
    n = len(d)
    t0 = Params(capital=CAPITAL, years=1.0, stop_days=stop)
    bnds = [(n - (FOLDS - k) * SLICE, n - (FOLDS - k - 1) * SLICE - 1) for k in range(FOLDS)]
    iS = bnds[0][0]

    folds, vec_a, vecs = [], None, []
    for k, (lo, hi) in enumerate(bnds):
        vec = A.fit(bars, chk, t0, 0, lo - 1, floor=8)
        vecs.append(vec)
        if k == 0:
            vec_a = vec
        ret, buys, dd, _ = A.score(bars, chk, vec, t0, lo, hi)
        folds.append(dict(k=k + 1, lo=d[lo], hi=d[hi], ret=ret, buys=buys, dd=dd,
                          yrs=(d[hi] - d[lo]).days / 365.25))
    h_ret, _hb, h_dd, _ = A.score(bars, chk, vec_a, t0, iS, n - 1)
    f_ret, _fb, _fd, _ = A.score(bars, chk, vec_a, t0, 0, iS - 1)

    tested = [f['ret'] for f in folds] + [h_ret]
    yrs = (d[n - 1] - d[iS]).days / 365.25
    raw = np.prod([(1 + f['ret']) ** f['yrs'] for f in folds])
    Cn = np.array(C, dtype=float)

    return dict(name=name, ri=ri, label=label, folds=folds, half=h_ret, fitted=f_ret,
                planned=float(np.median(tested)), worst=float(min(tested)),
                npos=sum(1 for x in tested if x > 0),
                stitched=float(raw ** (1 / sum(f['yrs'] for f in folds)) - 1),
                buys=sum(f['buys'] * f['yrs'] for f in folds) / yrs,
                dd=max([f['dd'] for f in folds] + [h_dd]),
                bh=(Cn[n - 1] / Cn[iS]) ** (1 / yrs) - 1,
                prem=vecs[0][4], ou_prem=vecs[0][7], vecs=vecs)


def main():
    jobs = [(n, ri) for n in PAIR for ri in range(len(REGIMES))]
    print(f'{len(jobs)} arms x {FOLDS} fits on 4 processes...', flush=True)
    with mp_pool.Pool(4) as pool:
        got = list(pool.imap_unordered(job, jobs))
    res = {(r['name'], r['ri']): r for r in got}

    print('\n\n=== NVDA and AVGO, both configurations ===')
    print('    same method as the twelve-name table: median of four tested windows\n')
    print(f"{'name':6s} {'regime':11s} {'PLANNED':>9s} {'BUYS/YR':>8s} {'worst':>9s} "
          f"{'+/4':>4s} {'stitched':>9s} {'max DD':>7s} {'fitted':>9s} {'spread':>8s} "
          f"{'prem':>7s} {'ou prem':>8s}")
    for n in PAIR:
        for ri in range(len(REGIMES)):
            r = res[(n, ri)]
            print(f"{n:6s} {r['label']:11s} {100*r['planned']:+8.1f}% {r['buys']:8.1f} "
                  f"{100*r['worst']:+8.1f}% {r['npos']:>2d}/4 {100*r['stitched']:+8.1f}% "
                  f"{100*r['dd']:6.1f}% {100*r['fitted']:+8.1f}% "
                  f"{100*abs(r['half']-r['fitted']):7.1f}pp "
                  f"{100*r['prem']:6.2f}% {100*r['ou_prem']:7.2f}%")
        print()

    print('=== the four tested windows behind each median ===\n')
    f0 = res[(PAIR[0], 0)]['folds']
    print(f"{'name':6s} {'regime':11s} " + ' '.join(
        f"{'f'+str(f['k'])+' '+str(f['lo'])[2:]:>16s}" for f in f0) + f"{'half-sample':>16s}")
    for n in PAIR:
        for ri in range(len(REGIMES)):
            r = res[(n, ri)]
            cells = ' '.join(f"{100*f['ret']:+11.1f}% {f['buys']:3.0f}" for f in r['folds'])
            print(f"{n:6s} {r['label']:11s} {cells} {100*r['half']:+11.1f}%")

    print('\n\n=== does the high-premium thesis hold? ===\n')
    for n in PAIR:
        s, h = res[(n, 0)], res[(n, 1)]
        print(f"  {n}: standard {100*s['planned']:+.1f}% on {s['buys']:.0f} buys/yr  ->  "
              f"high-prem {100*h['planned']:+.1f}% on {h['buys']:.0f} buys/yr")
        print(f"      fewer trades? {'yes' if h['buys'] < s['buys'] else 'NO'}"
              f"   better planned? {'yes' if h['planned'] > s['planned'] else 'NO'}"
              f"   shallower drawdown? "
              f"{'yes' if h['dd'] < s['dd'] else 'NO'}"
              f"  ({100*s['dd']:.1f}% -> {100*h['dd']:.1f}%)")

    print('\n\n=== against the proposed bar ===')
    print('    planned >= 30%, buys/yr >= 25, worst window >= -15%, at least 3 of 4 positive\n')
    print(f"{'name':6s} {'regime':11s} {'planned':>9s} {'buys':>7s} {'worst':>9s} "
          f"{'+/4':>4s}  verdict")
    for n in PAIR:
        for ri in range(len(REGIMES)):
            r = res[(n, ri)]
            why = []
            if r['planned'] < 0.30:
                why.append(f"planned {100*r['planned']:.0f}% < 30%")
            if r['buys'] < 25:
                why.append(f"{r['buys']:.0f} buys/yr < 25")
            if r['worst'] < -0.15:
                why.append(f"worst {100*r['worst']:.0f}% < -15%")
            if r['npos'] < 3:
                why.append(f"only {r['npos']}/4 positive")
            print(f"{n:6s} {r['label']:11s} {100*r['planned']:+8.1f}% {r['buys']:7.1f} "
                  f"{100*r['worst']:+8.1f}% {r['npos']:>2d}/4  "
                  + ('ADMIT' if not why else 'REJECT  (' + '; '.join(why) + ')'))


if __name__ == '__main__':
    main()
