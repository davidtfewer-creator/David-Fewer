"""
Walk-forward on the eight-name book: RKLB, TSM, VST, VRT, MU + GM, VLO, CF.

The half-sample split said adding GM, VLO and CF costs about 14pp of return and roughly halves the
loss through an AI drawdown. That rested on one boundary and, in the stress test, largely on one
episode. This re-runs it as an expanding walk-forward so the claim has to hold on several unseen
windows rather than one.

Two design choices carry the result.

SYMMETRY. Every name is re-fitted on each training window, the five book names included. The
deployed book parameters were fitted on the whole sample, so scoring them on a test window would
let the incumbent see its own test data while the candidates were frozen from train -- an
asymmetry that flatters the five-name book, which is precisely the comparison at issue. The
deployed book is still reported per fold, clearly labelled, because it is what actually runs; it
just is not the number the comparison is decided on.

NO REBALANCING. Each book is built by giving every name an equal share of capital at the start of
the test window and letting each compound independently, which is how the sleeves actually work.
The earlier rebalanced construction was what made these names look free, and it was wrong.

Reported per fold: each book's return and drawdown on the unseen window, and the AI factor's own
return over the same window, so a fold where the theme rose and a fold where it fell can be told
apart. A diversifier is supposed to lose in the first and win in the second; if it loses in both,
it is just a worse book.
"""
import copy
import datetime
import math
import statistics
import sys

from engine import run_model
from optimise_candidates import NAMES, mp
from newdiv import (BOOK, BUF_RESID, CAND, SEED, daily_from_5min, daily_returns,
                    optimise, seg, stats)
import five_min

ADD = ['GM', 'VLO', 'CF']
AI = ['TSM', 'VRT', 'VST', 'MU']
ALL8 = BOOK + ADD
CUTS = (0.50, 0.667, 0.833, 1.0)          # three expanding folds, as used for the book


def load_all():
    from daily_window_split import data as bdata, params as bparams
    from mu_rerun import from_workbook
    from five_min import make_checker as fm
    bdata = dict(bdata)
    bdata['MU'] = from_workbook()
    data, chk, dep = {}, {}, {}
    for s in BOOK:
        data[s] = bdata[s]
        chk[s] = fm(s, bdata[s][0], bdata[s][1])[0]
        p = copy.copy(bparams[s])
        p.bayes_pct = 0.5
        p.ou_buf_k = BUF_RESID[s]
        dep[s] = p
    for t in ADD:
        data[t] = daily_from_5min(t)
        chk[t] = five_min.make_checker(t, data[t][0], data[t][1])[0]
    return data, chk, dep


def curve(d, vec_or_params, tmpl, sde):
    p = vec_or_params if hasattr(vec_or_params, 'lam') else mp(vec_or_params, tmpl)
    return run_model(d['dts'], d['O'], d['H'], d['L'], d['C'], p, collect=True,
                     same_day_exit=sde, ou_sigma='resid').frames['equity']


def held(curves, dts_list, lo_date, hi_date):
    """Equal capital per name at lo_date, each compounding independently."""
    rets = [daily_returns(dts_list[i], curves[i]) for i in range(len(curves))]
    dates = sorted(set().union(*[set(r) for r in rets]))
    dates = [x for x in dates if lo_date <= x <= hi_date]
    pots = [1.0/len(curves)]*len(curves)
    eq = [1.0]
    for x in dates:
        for j, r in enumerate(rets):
            if x in r:
                pots[j] *= (1 + r[x])
        eq.append(sum(pots))
    return dates, eq


def ann(eq, dates):
    y = max((dates[-1]-dates[0]).days/365.25, 1e-6)
    return ((eq[-1]/eq[0])**(1/y) - 1)*100


if __name__ == '__main__':
    data, chk, dep = load_all()

    # a common calendar, so folds line up across names with slightly different session sets
    cal = sorted(set(data['TSM'][0]))
    N = len(cal)
    cuts = [int(N*f) for f in CUTS]
    print(f'common calendar {cal[0]} to {cal[-1]}, {N} sessions', flush=True)
    print(f'folds: ' + '  '.join(f'{cal[cuts[j]]}..{cal[cuts[j+1]-1]}' for j in range(3)),
          flush=True)

    # AI factor from the underlying shares, for context on each window
    from mu_rerun import from_workbook
    from daily_window_split import data as bdata0
    bd = dict(bdata0)
    bd['MU'] = from_workbook()
    ur = {}
    for s in AI:
        dts, O, H, L, C = bd[s]
        ur[s] = {dts[i]: C[i]/C[i-1]-1 for i in range(1, len(C)) if C[i-1] > 0}
    fdates = sorted(set.intersection(*[set(ur[s]) for s in AI]))
    fac = {d: statistics.mean(ur[s][d] for s in AI) for d in fdates}

    rows = []
    for j in range(3):
        tr_hi = cuts[j]-1
        te_lo, te_hi = cuts[j], cuts[j+1]-1
        d0, d1 = cal[te_lo], cal[te_hi]
        print(f'\n{"="*80}\nFOLD {j+1}: train to {cal[tr_hi]}, test {d0} to {d1}\n{"="*80}',
              flush=True)

        fitted, curves5, curves8, dts5, dts8, dep5 = {}, [], [], [], [], []
        for s in ALL8:
            dts, O, H, L, C = data[s]
            d = dict(dts=dts, O=O, H=H, L=L, C=C)
            tmpl = copy.copy(SEED)
            tmpl.years = (dts[-1]-dts[0]).days/365.25
            # map the common-calendar cut onto this name's own index
            hi = max(i for i, x in enumerate(dts) if x <= cal[tr_hi])
            th = optimise(d, tmpl, 0, hi, max(8, int(0.03*hi)), chk[s])
            fitted[s] = th
            eq = curve(d, th, tmpl, chk[s])
            if s in BOOK:
                curves5.append(eq)
                dts5.append(dts)
                dep5.append(curve(d, dep[s], tmpl, chk[s]))
            curves8.append(eq)
            dts8.append(dts)
            lo = max(i for i, x in enumerate(dts) if x <= d0)
            hi2 = max(i for i, x in enumerate(dts) if x <= d1)
            print(f'  {s:5s} OOS {(eq[hi2]/eq[lo]-1)*100:>7.1f}%', flush=True)

        f5 = held(curves5, dts5, d0, d1)
        f8 = held(curves8, dts8, d0, d1)
        fd = held(dep5, dts5, d0, d1)
        aiw = 1.0
        for x in sorted(fac):
            if d0 <= x <= d1:
                aiw *= (1+fac[x])
        r5, r8, rd = ann(f5[1], f5[0]), ann(f8[1], f8[0]), ann(fd[1], fd[0])
        dd5 = stats(f5[1], 0, len(f5[1])-1)[0]
        dd8 = stats(f8[1], 0, len(f8[1])-1)[0]
        ddd = stats(fd[1], 0, len(fd[1])-1)[0]
        rows.append(dict(j=j+1, r5=r5, r8=r8, rd=rd, dd5=dd5, dd8=dd8, ddd=ddd,
                         ai=(aiw-1)*100, d0=d0, d1=d1))
        print(f'\n  AI factor over the window {(aiw-1)*100:+.1f}%', flush=True)
        print(f'  five-name  (refit)   {r5:>7.1f}%   max DD {dd5:>5.1f}%', flush=True)
        print(f'  eight-name (refit)   {r8:>7.1f}%   max DD {dd8:>5.1f}%', flush=True)
        print(f'  five-name  (deployed params, for reference) {rd:>7.1f}%   max DD {ddd:>5.1f}%',
              flush=True)

    print(f'\n{"="*80}\nSUMMARY -- all parameters fitted on train only, no rebalancing\n{"="*80}',
          flush=True)
    print(f'{"fold":6s}{"window":26s}{"AI":>8s}{"five":>9s}{"eight":>9s}{"delta":>9s}'
          f'{"DD five":>10s}{"DD eight":>10s}', flush=True)
    print('-'*87, flush=True)
    for r in rows:
        print(f'{r["j"]:<6d}{str(r["d0"])+" to "+str(r["d1"]):26s}{r["ai"]:>7.1f}%'
              f'{r["r5"]:>8.1f}%{r["r8"]:>8.1f}%{r["r8"]-r["r5"]:>+8.1f}'
              f'{r["dd5"]:>9.1f}%{r["dd8"]:>9.1f}%', flush=True)
    print('-'*87, flush=True)
    w = sum(1 for r in rows if r['r8'] > r['r5'])
    wd = sum(1 for r in rows if r['dd8'] < r['dd5'])
    print(f'  eight-name higher return in {w}/3 folds; mean '
          f'{statistics.mean(r["r8"]-r["r5"] for r in rows):+.1f}pp', flush=True)
    print(f'  eight-name lower drawdown in {wd}/3 folds; mean '
          f'{statistics.mean(r["dd8"]-r["dd5"] for r in rows):+.1f}pp', flush=True)
    print('\nparameters by fold:', flush=True)
    print('DONE', flush=True)
