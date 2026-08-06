"""
The patient, high-premium daily model: premium 1%-8%, stop 50 days to never.

Everything tested so far has been within a whisker of the deployed premium (the dense sweeps
reached 1.3x, i.e. 2.25% on the Bayes leg). The proposition here is different in kind: set the
premium at 3-5%, keep the Bayes and OU bid machinery exactly as it is, and be willing to wait.
That is two knobs -- premium and stop -- on an otherwise frozen model, so it is a structural
change rather than a parameter search.

Three things this measures that the earlier work could not.

  1. LEVEL. Return, trade frequency and holding period across premiums the model has never
     been run at, and across stops from the deployed 50 calendar days out to no stop at all.

  2. FILL-RULE DEPENDENCE. The deployed model's headline collapses from 142% to 36% because
     most of its round trips are same-day and daily bars cannot order them. A high premium
     should make same-day exits nearly impossible, which would make the result independent of
     the assumption that has been doing the damage. The spread between the optimistic sheet
     rule and the no-same-day floor is reported at every premium: if it closes, the
     high-premium model is standing on much firmer evidence than the deployed one, whatever
     its level.

  3. RECENCY. Returns are reported on the full sample, the two halves, and the trailing 12 and
     6 months, so a reader who believes older data is not representative can read the recent
     columns and ignore the rest. The trailing windows are short and correspondingly noisy;
     they are shown with the trade counts that produced them so that noise is visible.

All returns are annualised off the EQUITY CURVE, not the terminal fund. At a 5% premium with a
long stop many positions are still open at the end of the sample, and the fund column values
open positions at cost, which would understate a patient strategy badly.

Run:  python3 premium_wide.py [NVDA AVGO ...]
"""
import sys

import numpy as np

import ramp_premium as R
from engine import Params

NAMES = sys.argv[1:] or ['NVDA', 'AVGO']
PREMIA = (0.010, 0.0125, 0.015, 0.0173, 0.020, 0.025, 0.030, 0.035,
          0.040, 0.045, 0.050, 0.060, 0.070, 0.080)
STOPS = (50, 100, 200, 100000)
MODE = 'verified'


def wret(eq, dates, start, end=None):
    i0 = next(i for i, x in enumerate(dates) if x >= start)
    i1 = (len(dates) - 1) if end is None else max(i for i, x in enumerate(dates) if x <= end)
    yrs = (dates[i1] - dates[i0]).days / 365.25
    if eq[i0] <= 0 or yrs <= 0:
        return float('nan')
    return (eq[i1] / eq[i0]) ** (1 / yrs) - 1


def ctx(stock):
    d, O, H, L, C = R.load_feed(stock)
    yrs = (d[-1] - d[0]).days / 365.25
    p, _ = R.load_params(stock, years=yrs)
    return d, (d, O, H, L, C), p, R.build_index(stock)


def go(args, p, prem, stop, mode, idx, stock):
    """Both sleeves at the SAME absolute premium -- the proposition is a premium level."""
    q = Params(**{**p.__dict__, 'premium': prem, 'ou_prem': prem, 'stop_days': stop})
    return R.run(stock, ramp=None, mode=mode, p=q, data=args, idx=idx)


def main():
    for stock in NAMES:
        d, args, p, idx = ctx(stock)
        L = args[3]
        yrs = (d[-1] - d[0]).days / 365.25
        last12 = d[-1].replace(year=d[-1].year - 1)
        last6 = d[-1].replace(year=d[-1].year - 1, month=d[-1].month + 6) \
            if d[-1].month <= 6 else d[-1].replace(month=d[-1].month - 6)

        print(f'\n{"="*100}')
        print(f'{stock}: premium level x stop, verified fills. '
              f'Deployed premium {p.premium:.4%} Bayes / {p.ou_prem:.4%} OU, stop {p.stop_days}d.')
        print(f'{"="*100}\n')

        for stop in STOPS:
            lbl = 'no stop' if stop > 10000 else f'{stop}d stop'
            print(f'-- {lbl} --')
            print(f"{'premium':>8s} {'full':>8s} {'fitted':>8s} {'tested':>8s} {'last12m':>8s} "
                  f"{'last6m':>8s} {'trips/y':>8s} {'medhold':>8s} {'1-day':>6s} "
                  f"{'stops':>6s} {'cash%':>6s}")
            for prem in PREMIA:
                r = go(args, p, prem, stop, MODE, idx, stock)
                eq = r.frames['equity']
                s = R.stats(r, p, len(d))
                tr = R.trades_of(r.frames['t1']) + R.trades_of(r.frames['t2'])
                hh = np.array([t[2] for t in tr]) if tr else np.array([0])
                mark = ' <' if abs(prem - p.premium) < 1e-6 else ''
                print(f"{prem:8.2%} {100*wret(eq,d,d[0]):7.2f}% {100*wret(eq,d,d[0],R.SPLIT):7.2f}% "
                      f"{100*wret(eq,d,R.SPLIT):7.2f}% {100*wret(eq,d,last12):7.2f}% "
                      f"{100*wret(eq,d,last6):7.2f}% {len(tr)/yrs:8.1f} {np.median(hh):8.0f} "
                      f"{s['same_day']:6d} {r.stop_loss_exits:6d} {s['cash_pct']:5.1f}%{mark}")
            print()

        # ---- how much does the answer still depend on the fill assumption? ------------
        print(f'-- fill-rule dependence at a {STOPS[0]}d stop: how much of the result is')
        print(f'   resting on same-day round trips that daily bars cannot order? --')
        print(f"{'premium':>8s} {'sheet':>9s} {'verified':>9s} {'no same-day':>12s} "
              f"{'spread':>8s} {'1-day trips':>12s}")
        for prem in PREMIA:
            vals = {}
            for m in ('sheet', 'verified', 'none'):
                r = go(args, p, prem, p.stop_days, m, idx, stock)
                vals[m] = wret(r.frames['equity'], d, d[0])
                if m == 'verified':
                    sd = R.stats(r, p, len(d))['same_day']
                    ntr = len(R.trades_of(r.frames['t1']) + R.trades_of(r.frames['t2']))
            print(f"{prem:8.2%} {100*vals['sheet']:8.2f}% {100*vals['verified']:8.2f}% "
                  f"{100*vals['none']:11.2f}% {100*(vals['sheet']-vals['none']):7.2f}pp "
                  f"{sd:6d}/{ntr:<5d}")

        # ---- honest summary: band medians, not the best cell ------------------------
        BANDS = (('1.0-2.0%', (0.010, 0.0125, 0.015, 0.0173, 0.020)),
                 ('2.5-3.5%', (0.025, 0.030, 0.035)),
                 ('4.0-6.0%', (0.040, 0.045, 0.050, 0.060)),
                 ('7.0-8.0%', (0.070, 0.080)))
        print(f'\n-- band MEDIANS (the surface is jagged; adjacent premium steps swing 10pp,')
        print(f'   so a single best cell is a lottery ticket, not an estimate) --')
        dep = R.run(stock, ramp=None, mode=MODE, p=p, data=args, idx=idx)
        de = dep.frames['equity']
        print(f"  deployed ({p.premium:.2%} Bayes / {p.ou_prem:.2%} OU, {p.stop_days}d stop), "
              f"same equity basis:")
        print(f"      full {100*wret(de,d,d[0]):.2f}%  fitted {100*wret(de,d,d[0],R.SPLIT):.2f}%  "
              f"tested {100*wret(de,d,R.SPLIT):.2f}%  last12m {100*wret(de,d,last12):.2f}%  "
              f"last6m {100*wret(de,d,last6):.2f}%\n")
        print(f"{'stop':>9s} {'band':>9s} {'full':>8s} {'fitted':>8s} {'tested':>8s} "
              f"{'last12m':>8s} {'last6m':>8s} {'trips/y':>8s} {'trades in':>10s}")
        print(f"{'':9s} {'':9s} {'':8s} {'':8s} {'':8s} {'':8s} {'':8s} {'':8s} {'last 12m':>10s}")
        for stop in STOPS:
            lbl = 'no stop' if stop > 10000 else f'{stop}d'
            for bname, band in BANDS:
                cols = [[] for _ in range(6)]
                n12 = []
                for prem in band:
                    r = go(args, p, prem, stop, MODE, idx, stock)
                    eq = r.frames['equity']
                    tr = R.trades_of(r.frames['t1']) + R.trades_of(r.frames['t2'])
                    cols[0].append(wret(eq, d, d[0]))
                    cols[1].append(wret(eq, d, d[0], R.SPLIT))
                    cols[2].append(wret(eq, d, R.SPLIT))
                    cols[3].append(wret(eq, d, last12))
                    cols[4].append(wret(eq, d, last6))
                    cols[5].append(len(tr) / yrs)
                    n12.append(sum(1 for t in tr if d[t[1]] >= last12))
                m = [float(np.median(c)) for c in cols]
                print(f"{lbl:>9s} {bname:>9s} {100*m[0]:7.2f}% {100*m[1]:7.2f}% {100*m[2]:7.2f}% "
                      f"{100*m[3]:7.2f}% {100*m[4]:7.2f}% {m[5]:8.1f} {int(np.median(n12)):10d}")
            print()


if __name__ == '__main__':
    main()
