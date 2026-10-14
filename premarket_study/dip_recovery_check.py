"""
Is the dip-recovery spread real, and is it NEW information?

dip_recovery.py found P(recover within 50 calendar days of being 10% down)
ranging from GM's 0% to MU's 80%. Two things have to be true before that is
worth building on, and this session has already been caught out once by not
checking the second.

1. STABILITY. Each name has only 3-10 episodes at a 10% threshold, so GM's 0%
   rests on three observations. If the ordering holds as the threshold moves
   (5%, 7.5%, 10%, 15% -- which changes both the number of episodes and which
   ones qualify), the spread is a property of the name. If it reshuffles, it is
   noise and nothing should be built on it.

2. NOVELTY. §3.14 found volatility and AI correlation are the same axis; §3.45
   found a candidate set that was AI-correlated by construction; §3.50 found
   turnover joins them. Three times, the "new" measure turned out to be the old
   one. So dip recovery is ranked against daily volatility, AI beta and the
   measured fills-per-year, and if it correlates strongly with any of them it is
   not new and should be dropped.

Fills/yr are the measured figures from §3.49 (book_turnover.py, deployed
parameters), hardcoded because four of the nine deployed vectors live only in
the workbook, which is not currently attached (§3.54 open item 7).

Usage:  python3 dip_recovery_check.py
"""
import json
import math
import statistics

import numpy as np

from dip_recovery import BOOK, episodes
from fresh_opt_cands import daily_from_5min

DEPTHS = (0.05, 0.075, 0.10, 0.15)
AI = ('TSM', 'VRT', 'VST', 'AVGO', 'MU', 'MRVL')
# §3.49, book_turnover.py at deployed/reference parameters. MRVL omitted: its
# only measured figure (§3.50) is on a different basis (train-half frozen).
FILLS_YR = {'TSM': 91.5, 'VRT': 69.6, 'VST': 74.8, 'AVGO': 59.7, 'MU': 56.1,
            'GM': 60.3, 'VLO': 34.6, 'CF': 25.7}


def p_rec(dts, C, depth, cal=50):
    eps = episodes(dts, C, depth)
    if not eps:
        return None, 0
    good = sum(1 for e in eps if e['recovered'] and e['cal_hit'] <= cal)
    return good/len(eps)*100, len(eps)


def spearman(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pairs) < 4:
        return float('nan')
    xs, ys = zip(*pairs)
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0]*len(v)
        for p, i in enumerate(o):
            r[i] = p
        return r
    return float(np.corrcoef(rank(list(xs)), rank(list(ys)))[0, 1])


def main():
    data = {n: daily_from_5min(n) for n in BOOK}
    print('1. STABILITY — P(recover within 50 calendar days) at four thresholds\n')
    print(f'{"name":6s}' + ''.join(f'{f"{d*100:.1f}%":>16s}' for d in DEPTHS))
    print(f'{"":6s}' + ''.join(f'{"P50  (n eps)":>16s}' for _ in DEPTHS))
    cols = {d: [] for d in DEPTHS}
    for nm in BOOK:
        dts, O, H, L, C = data[nm]
        cells = []
        for d in DEPTHS:
            p, n = p_rec(dts, C, d)
            cols[d].append(p)
            cells.append(f'{(f"{p:.0f}%" if p is not None else "-"):>7s}  ({n:>2d})    ')
        print(f'{nm:6s}' + ''.join(c[:16] for c in cells), flush=True)
    print('\n  rank correlation between thresholds (is the ordering the same name-by-name?)')
    for i, d1 in enumerate(DEPTHS):
        for d2 in DEPTHS[i+1:]:
            print(f'    {d1*100:4.1f}% vs {d2*100:4.1f}%   rho {spearman(cols[d1], cols[d2]):+.2f}',
                  flush=True)

    print('\n2. NOVELTY — is dip recovery just volatility, beta or turnover again?\n')
    # AI factor from its six constituents, same definition as elsewhere
    cl = {n: dict(zip(data[n][0], data[n][4])) for n in BOOK}
    cal = sorted(set.intersection(*(set(cl[n]) for n in BOOK)))
    R = {n: np.array([cl[n][cal[i]]/cl[n][cal[i-1]] - 1 for i in range(1, len(cal))])
         for n in BOOK}
    factor = np.mean(np.vstack([R[n] for n in AI]), axis=0)
    p10 = cols[0.10]
    vol = [float(np.std(R[n]))*math.sqrt(252)*100 for n in BOOK]
    beta = [float(np.polyfit(factor, R[n], 1)[0]) for n in BOOK]
    fills = [FILLS_YR.get(n) for n in BOOK]
    print(f'{"name":6s}{"P(rec<=50cal)":>15s}{"ann vol":>10s}{"AI beta":>10s}{"fills/yr":>10s}')
    for i, nm in enumerate(BOOK):
        print(f'{nm:6s}{(f"{p10[i]:.0f}%" if p10[i] is not None else "-"):>15s}'
              f'{vol[i]:>9.0f}%{beta[i]:>10.2f}'
              f'{(f"{fills[i]:.1f}" if fills[i] else "-"):>10s}', flush=True)
    print()
    for lbl, v in (('annualised volatility', vol), ('AI beta', beta), ('fills/yr', fills)):
        r = spearman(p10, v)
        verdict = 'NOT the same axis' if abs(r) < 0.4 else 'collinear — drop it'
        print(f'  P(rec<=50cal) vs {lbl:22s} rho {r:+.2f}   {verdict}', flush=True)
    json.dump(dict(stability={str(d): dict(zip(BOOK, cols[d])) for d in DEPTHS},
                   vol=dict(zip(BOOK, vol)), beta=dict(zip(BOOK, beta)),
                   fills_yr=FILLS_YR),
              open('dip_recovery_check.json', 'w'), indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
