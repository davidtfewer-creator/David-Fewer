"""
Does the diversification benefit survive without daily rebalancing?

The marginal test in newdiv.py builds each six-name book by averaging the names' DAILY returns and
compounding, which is equal weight rebalanced every day. That is how the five-name benchmark was
built too, so the comparison is internally consistent -- but it is not how the book runs. Each
sleeve owns its capital and compounds it independently; nothing sweeps a winner's profit back into
a laggard overnight.

That distinction is not cosmetic. Rebalancing across weakly correlated series earns a variance
bonus, and with correlations of 0.01 to 0.30 the bonus here could be most of the effect. If it is,
then "free risk reduction" is really "risk reduction, paid for by a rebalancing discipline the
book does not have".

So both constructions are computed over the tested half:

    rebalanced   equal weight restored every day
    held         one sixth of capital to each name at the start, compounding independently

with the candidates on their frozen first-half parameters throughout. No fitting happens here.
"""
import copy
import datetime
import math
import statistics

from engine import run_model
from optimise_candidates import mp
from newdiv import (BOOK, BUF_RESID, CAND, CUT, SEED, book_curves, daily_from_5min,
                    daily_returns, stats)
import five_min

FROZEN = {
    'GM':   [0.2011, 0.2907, 0.04228, 0.3827, 0.005803, 0.03368, 0.6041, 0.009885, 0.09131, 41.42],
    'VLO':  [1.441, 0.7016, 0.02011, 0.945, 0.02321, 0.05922, 1.799, 0.02552, 0.08021, 116.7],
    'CF':   [0.8737, 0.4777, 0.004598, 1.838, 0.02545, 0.06327, 0.8036, 0.05159, 0.09228, 65.56],
    'ALNY': [0.7795, 0.1431, 0.02285, 1.266, 0.03147, 0.006668, 2.009, 0.04964, 0.03783, 130.9],
}


def cand_curve(t):
    dts, O, H, L, C = daily_from_5min(t)
    tmpl = copy.copy(SEED)
    tmpl.years = (dts[-1]-dts[0]).days/365.25
    chk = five_min.make_checker(t, dts, O)[0]
    eq = run_model(dts, O, H, L, C, mp(FROZEN[t], tmpl), collect=True,
                   same_day_exit=chk, ou_sigma='resid').frames['equity']
    return dts, eq


def rebalanced(curves):
    rets = [daily_returns(d, e) for d, e in curves]
    dates = [d for d in sorted(set().union(*[set(r) for r in rets])) if d >= CUT]
    eq, v = [1.0], 1.0
    for d in dates:
        vals = [r[d] for r in rets if d in r]
        v *= (1 + (statistics.mean(vals) if vals else 0.0))
        eq.append(v)
    return dates, eq


def held(curves):
    """One share of capital each at the cut, compounding independently thereafter."""
    rets = [daily_returns(d, e) for d, e in curves]
    dates = [d for d in sorted(set().union(*[set(r) for r in rets])) if d >= CUT]
    n = len(curves)
    pots = [1.0/n]*n
    eq = [1.0]
    for d in dates:
        for j, r in enumerate(rets):
            if d in r:
                pots[j] *= (1 + r[d])
        eq.append(sum(pots))
    return dates, eq


def ann(eq, dates):
    y = max((dates[-1]-dates[0]).days/365.25, 1e-6)
    return ((eq[-1]/eq[0])**(1/y) - 1)*100


if __name__ == '__main__':
    bc = book_curves()
    base = [bc[s] for s in BOOK]
    cc = {t: cand_curve(t) for t in CAND}

    print(f'tested half only, from {CUT}; candidates on frozen first-half parameters\n',
          flush=True)
    print(f'{"book":16s}{"REBALANCED daily":>28s}{"HELD, no rebalancing":>32s}', flush=True)
    print(f'{"":16s}{"return":>10s}{"DD":>8s}{"Sharpe":>9s}'
          f'{"return":>12s}{"DD":>8s}{"Sharpe":>9s}{"reb bonus":>12s}', flush=True)
    print('-'*77, flush=True)

    rows = [('five names', base)] + [(f'+ {t}', base + [cc[t]]) for t in CAND]
    ref = {}
    for label, curves in rows:
        dr, er = rebalanced(curves)
        dh, eh = held(curves)
        ar, ah = ann(er, dr), ann(eh, dh)
        ddr, shr = stats(er, 0, len(er)-1)
        ddh, shh = stats(eh, 0, len(eh)-1)
        if label == 'five names':
            ref = dict(ar=ar, ah=ah, ddr=ddr, ddh=ddh, shr=shr, shh=shh)
        print(f'{label:16s}{ar:>9.1f}%{ddr:>7.1f}%{shr:>9.2f}'
              f'{ah:>11.1f}%{ddh:>7.1f}%{shh:>9.2f}{ar-ah:>+11.1f}pp', flush=True)

    print('-'*77, flush=True)
    print('\nagainst the five-name book, on the HELD construction that matches how the book '
          'actually runs:', flush=True)
    for t in CAND:
        dh, eh = held(base + [cc[t]])
        ah = ann(eh, dh)
        ddh, shh = stats(eh, 0, len(eh)-1)
        print(f'  + {t:5s} return {ah-ref["ah"]:+6.1f}pp   drawdown '
              f'{ddh-ref["ddh"]:+6.1f}pp   Sharpe {shh-ref["shh"]:+5.2f}', flush=True)
    print('DONE', flush=True)
