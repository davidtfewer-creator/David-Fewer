"""
The control that decides the patient high-premium model: is it beating buy-and-hold, or
becoming it?

Raising the premium and lengthening the stop both do the same thing to exposure: they keep
the model in the stock for longer. Cash time falls from about 65% to about 30%. Over a window
in which these names tripled, ANY change that increases exposure will raise the measured
return, and will do it on every name at once -- which is exactly the "10 of 10" pattern the
transport test produced. That is the signature of beta, not of skill, and it has to be ruled
out before the result means anything.

So each configuration is scored against two benchmarks:

  BUY AND HOLD          the name itself, over the same window. The strategy has to beat this
                        to be worth running at all.
  EXPOSURE-MATCHED      buy-and-hold scaled to the fraction of the time the model was actually
                        invested, with idle cash earning the IBKR rate. This is the return a
                        coin-flipping strategy with the same market exposure would have made.
                        Beating THIS is what "the entry and exit rules add value" means.

The second is the one that matters. A strategy can beat exposure-matched buy-and-hold while
losing to outright buy-and-hold (it is picking good entries but is under-invested), or beat
outright buy-and-hold while losing to exposure-matched (it is just levered to a rising market
through time-in-market).

Run:  python3 premium_vs_hold.py
"""
import numpy as np

import ramp_premium as R
from engine import Params

ALL_NAMES = ('NVDA', 'AVGO', 'TSM', 'RKLB', 'VST', 'VRT', 'TSLA', 'PLTR', 'SOFI', 'SPOT')
HIGH = (0.040, 0.045, 0.050, 0.060)
CONFIGS = (('deployed/50d', None, 50), ('deployed/200d', None, 200),
           ('4-6%/50d', HIGH, 50), ('4-6%/200d', HIGH, 200))


def idx_of(dates, start, end):
    i0 = next(i for i, x in enumerate(dates) if x >= start)
    i1 = (len(dates) - 1) if end is None else max(i for i, x in enumerate(dates) if x <= end)
    return i0, i1


def ann(v0, v1, dates, i0, i1):
    yrs = (dates[i1] - dates[i0]).days / 365.25
    if v0 <= 0 or yrs <= 0:
        return float('nan')
    return (v1 / v0) ** (1 / yrs) - 1


def main():
    windows = None
    rows = {}
    for stock in ALL_NAMES:
        d, O, H, L, C = R.load_feed(stock)
        args = (d, O, H, L, C)
        p, _ = R.load_params(stock, years=(d[-1] - d[0]).days / 365.25)
        last12 = d[-1].replace(year=d[-1].year - 1)
        windows = (('full', d[0], None), ('fitted', d[0], R.SPLIT),
                   ('tested', R.SPLIT, None), ('last12m', last12, None))
        rows[stock] = {}
        for label, band, stop in CONFIGS:
            prems = [None] if band is None else list(band)
            per_w = {w[0]: [] for w in windows}
            expo = []
            for prem in prems:
                q = Params(**{**p.__dict__, 'stop_days': stop}) if prem is None else \
                    Params(**{**p.__dict__, 'premium': prem, 'ou_prem': prem, 'stop_days': stop})
                r = R.run(stock, ramp=None, mode='at_open', p=q, data=args, idx=None)
                eq = r.frames['equity']
                t1, t2 = r.frames['t1'], r.frames['t2']
                for wn, s, e in windows:
                    i0, i1 = idx_of(d, s, e)
                    per_w[wn].append(ann(eq[i0], eq[i1], d, i0, i1))
                    if wn == 'full':
                        inv = sum(t1['AE'][i] + t2['AE'][i] for i in range(len(d))) / (2 * len(d))
                        expo.append(inv)
            rows[stock][label] = ({k: float(np.median(v)) for k, v in per_w.items()},
                                  float(np.median(expo)))
        # benchmarks
        bh, bhx = {}, {}
        for wn, s, e in windows:
            i0, i1 = idx_of(d, s, e)
            bh[wn] = ann(C[i0], C[i1], d, i0, i1)
        rows[stock]['_bh'] = bh

    print('=== strategy vs buy-and-hold, at-open floor, band medians ===\n')
    for wn in ('full', 'fitted', 'tested', 'last12m'):
        print(f'-- {wn} --')
        print(f"{'name':6s} {'buy&hold':>9s} " +
              ' '.join(f'{c[0]:>14s}' for c in CONFIGS))
        print(f"{'':6s} {'':9s} " + ' '.join(f'{"ret  (expo)":>14s}' for _ in CONFIGS))
        for stock in ALL_NAMES:
            line = f"{stock:6s} {100*rows[stock]['_bh'][wn]:8.1f}% "
            for label, _b, _s in CONFIGS:
                v, ex = rows[stock][label]
                line += f'{100*v[wn]:8.1f}%{100*ex:5.0f}% '
            print(line)
        bhv = np.array([rows[s]['_bh'][wn] for s in ALL_NAMES])
        print(f"{'median':6s} {100*np.median(bhv):8.1f}% " + ' '.join(
            f'{100*np.median([rows[s][c[0]][0][wn] for s in ALL_NAMES]):8.1f}%'
            f'{100*np.median([rows[s][c[0]][1] for s in ALL_NAMES]):5.0f}%' for c in CONFIGS))
        for label, _b, _s in CONFIGS:
            beat = sum(1 for s in ALL_NAMES if rows[s][label][0][wn] > rows[s]['_bh'][wn])
            print(f"    {label:16s} beats outright buy-and-hold on {beat}/10 names")
        print()

    # ---- exposure-matched benchmark --------------------------------------------------
    print('=== exposure-matched: does the model beat a coin flip with the same time in market? ===\n')
    print('  benchmark = buy-and-hold return scaled by exposure, idle cash at 3.14%:')
    print('      r_bench = exposure * r_buyhold + (1 - exposure) * 0.0314\n')
    for wn in ('full', 'tested', 'last12m'):
        print(f'-- {wn} --')
        print(f"{'name':6s} " + ' '.join(f'{c[0]:>18s}' for c in CONFIGS))
        print(f"{'':6s} " + ' '.join(f'{"model  bench   Δ":>18s}' for _ in CONFIGS))
        agg = {c[0]: [] for c in CONFIGS}
        for stock in ALL_NAMES:
            line = f'{stock:6s} '
            for label, _b, _s in CONFIGS:
                v, ex = rows[stock][label]
                bench = ex * rows[stock]['_bh'][wn] + (1 - ex) * 0.0314
                agg[label].append(v[wn] - bench)
                line += f'{100*v[wn]:6.0f}%{100*bench:6.0f}%{100*(v[wn]-bench):+6.0f} '
            print(line)
        print(f"{'median':6s} " + ' '.join(
            f'{"":6s}{"":6s}{100*np.median(agg[c[0]]):+6.1f} ' for c in CONFIGS))
        for label, _b, _s in CONFIGS:
            v = np.array(agg[label])
            print(f'    {label:16s} median {100*np.median(v):+6.2f}pp, '
                  f'{sum(1 for x in v if x > 0)}/10 names positive')
        print()


if __name__ == '__main__':
    main()
