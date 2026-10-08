"""
g1_screen.py — G1 classification for candidate names (8 Oct 2026).

The cheap gate, run before any fit: how much of a candidate's return is the AI
trade? §3.14 set the rule — a name whose AI beta and book correlation are low
faces a 30% return gate, one that trades with the factor faces 50%. §3.32 added
the profile columns that decide whether a name can even address CF's problem,
and §3.33 showed no price screen predicts turnover (that follows the fitted
premium), so these are read as context, not as a verdict.

Incumbent diversifiers are printed alongside for scale: CF is the name any
candidate would replace, GM and VLO the other two in the slot class.

Usage: BAYES_WORKBOOK=<workbook.xlsx> python g1_screen.py TICKER [TICKER ...]
"""
import sys

import numpy as np

from baseline_check import load
from fresh_opt_cands import daily_from_5min

AI = ('TSM', 'VRT', 'VST', 'AVGO', 'MU', 'MRVL')
REFS = ('CF', 'GM', 'VLO')


def rets_on(cal, dts, C):
    idx = {d: i for i, d in enumerate(dts)}
    out = [np.nan]
    for d in cal[1:]:
        i = idx.get(d)
        out.append(C[i] / C[i - 1] - 1 if (i is not None and i > 0) else np.nan)
    return np.array(out)


def dip_recover(O, H, L, C, dip=0.02, rec=0.025, win=10):
    n, opp, hit = len(C), 0, 0
    for i in range(1, n - win):
        thr = C[i - 1] * (1 - dip)
        if L[i] <= thr:
            opp += 1
            hit += max(H[i + 1:i + 1 + win]) >= thr * (1 + rec)
    return opp / n, hit / n


def main():
    cands = sys.argv[1:]
    data, sleeves, cal, _ = load()
    book = sorted(data)

    R, series = {}, {}
    for nm in book:
        d = data[nm]
        C = [d['C'][d['idx'][x]] for x in cal]
        R[nm] = np.array([np.nan] + [C[i] / C[i - 1] - 1 for i in range(1, len(C))])
        series[nm] = tuple([d[k][d['idx'][x]] for x in cal] for k in ('O', 'H', 'L', 'C'))
    for nm in cands:
        dts, O, H, L, C = daily_from_5min(nm)
        R[nm] = rets_on(cal, dts, C)
        series[nm] = (O, H, L, C)

    factor = np.nanmean([R[n] for n in AI], axis=0)
    bookavg = np.nanmean([R[n] for n in book], axis=0)

    def fin(a, b):
        m = ~(np.isnan(a) | np.isnan(b))
        return a[m], b[m]

    print(f'G1 — classification (gate: AI-related names face 50%, uncorrelated 30%)\n')
    print(f'  {"name":6s}{"AI beta":>9s}{"corr AI":>9s}{"corr book":>11s}{"sessions":>10s}'
          f'{"range%":>9s}{"|move|%":>9s}{"dip+rec":>9s}   class')
    rows = []
    for nm in cands + list(REFS):
        x, y = fin(factor, R[nm])
        beta = float(np.polyfit(x, y, 1)[0])
        ca = float(np.corrcoef(x, y)[0, 1])
        xb, yb = fin(bookavg, R[nm])
        cb = float(np.corrcoef(xb, yb)[0, 1])
        O, H, L, C = series[nm]
        n = len(C)
        rng = float(np.mean([(H[i] - L[i]) / C[i] for i in range(n)]))
        absm = float(np.nanmean(np.abs(R[nm])))
        _, hit = dip_recover(O, H, L, C)
        cls = 'uncorrelated (30%)' if (beta < 0.25 and cb < 0.30) else 'AI-related (50%)'
        tag = nm if nm in cands else f'[{nm}]'
        rows.append((nm, beta, ca, cb, rng, absm, hit, cls))
        print(f'  {tag:6s}{beta:>9.2f}{ca:>9.2f}{cb:>11.2f}{n:>10d}{rng*100:>9.2f}'
              f'{absm*100:>9.2f}{hit*100:>9.1f}   {cls if nm in cands else "incumbent"}')
    print('\n  [CF] [GM] [VLO] are the incumbent diversifiers, for scale.')
    print('  Recorded for reference: LEN 0.09/0.15 uncorrelated; NEM 0.27/0.31 AI-related.')


if __name__ == '__main__':
    main()
