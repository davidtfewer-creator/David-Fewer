"""
Is a different ALGORITHM the lever, or is it the names?

Before building anything, two questions decide whether a second algorithm on
different names is worth the effort:

  1. Is there short-horizon MEAN REVERSION in the uncorrelated names at all?
     If a name trends, no entry rule monetises a dip, and Schwartz-Smith -- whose
     whole structure is a transient deviation around a stochastic equilibrium --
     has nothing to lock onto. Measured model-free with a variance ratio:
     VR(k) = Var(k-day return)/(k * Var(1-day return)). VR < 1 is reversion,
     VR > 1 is trending, VR = 1 is a random walk. Significance by PERMUTATION
     (shuffle the return series, recompute, 400 draws), which assumes nothing
     about the distribution.

  2. Is the CURRENT ENTRY RULE what stops us? The deployed bid is
     min(fair - k*sigma, Open, ATH*(1-peak_cap)). The ATH cap only buys below a
     running high, which in a range-bound name can be almost never. If a name
     reverts (question 1) but the model rarely fills, the entry rule is the
     binding constraint and a different one is worth building. If it reverts and
     fills often, the model is already harvesting what is there and a new
     algorithm is unlikely to add much.

Read together: REVERTS + RARELY FILLS is the case for a second algorithm.
REVERTS + FILLS OFTEN means the edge is already taken. NO REVERSION means the
name is hopeless whatever the algorithm, which is the result that would stop
this line of work cheaply.

Fitted vectors come from screen_speed.json (train-half frozen, §3.50), so the
fill statistics are out-of-sample in the parameters.

Usage:  python3 reversion_diag.py
"""
import json
import math
import os
import random
import statistics

from engine import run_model
from fresh_opt_cands import daily_from_5min
from live5_load import load as load_book
from minute_index import make_checker
from two_day import Clock

HORIZONS = (2, 5, 10)
DRAWS = 400
BOOK = ('TSM', 'VRT', 'VST', 'AVGO', 'MU')


def var_ratio(r, k):
    """Overlapping variance ratio. r = single-period log returns."""
    n = len(r)
    if n < k*3:
        return float('nan')
    mu = statistics.fmean(r)
    v1 = sum((x - mu)**2 for x in r)/(n - 1)
    s = [sum(r[i:i+k]) for i in range(n - k + 1)]
    mk = statistics.fmean(s)
    vk = sum((x - mk)**2 for x in s)/(len(s) - 1)
    return (vk/k)/v1 if v1 > 0 else float('nan')


def vr_pvalue(r, k, draws=DRAWS, seed=42):
    """Two-sided permutation p-value: shuffling destroys any serial structure."""
    obs = var_ratio(r, k)
    rng = random.Random(seed)
    w = list(r)
    hits = 0
    for _ in range(draws):
        rng.shuffle(w)
        if abs(var_ratio(w, k) - 1.0) >= abs(obs - 1.0):
            hits += 1
    return obs, (hits + 1)/(draws + 1)


def fill_profile(nm, vec):
    """How often does the deployed entry rule even place a reachable bid?"""
    c = Clock(nm, 1, 0)
    p = c.params(vec)
    fr = run_model(c.D, c.Ob, c.Hb, c.Lb, c.Cb, p, ou_sigma='resid',
                   same_day_exit=c.chk, collect=True).frames
    X, AM, L, H = fr['X'], fr['AM'], c.Lb, c.Hb
    ath, cap_binds, priced, reach, depth = 0.0, 0, 0, 0, []
    for i in range(c.N):
        ath = max(ath, H[i])
        b = X[i]
        if b is None:
            continue
        priced += 1
        if abs(b - ath*(1 - p.peak_cap)) < 1e-9:
            cap_binds += 1
        if L[i] <= b:
            reach += 1
        if i > 0 and c.Cb[i-1] > 0:
            depth.append(b/c.Cb[i-1] - 1)
    return dict(priced=priced, bars=c.N,
                cap_binds=cap_binds/max(priced, 1)*100,
                reach=reach/max(priced, 1)*100,
                med_depth=statistics.median(depth)*100 if depth else None)


def main():
    frozen = {r['name']: r['vec'] for r in json.load(open('screen_speed.json'))}
    book, bparams, _ = load_book()
    names = sorted(frozen) + [n for n in BOOK if n in book]
    print('variance ratio (VR<1 reverts, >1 trends; p by 400-draw permutation) '
          'and the deployed entry rule\n')
    print(f'{"name":6s}{"VR2":>8s}{"p":>7s}{"VR5":>8s}{"p":>7s}{"VR10":>8s}{"p":>7s}'
          f'{"bid priced":>12s}{"ATH cap":>9s}{"reached":>9s}{"bid depth":>11s}')
    out = []
    for nm in names:
        if nm in frozen:
            dts, O, H, L, C = daily_from_5min(nm)
            prof = fill_profile(nm, frozen[nm])
            tag = nm
        else:
            dts, O, H, L, C = book[nm]
            prof = None
            tag = f'[{nm}]'
        r = [math.log(C[i]/C[i-1]) for i in range(1, len(C)) if C[i-1] > 0]
        vrs = [vr_pvalue(r, k) for k in HORIZONS]
        row = dict(name=nm, in_book=nm in BOOK,
                   vr={str(k): dict(vr=v, p=pv) for k, (v, pv) in zip(HORIZONS, vrs)},
                   entry=prof)
        out.append(row)
        s = ''.join(f'{v:>8.2f}{pv:>7.3f}' for v, pv in vrs)
        if prof:
            s += (f'{prof["priced"]/prof["bars"]*100:>11.0f}%{prof["cap_binds"]:>8.0f}%'
                  f'{prof["reach"]:>8.1f}%{prof["med_depth"]:>10.2f}%')
        else:
            s += f'{"  (book name - deployed vector not refit here)":>43s}'
        print(f'{tag:6s}{s}', flush=True)
    with open('reversion_diag.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('\n  [NAME] = currently in the book, shown for scale.')
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
