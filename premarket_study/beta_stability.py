"""
beta_stability.py — is the AI-factor beta a real relationship or an artefact?
(user challenge, 8 Oct 2026)

User: "What basis do you have for calling NEM AI-related? Is it strong enough?"

NEM is a gold miner. §3.14 classified it AI-related on an estimated beta of
0.27 and grouped it with FCX (0.49) and UAL (0.43) — but 0.27 is much nearer
GM's 0.18, and GM sits IN the book as a diversifier. The §3.14 note even
registers the oddity ("copper, airlines, even gold miners"). A classification
that decides which gate a name faces should be tested, not assumed, so:

  - the standard error and 95% interval on the full-sample beta
  - beta estimated separately on each half (the house blade)
  - rolling 120-session beta: how far it travels
  - beta with the 5% largest factor-move days removed — a beta that lives
    entirely in common shocks is risk-off co-movement, which every equity
    shares, not exposure to the AI trade

Incumbent diversifiers are shown alongside: if NEM's beta is no better
determined than GM's or VLO's, it cannot carry a different gate from theirs.

Usage: BAYES_WORKBOOK=<workbook.xlsx> python beta_stability.py [TICKER ...]
"""
import datetime as dt
import json
import sys

import numpy as np

from baseline_check import load
from fresh_opt_cands import daily_from_5min

OUT = 'beta_stability.json'
AI = ('TSM', 'VRT', 'VST', 'AVGO', 'MU', 'MRVL')
SPLIT = dt.date(2025, 5, 23)
WIN = 120


def ols(x, y):
    """slope, its standard error, and R^2."""
    n = len(x)
    xm, ym = x.mean(), y.mean()
    sxx = ((x - xm) ** 2).sum()
    b = ((x - xm) * (y - ym)).sum() / sxx
    a = ym - b * xm
    resid = y - (a + b * x)
    s2 = (resid ** 2).sum() / (n - 2)
    se = np.sqrt(s2 / sxx)
    ss_tot = ((y - ym) ** 2).sum()
    return b, se, 1 - (resid ** 2).sum() / ss_tot


def main():
    cands = [c.upper() for c in sys.argv[1:]] or ['NEM', 'RTX', 'DE', 'LEN', 'NOC', 'STNG']
    data, sleeves, cal, _ = load()
    book = sorted(data)

    R = {}
    for nm in book:
        d = data[nm]
        C = [d['C'][d['idx'][x]] for x in cal]
        R[nm] = np.array([np.nan] + [C[i] / C[i - 1] - 1 for i in range(1, len(C))])
    for nm in cands:
        if nm in R:
            continue
        dts, O, H, L, C = daily_from_5min(nm)
        idx = {d: i for i, d in enumerate(dts)}
        R[nm] = np.array([np.nan] + [
            (C[idx[d]] / C[idx[d] - 1] - 1) if (d in idx and idx[d] > 0) else np.nan
            for d in cal[1:]])

    factor = np.nanmean([R[n] for n in AI], axis=0)
    dates = np.array(cal)

    print(f'AI-factor beta, {cal[0]} to {cal[-1]}; incumbents in [brackets]\n')
    print(f'  {"name":6s}{"beta":>7s}{"s.e.":>7s}{"95% interval":>16s}{"R2":>7s}'
          f'{"train":>8s}{"test":>8s}{"roll min":>10s}{"roll max":>10s}{"ex-shock":>10s}')
    res = {}
    for nm in cands + ['GM', 'VLO', 'CF']:
        m = ~(np.isnan(factor) | np.isnan(R[nm]))
        x, y, d = factor[m], R[nm][m], dates[m]
        b, se, r2 = ols(x, y)
        lo, hi = b - 1.96 * se, b + 1.96 * se
        tr = d < SPLIT
        b_tr = ols(x[tr], y[tr])[0]
        b_te = ols(x[~tr], y[~tr])[0]
        roll = [ols(x[i:i + WIN], y[i:i + WIN])[0] for i in range(0, len(x) - WIN, 10)]
        # drop the 5% largest absolute factor moves: common shocks
        cut = np.quantile(np.abs(x), 0.95)
        keep = np.abs(x) < cut
        b_ex = ols(x[keep], y[keep])[0]
        tag = nm if nm in cands else f'[{nm}]'
        res[nm] = dict(beta=b, se=se, ci=[lo, hi], r2=r2, train=b_tr, test=b_te,
                       roll_min=min(roll), roll_max=max(roll), ex_shock=b_ex)
        print(f'  {tag:6s}{b:>7.2f}{se:>7.3f}{f"{lo:+.2f} to {hi:+.2f}":>16s}{r2:>7.3f}'
              f'{b_tr:>8.2f}{b_te:>8.2f}{min(roll):>10.2f}{max(roll):>10.2f}{b_ex:>10.2f}')

    print(f'\n  roll = {WIN}-session windows stepped by 10; ex-shock drops the 5% '
          f'largest |factor| days.')
    print(f'  R2 is the share of the name\'s daily variance the AI factor explains.')

    with open(OUT, 'w') as f:
        json.dump(res, f, indent=1, default=str)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
