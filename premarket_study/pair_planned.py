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
same residual OU sigma, same widened psi bound.

The minimum-trade floor stays at 8 across the training window, the same as every other name.
That is about seven trades a year, which the user has confirmed is an acceptable minimum for
the high-premium regime. The floor is a degeneracy guard -- it stops the optimiser finding a
do-nothing solution that collects interest and books no risk -- rather than a trade-frequency
preference, and at seven a year it leaves a 10% premium ample room. Realised buy counts are
reported so that a fit sitting on the floor is visible if it happens.

The premium ceiling is 16%, reached in two steps. It was first raised from 8% to 12% because
AVGO's optimum was expected near 10% and a low bound pins the fit at the edge and understates
the name, exactly as the old psi cap did to VRT. At 12% AVGO's third training window came back
at 11.82% -- inside the ceiling by 0.18pp, which is a boundary-seeking fit in all but name, so
its +65.7% could still have been understated. Raised again to 16% to settle it.

Both names in the regime get the same ceiling even though only AVGO motivated it. NVDA's fits
sat at 7.5-9.0%, comfortably interior, so widening cannot move it; giving AVGO a private bound
would be the per-name special-casing this exercise exists to remove, and running NVDA at the
wider bound costs nothing and confirms its optimum is genuinely interior rather than assumed.

One tension is surfaced rather than resolved silently: a high-premium name legitimately
trading eight or ten times a year would fail the proposed 25-buys-a-year admission rule, which
was calibrated on names running 1.5-2.7% premia. That rule cannot judge this regime as it
stands.

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
STD[5] = (0.002, 0.250)                  # peak cap: must be able to reach the premium
STD[8] = (0.005, 0.250)
HIGH = list(STD)
HIGH[4] = (0.040, 0.160)                 # Bayes take-profit premium; AVGO reached 11.82% at 12%
HIGH[7] = (0.040, 0.160)                 # OU take-profit premium

# The minimum-trade floor is a RATE per year, not a raw count, because a fixed count silently
# loosens as the training window grows -- 8 trades is 7/yr across the half sample and 3.4/yr
# across the full one. That is what let a near-non-trading VLO fit through elsewhere. The rate
# differs by regime on purpose: the standard regime should sustain 20 a year, while the
# high-premium regime is designed to trade less and 7 a year is the confirmed minimum there.
#          label        bounds  stop  floor (trades/yr the fit must sustain)
REGIMES = (('standard',  STD,     50, 20.0),
           ('high-prem', HIGH,   200,  7.0))


def repair(vec):
    """Never bid so close to the peak that the exit needs a new all-time high.

    The engine caps each bid at G[i-1]*(1-cap), where G is the running maximum high, and sells
    at bid + premium*C[i-1]. The target therefore clears the old peak whenever
    cap < (C/G)*premium, and since C never exceeds G, requiring cap >= premium is sufficient
    and is the form used here.

    This is not a tuning preference. A sleeve whose target sits above the all-time high can
    only be filled by the stock making a new one, so its exits are conditional on the trend
    continuing -- it looks excellent while a name keeps printing highs and stops working the
    moment that pauses, with the position then held to the stop. The deployed book already
    contains two such sleeves: RKLB (premium 2.684% against a 0.801% cap) and VST (2.182%
    against 1.366%). Those are the two incumbents that fail on planned return; TSM, VRT and MU
    all satisfy the constraint and all pass.

    It binds hardest exactly where the high-premium regime lives. At an 8-12% premium the old
    peak_cap ceiling of 0.07 made the constraint unsatisfiable, so every high-premium result
    computed before this repair was trading a breach-dependent Bayes sleeve.

    Applied by lifting the cap to meet the premium rather than by cutting the premium, so the
    take-profit under test stays the one asked for.
    """
    v = list(vec)
    v[5] = max(v[5], v[4])               # Bayes: peak_cap >= premium
    v[8] = max(v[8], v[7])               # OU:    ou_cap  >= ou_prem
    return v


def fit_repaired(bars, chk, t, lo, hi, floor, bounds):
    """A.fit, with every candidate vector repaired before it is scored."""
    from scipy.optimize import differential_evolution
    res = differential_evolution(
        lambda v: -A.robust(bars, chk, repair(v), t, lo, hi, floor), bounds,
        maxiter=6, popsize=6, seed=42, tol=0.01, mutation=(0.5, 1.0),
        recombination=0.7, polish=False, init='sobol', workers=1)
    return repair(list(res.x))


def breach_share(bars, chk, vec, t, lo, hi):
    """Of the buys in [lo,hi], what share had a sell target above the running all-time high?"""
    from optimise_candidates import mp
    from engine import run_model
    d, O, H, L, C = bars
    r = run_model(d, O, H, L, C, mp(vec, t), ou_sigma='resid', same_day_exit=chk, collect=True)
    fr = r.frames
    G = fr['G']
    tot = brc = 0
    for s in ('t1', 't2'):
        f = fr[s]
        for i in range(lo, hi + 1):
            if f['Z'][i] == 1 and f['AB'][i] is not None and G[i - 1] is not None:
                tot += 1
                if f['AB'][i] > G[i - 1] + 1e-9:
                    brc += 1
    return (brc / tot if tot else float('nan')), tot


def job(arg):
    name, ri = arg
    label, bounds, stop, floor_rate = REGIMES[ri]
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
        floor = int(round(floor_rate * (d[lo - 1] - d[0]).days / 365.25))
        vec = fit_repaired(bars, chk, t0, 0, lo - 1, floor, bounds)
        vecs.append(vec)
        if k == 0:
            vec_a = vec
        ret, buys, dd, _ = A.score(bars, chk, vec, t0, lo, hi)
        folds.append(dict(k=k + 1, lo=d[lo], hi=d[hi], ret=ret, buys=buys, dd=dd,
                          yrs=(d[hi] - d[lo]).days / 365.25))
    h_ret, _hb, h_dd, _ = A.score(bars, chk, vec_a, t0, iS, n - 1)
    f_ret, _fb, _fd, _ = A.score(bars, chk, vec_a, t0, 0, iS - 1)
    brc, ntr = breach_share(bars, chk, vec_a, t0, iS, n - 1)

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
                prem=vecs[0][4], ou_prem=vecs[0][7], vecs=vecs,
                bounds=bounds, floor_rate=floor_rate, breach=brc, ntrades=ntr)


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

    print('\n\n=== fitted premia across the three training windows ===')
    print('    a value at the ceiling is a pinned fit, not a chosen one -- the psi lesson\n')
    print(f"{'name':6s} {'regime':11s} {'ceiling':>8s} " + ' '.join(
        f"{'fit '+str(k+1):>16s}" for k in range(FOLDS)))
    for n in PAIR:
        for ri in range(len(REGIMES)):
            r = res[(n, ri)]
            hi = r['bounds'][4][1]
            cells = []
            for v in r['vecs']:
                pin = '*' if v[4] >= hi - 0.02 * (hi - r['bounds'][4][0]) else ' '
                cells.append(f"{100*v[4]:7.2f}%/{100*v[7]:6.2f}%{pin}")
            print(f"{n:6s} {r['label']:11s} {100*hi:7.1f}% " + ' '.join(cells))
    print('  (Bayes premium / OU premium per fit; * = within 2% of the ceiling)')

    print('\n\n=== the peak cap: does an exit need a new all-time high? ===')
    print('    cap must be at least the premium, else the target clears the running peak\n')
    print(f"{'name':6s} {'regime':11s} {'premium':>8s} {'peak cap':>9s} {'ou prem':>8s} "
          f"{'ou cap':>8s} {'breach share':>13s} {'unseen buys':>12s}")
    for n in PAIR:
        for ri in range(len(REGIMES)):
            r = res[(n, ri)]
            v = r['vecs'][0]
            print(f"{n:6s} {r['label']:11s} {100*v[4]:7.2f}% {100*v[5]:8.2f}% "
                  f"{100*v[7]:7.2f}% {100*v[8]:7.2f}% {100*r['breach']:12.1f}% "
                  f"{r['ntrades']:12d}")
    print('\n  breach share is measured on the unseen span with the frozen vector. with the')
    print('  repair active it should be zero or near it; anything left is the C/G slack, since')
    print('  cap >= premium is sufficient but not tight.')

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
    print('\n  NOTE: the 25-buys-a-year rule was calibrated on names running 1.5-2.7% premia.')
    print('  The high-premium regime is DESIGNED to trade less -- that is the thesis, not a')
    print('  defect -- so a name can clear every return and consistency test here and still')
    print('  fail on frequency. Read a frequency rejection below as the rule being mis-cut for')
    print('  this regime, not as evidence against the name.')


if __name__ == '__main__':
    main()
