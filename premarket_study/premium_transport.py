"""
Does "patient + high premium" transport across names, and is it the premium or the stop?

Two questions the NVDA sweep cannot answer on its own.

  1. Which knob is doing the work? Raising the premium and lengthening the stop were varied
     together. A 2x2 -- premium (deployed vs the 4-6% band) x stop (50d vs 200d) -- separates
     them.
  2. Does it survive a second, third, tenth name? Every idea in this study has died at that
     step, and this one has to face it too.

A convenient property makes the ten-name version honest without intraday data for eight of
them: at a 4-6% premium the model books NO same-day round trips at all, so the at-open floor
and the 5-minute-verified answer coincide. That is checked explicitly on NVDA and AVGO, where
both are available, before the floor is trusted for the rest.

Band medians throughout -- never a single premium -- because adjacent premium steps swing
about 10pp.

Run:  python3 premium_transport.py
"""
import numpy as np

import ramp_premium as R
from engine import Params

ALL_NAMES = ('NVDA', 'AVGO', 'TSM', 'RKLB', 'VST', 'VRT', 'TSLA', 'PLTR', 'SOFI', 'SPOT')
LOW = None                      # each name's own deployed premia
HIGH = (0.040, 0.045, 0.050, 0.060)
STOPS = (50, 200)


def wret(eq, dates, start, end=None):
    i0 = next(i for i, x in enumerate(dates) if x >= start)
    i1 = (len(dates) - 1) if end is None else max(i for i, x in enumerate(dates) if x <= end)
    yrs = (dates[i1] - dates[i0]).days / 365.25
    if eq[i0] <= 0 or yrs <= 0:
        return float('nan')
    return (eq[i1] / eq[i0]) ** (1 / yrs) - 1


def cell(stock, args, p, d, band, stop, mode, idx, last12):
    """Median over the premium band of (full, fitted, tested, last12m, trips/yr, same-day)."""
    prems = [None] if band is None else list(band)
    acc = [[] for _ in range(6)]
    for prem in prems:
        q = Params(**{**p.__dict__, 'stop_days': stop}) if prem is None else \
            Params(**{**p.__dict__, 'premium': prem, 'ou_prem': prem, 'stop_days': stop})
        r = R.run(stock, ramp=None, mode=mode, p=q, data=args, idx=idx)
        eq = r.frames['equity']
        tr = R.trades_of(r.frames['t1']) + R.trades_of(r.frames['t2'])
        yrs = (d[-1] - d[0]).days / 365.25
        acc[0].append(wret(eq, d, d[0]))
        acc[1].append(wret(eq, d, d[0], R.SPLIT))
        acc[2].append(wret(eq, d, R.SPLIT))
        acc[3].append(wret(eq, d, last12))
        acc[4].append(len(tr) / yrs)
        acc[5].append(R.stats(r, p, len(d))['same_day'])
    return [float(np.median(a)) for a in acc]


def main():
    # ---- 0. is the at-open floor safe to use at a high premium? ---------------------
    print('=== 0. at a 4-6% premium, does the at-open floor equal the verified answer? ===\n')
    for stock in ('NVDA', 'AVGO'):
        d, O, H, L, C = R.load_feed(stock)
        args = (d, O, H, L, C)
        p, _ = R.load_params(stock, years=(d[-1] - d[0]).days / 365.25)
        idx = R.build_index(stock)
        last12 = d[-1].replace(year=d[-1].year - 1)
        v = cell(stock, args, p, d, HIGH, 200, 'verified', idx, last12)
        f = cell(stock, args, p, d, HIGH, 200, 'at_open', idx, last12)
        print(f'  {stock}: verified {100*v[0]:6.2f}%  at-open floor {100*f[0]:6.2f}%  '
              f'gap {100*abs(v[0]-f[0]):.2f}pp   same-day trips (verified): {v[5]:.0f}')
    print('\n  -> the floor is exact where same-day trips are zero, so it is used below.\n')

    # ---- 1. the 2x2, name by name ---------------------------------------------------
    print('=== 1. premium x stop, all ten names, at-open floor. Full sample / fitted / tested ===\n')
    grid = {}
    for stock in ALL_NAMES:
        d, O, H, L, C = R.load_feed(stock)
        args = (d, O, H, L, C)
        p, _ = R.load_params(stock, years=(d[-1] - d[0]).days / 365.25)
        last12 = d[-1].replace(year=d[-1].year - 1)
        grid[stock] = {}
        for bname, band in (('deployed', LOW), ('4-6%', HIGH)):
            for stop in STOPS:
                grid[stock][(bname, stop)] = cell(stock, args, p, d, band, stop,
                                                  'at_open', None, last12)
    combos = [('deployed', 50), ('deployed', 200), ('4-6%', 50), ('4-6%', 200)]
    print(f"{'name':6s} " + ' '.join(f'{b+"/"+str(s)+"d":>16s}' for b, s in combos))
    print(f"{'':6s} " + ' '.join(f'{"full fit  test":>16s}' for _ in combos))
    for stock in ALL_NAMES:
        line = f'{stock:6s} '
        for c in combos:
            v = grid[stock][c]
            line += f'{100*v[0]:5.0f}{100*v[1]:5.0f}{100*v[2]:6.0f}  '
        print(line)

    print(f'\n=== 2. what each knob is worth, across the ten names (pp vs deployed/50d) ===\n')
    print(f"{'change':22s} {'full':>22s} {'fitted':>22s} {'tested':>22s} {'last12m':>22s}")
    print(f"{'':22s} " + ' '.join(f'{"median  n>0":>22s}' for _ in range(4)))
    for label, c in (('longer stop only', ('deployed', 200)),
                     ('higher premium only', ('4-6%', 50)),
                     ('both', ('4-6%', 200))):
        line = f'{label:22s} '
        for j in (0, 1, 2, 3):
            v = np.array([grid[s][c][j] - grid[s][('deployed', 50)][j] for s in ALL_NAMES])
            line += f'{100*np.median(v):+9.2f}pp {sum(1 for x in v if x > 0):2d}/10      '
        print(line)

    print(f'\n=== 3. trade counts: how much evidence does each configuration generate? ===\n')
    print(f"{'config':22s} {'median trips/yr':>16s} {'trades in last 12m':>20s}")
    for label, c in (('deployed / 50d', ('deployed', 50)),
                     ('deployed / 200d', ('deployed', 200)),
                     ('4-6% / 50d', ('4-6%', 50)),
                     ('4-6% / 200d', ('4-6%', 200))):
        t = np.median([grid[s][c][4] for s in ALL_NAMES])
        print(f'{label:22s} {t:16.1f} {t:20.0f}')


if __name__ == '__main__':
    main()
