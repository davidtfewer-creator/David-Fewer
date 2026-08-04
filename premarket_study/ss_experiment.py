"""
Schwartz-Smith: third sleeve, replacement, or neither -- and what it does with the laggards.

All three sleeves run through the same simplified execution harness, so cross-sleeve comparisons
are valid. Absolute levels differ from the deployed engine (the harness is a replica, not the
engine itself) and must NOT be compared with the figures in the specification.
"""
import statistics, sys
import numpy as np
from ss_sleeve import (DATA, PARAMS, BOOK, LAGGARDS, CUT, KGRID, bids, sleeve_run, ann,
                       blend, rets, corr)


def fit_k(s, prem):
    best = None
    for k in KGRID:
        b = bids(s, 'ss', k)
        eq, t = sleeve_run(s, b, prem)
        if t < 8: continue
        a = ann(eq, DATA[s][0], 0, len(eq)-1)
        if best is None or a > best[0]: best = (a, k)
    return best[1] if best else 1.0


def analyse(names, label):
    print(f'\n{"="*94}\n{label}\n{"="*94}', flush=True)
    print(f'{"stock":7s}{"k":>5s}{"Bayes":>8s}{"OU":>8s}{"SS":>8s} | '
          f'{"B+O":>7s}{"B+O+SS":>9s}{"B+SS":>7s} | {"r(B,O)":>8s}{"r(B,SS)":>9s}{"r(O,SS)":>9s}',
          flush=True)
    print('-'*94, flush=True)
    agg = {kk: [] for kk in ('B', 'O', 'S', 'BO', 'BOS', 'BS')}
    cc = {kk: [] for kk in ('BO', 'BS', 'OS')}
    halves = {}
    for s in names:
        dts = DATA[s][0]; prem = PARAMS[s].premium
        k = fit_k(s, prem)
        eB, _ = sleeve_run(s, bids(s, 'bayes'), prem)
        eO, _ = sleeve_run(s, bids(s, 'ou'), prem)
        eS, _ = sleeve_run(s, bids(s, 'ss', k), prem)
        cur = {'B': eB, 'O': eO, 'S': eS,
               'BO': blend([eB, eO]), 'BOS': blend([eB, eO, eS]), 'BS': blend([eB, eS])}
        n = len(dts)-1
        vals = {kk: ann(v, dts, 0, n) for kk, v in cur.items()}
        for kk in agg: agg[kk].append(vals[kk])
        rB, rO, rS = rets(eB), rets(eO), rets(eS)
        c = dict(BO=corr(rB, rO), BS=corr(rB, rS), OS=corr(rO, rS))
        for kk in cc: cc[kk].append(c[kk])
        j = next(i for i, d in enumerate(dts) if d >= CUT)
        halves[s] = {kk: (ann(v, dts, 0, j), ann(v, dts, j, n)) for kk, v in cur.items()}
        print(f'{s:7s}{k:>5.1f}{vals["B"]:>7.0f}%{vals["O"]:>7.0f}%{vals["S"]:>7.0f}% | '
              f'{vals["BO"]:>6.0f}%{vals["BOS"]:>8.0f}%{vals["BS"]:>6.0f}% | '
              f'{c["BO"]:>8.2f}{c["BS"]:>9.2f}{c["OS"]:>9.2f}', flush=True)
    print('-'*94, flush=True)
    print(f'{"mean":7s}{"":5s}{statistics.mean(agg["B"]):>7.0f}%{statistics.mean(agg["O"]):>7.0f}%'
          f'{statistics.mean(agg["S"]):>7.0f}% | {statistics.mean(agg["BO"]):>6.0f}%'
          f'{statistics.mean(agg["BOS"]):>8.0f}%{statistics.mean(agg["BS"]):>6.0f}% | '
          f'{statistics.mean(cc["BO"]):>8.2f}{statistics.mean(cc["BS"]):>9.2f}'
          f'{statistics.mean(cc["OS"]):>9.2f}', flush=True)

    print(f'\nhalf-sample (first / TESTED), key configurations', flush=True)
    print(f'{"stock":7s}{"B+O (deployed)":>22s}{"B+O+SS":>22s}{"SS alone":>22s}', flush=True)
    for s in names:
        h = halves[s]
        f = lambda kk: f'{h[kk][0]:6.0f}% /{h[kk][1]:7.0f}%'
        print(f'{s:7s}{f("BO"):>22s}{f("BOS"):>22s}{f("S"):>22s}', flush=True)
    mt = lambda kk: statistics.mean(halves[s][kk][1] for s in names)
    print(f'{"mean tested":7s}{mt("BO"):>21.0f}%{mt("BOS"):>21.0f}%{mt("S"):>21.0f}%', flush=True)
    return agg, cc


if __name__ == '__main__':
    analyse(BOOK, 'QUESTION 1 --- the five book names')
    analyse(LAGGARDS, 'QUESTION 2 --- the four rejected laggards')
    print('\nDONE', flush=True)
