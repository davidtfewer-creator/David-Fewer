"""
fit_recent.py — the fit test (fittability.py: 300 random vectors, seed 42,
train->test rank correlation of annualised segment returns) re-run on the MOST
RECENT two 12-month windows, for names that changed character (user, 23 Oct
2026: PLTR, TSLA). Each vector's model runs once over the whole file (state
carries, Apr-Jul 2024 is warm-up) and is scored on several window pairs:

  recent   Aug 2024 - Jul 2025  ->  Aug 2025 - Jul 2026   (asked for)
  Jun      Jun 2024 - May 2025  ->  Jun 2025 - May 2026   (stability)
  Apr      Apr 2024 - Mar 2025  ->  Apr 2025 - Mar 2026   (stability)
  original train/test split at 2025-05-23 (fittability.py)

Controls with known rho are included to calibrate the windows.
Usage: python3 fit_recent.py TICKER ...
"""
import datetime as dt
import json
import random
import statistics
import sys

import numpy as np

from two_day import Clock, bounds_for
from fittability import DRAWS, rank

PAIRS = {
    'recent': ((dt.date(2024, 8, 1), dt.date(2025, 7, 31)), (dt.date(2025, 8, 1), dt.date(2026, 7, 31))),
    'Jun': ((dt.date(2024, 6, 1), dt.date(2025, 5, 31)), (dt.date(2025, 6, 1), dt.date(2026, 5, 31))),
    'Apr': ((dt.date(2024, 4, 1), dt.date(2025, 3, 31)), (dt.date(2025, 4, 1), dt.date(2026, 3, 31))),
}


def idx(D, lo, hi):
    a = next(i for i, d in enumerate(D) if d >= lo)
    b = max(i for i, d in enumerate(D) if d <= hi)
    return a, b


def main():
    names = [a for a in sys.argv[1:] if not a.startswith('--')]
    rng = random.Random(42)
    vecs = [[rng.uniform(lo, hi) for lo, hi in bounds_for(1)] for _ in range(DRAWS)]
    out = {}
    print(f'{"name":6s}{"original":>10s}' + ''.join(f'{p:>10s}' for p in PAIRS)
          + '   recent windows: median return 1st / 2nd 12 months')
    for nm in names:
        c = Clock(nm, 1, 0)
        win = {'original': ((0, c.cut - 1), (c.cut, c.N - 1))}
        for p, (w1, w2) in PAIRS.items():
            win[p] = (idx(c.D, *w1), idx(c.D, *w2))
        sc = {p: ([], []) for p in win}
        for v in vecs:
            fr = c.run(v).frames
            eq, z = fr['equity'], [a + b for a, b in zip(fr['t1']['Z'], fr['t2']['Z'])]
            for p, ((a0, a1), (b0, b1)) in win.items():
                fa, fb = sum(z[a0:a1 + 1]), sum(z[b0:b1 + 1])
                if fa < 5 or fb < 5 or eq[a0] <= 0 or eq[b0] <= 0:
                    continue
                sc[p][0].append(c.ann(eq[a1] / eq[a0] - 1, a0, a1))
                sc[p][1].append(c.ann(eq[b1] / eq[b0] - 1, b0, b1))
        res = {}
        for p, (x, y) in sc.items():
            res[p] = dict(n=len(x), rho=float(np.corrcoef(rank(x), rank(y))[0, 1]) if len(x) >= 20 else None,
                          med1=statistics.median(x) if x else None, med2=statistics.median(y) if y else None)
        out[nm] = res
        print(f'{nm:6s}' + ''.join(f'{res[p]["rho"]:>+10.2f}' if res[p]['rho'] is not None else f'{"n/a":>10s}'
                                   for p in win)
              + f'   {res["recent"]["med1"]:+6.1f}% / {res["recent"]["med2"]:+6.1f}%  (n={res["recent"]["n"]})',
              flush=True)
    try:
        prev = json.load(open('fit_recent.json'))
    except (FileNotFoundError, ValueError):
        prev = {}
    prev.update(out)
    json.dump(prev, open('fit_recent.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
