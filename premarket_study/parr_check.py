"""
The two things that could kill PARR, before it goes anywhere near G5.

§3.53 found PARR clearing G1, G2 and G4 together -- the first name in this
project to do so -- and left two questions open.

A. IS IT ACTUALLY A DIVERSIFIER? A low AI beta is not a low BOOK correlation.
   PARR is a refiner and VLO, a refiner, is already in the book; §6 recorded
   VLO-CF at 0.41 and warned they are "one-and-a-bit names" rather than two.
   A third correlated energy name would be capacity, not diversification. This
   measures PARR against all nine book names, the book average, and the two
   incumbents it most resembles, on the book's own calendar.

B. WHY DOES AN ARBITRARY VECTOR BEAT THE FITTED ONE? On the unseen half the
   frozen train-half fit returned 46.1% while the neutral seed vector returned
   114.5%. Either the name is so favourable in this window that almost anything
   works -- in which case 46.1% is real but the fit is actively harmful -- or
   the train half points somewhere the test half does not reward, which would
   make the whole fitted number an accident.

   The test: draw vectors uniformly from the search bounds, score each on BOTH
   halves, and ask whether train performance predicts test performance at all.
   If the rank correlation is near zero the optimiser cannot work on this name
   and the planning figure is the DISTRIBUTION, not the fitted point. GM and CF
   run as controls -- GM is the only name that passed §3.50, CF is the book's
   zero-beta incumbent -- because a near-zero train-test link on all three would
   be a fact about the model, not about PARR.

Usage:  python3 parr_check.py [--draws 400]
"""
import json
import random
import statistics
import sys

import numpy as np

from fresh_opt_cands import daily_from_5min
from two_day import Clock, bounds_for, x0_vector

ROSTER = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'GM', 'VLO', 'CF', 'MRVL']
CONTROLS = ['GM', 'CF']


def rets(nm):
    dts, O, H, L, C = daily_from_5min(nm)
    return {d: C[i]/C[i-1] - 1 for i, d in enumerate(dts) if i > 0}


def part_a():
    print(f'{"="*78}\nA. IS PARR A DIVERSIFIER, OR A THIRD HELPING OF ENERGY?\n', flush=True)
    R = {n: rets(n) for n in ROSTER + ['PARR']}
    cal = sorted(set.intersection(*(set(r) for r in R.values())))
    V = {n: np.array([R[n][d] for d in cal]) for n in R}
    book = np.mean(np.vstack([V[n] for n in ROSTER]), axis=0)
    print(f'  {len(cal)} common sessions {cal[0]} .. {cal[-1]}\n')
    print(f'  PARR correlation to each book name:')
    out = {}
    for n in ROSTER:
        c = float(np.corrcoef(V['PARR'], V[n])[0, 1])
        out[n] = c
        print(f'    {n:6s}{c:>7.2f}', flush=True)
    cb = float(np.corrcoef(V['PARR'], book)[0, 1])
    out['book_avg'] = cb
    print(f'\n  PARR vs BOOK AVERAGE: {cb:.2f}   '
          f'(§3.32 bar for a diversifier: <= 0.30)', flush=True)
    print(f'\n  the energy cluster, pairwise:')
    for a, b in (('PARR', 'VLO'), ('PARR', 'CF'), ('VLO', 'CF')):
        c = float(np.corrcoef(V[a], V[b])[0, 1])
        out[f'{a}-{b}'] = c
        print(f'    {a:5s} vs {b:5s}{c:>7.2f}', flush=True)
    print(f'\n  for scale, the book\'s own average pairwise correlation:')
    ps = [float(np.corrcoef(V[a], V[b])[0, 1])
          for i, a in enumerate(ROSTER) for b in ROSTER[i+1:]]
    out['book_pairwise_mean'] = statistics.fmean(ps)
    print(f'    nine names, mean pairwise {statistics.fmean(ps):.2f}', flush=True)
    return out


def part_b(draws):
    print(f'\n{"="*78}\nB. DOES THE TRAIN HALF PREDICT THE TEST HALF?\n', flush=True)
    bnd = bounds_for(1)
    rng = random.Random(42)
    vecs = [[rng.uniform(lo, hi) for lo, hi in bnd] for _ in range(draws)]
    res = {}
    for nm in ['PARR'] + CONTROLS:
        c = Clock(nm, 1, 0)
        rows = []
        for v in vecs:
            rtr, btr = c.seg(v, 0, c.cut-1)
            rte, bte = c.seg(v, c.cut, c.N-1)
            if btr < 5 or bte < 5:          # degenerate: too few fills to mean anything
                continue
            rows.append((c.ann(rtr, 0, c.cut-1), c.ann(rte, c.cut, c.N-1)))
        tr = [a for a, _ in rows]
        te = [b for _, b in rows]
        # Spearman by hand: rank then Pearson
        def rank(x):
            order = sorted(range(len(x)), key=lambda i: x[i])
            r = [0.0]*len(x)
            for pos, i in enumerate(order):
                r[i] = pos
            return r
        rho = float(np.corrcoef(rank(tr), rank(te))[0, 1]) if len(rows) > 10 else float('nan')
        # where do the two known vectors sit?
        seed = x0_vector(1)
        r_s, _ = c.seg(seed, c.cut, c.N-1)
        a_seed = c.ann(r_s, c.cut, c.N-1)
        te_sorted = sorted(te)
        def pct(v):
            return sum(1 for x in te_sorted if x < v)/len(te_sorted)*100
        print(f'  {nm}: {len(rows)} of {draws} random vectors tradeable', flush=True)
        print(f'    test-half return  median {statistics.median(te):6.1f}%  '
              f'25th {te_sorted[len(te)//4]:6.1f}%  75th {te_sorted[3*len(te)//4]:6.1f}%  '
              f'max {max(te):6.1f}%', flush=True)
        print(f'    train->test rank correlation  {rho:+.2f}'
              f'   {"(fitting cannot work here)" if abs(rho) < 0.2 else ""}', flush=True)
        print(f'    seed vector scores {a_seed:6.1f}% on test = {pct(a_seed):3.0f}th percentile '
              f'of random vectors', flush=True)
        res[nm] = dict(n=len(rows), median_test=statistics.median(te),
                       q25=te_sorted[len(te)//4], q75=te_sorted[3*len(te)//4],
                       max_test=max(te), rho=rho, seed_test=a_seed,
                       seed_pct=pct(a_seed))
    return res


if __name__ == '__main__':
    draws = 400
    if '--draws' in sys.argv:
        draws = int(sys.argv[sys.argv.index('--draws')+1])
    a = part_a()
    b = part_b(draws)
    json.dump(dict(correlations=a, train_test=b), open('parr_check.json', 'w'), indent=1)
    print('\nDONE', flush=True)
