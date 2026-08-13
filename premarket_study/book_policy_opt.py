"""
Book-policy optimisation on the free-sleeve simulator.

Name-level vectors are FROZEN (the three-instrument verdict stands); what is
searched is book-level policy only, ~10 dimensions:

  w_1..w_8   relative per-name weights in the morning free-sleeve renormalisation
             (deployed: equal)
  eps        the ATH target guard, snapped to a grid {none, 0, 0.5%, 1%, 1.5%, 2%}
             (deployed: none)
  cap        max fraction of the morning pool one sleeve may take, cap/16
             (deployed: uncapped)

The MU P3 earnings pause is adopted (both halves, both bases) and fixed ON in
every configuration including the baseline.

Objective on the fitting window: annualised return - 0.5 * max drawdown.
Protocol: fit on one half, freeze, score the other half -- run in BOTH
directions. Policy is adoptable only where the two directions agree and each
improves its unseen half; otherwise equal weights stand.
"""
import datetime

import numpy as np
from scipy.optimize import differential_evolution

from book_sim import NAMES, load_all, simulate
from earnings_pause import EARNINGS, pause_dates
from fresh_opt import SPLIT

EPS_GRID = [None, 0.0, 0.005, 0.01, 0.015, 0.02]
BOUNDS = [(0.4, 2.5)] * 8 + [(0, 5.49), (1.0, 8.0)]

mu_e = [datetime.date.fromisoformat(x) for x in EARNINGS['MU']]
NO_BUY = {'MU': pause_dates(mu_e, 3)}


def build_datasets():
    """Bid series per guard-eps, computed once."""
    out = {}
    for k, eps in enumerate(EPS_GRID):
        ek = {} if eps is None else {s: dict(ath_target_guard=eps) for s in NAMES}
        out[k] = load_all(ek)
    return out


def run_policy(ds, vec, lo=None, hi=None):
    w = {NAMES[i]: vec[i] for i in range(8)}
    k = int(round(vec[8]))
    cap = vec[9] / 16.0 if vec[9] < 7.5 else None
    data, sleeves, cal = ds[k]
    return simulate(data, sleeves, cal, mode='pooled', no_buy=NO_BUY,
                    weights=w, cap_frac=cap, date_lo=lo, date_hi=hi)


def objective(r):
    return r['full'] - 0.5 * r['maxdd']     # 'full' of the restricted window


def fit(ds, lo, hi, seed=42):
    def neg(vec):
        return -objective(run_policy(ds, vec, lo, hi))
    res = differential_evolution(neg, BOUNDS, init='sobol', seed=seed, maxiter=10,
                                 popsize=10, mutation=(0.5, 1.0), recombination=0.7,
                                 tol=1e-4, polish=False, updating='immediate',
                                 workers=1)
    return list(res.x)


def show(vec):
    w = np.array(vec[:8])
    w = w / w.sum()
    k = int(round(vec[8]))
    cap = f'{vec[9]/16*100:.1f}%' if vec[9] < 7.5 else 'uncapped'
    parts = ', '.join(f'{NAMES[i]} {w[i]*100:.0f}%' for i in range(8))
    eps = 'none' if EPS_GRID[k] is None else f'{EPS_GRID[k]*100:.1f}%'
    return f'weights [{parts}]  guard {eps}  sleeve cap {cap}'


def main():
    print('precomputing bid series for the guard grid...', flush=True)
    ds = build_datasets()
    data, sleeves, cal = ds[0]
    split = next(d for d in cal if d >= SPLIT)
    day_before = max(d for d in cal if d < split)

    base_vec = [1.0] * 8 + [0.0, 8.0]     # equal weights, no guard, uncapped
    for label, lo, hi in [('half 1', None, day_before), ('half 2', split, None)]:
        r = run_policy(ds, base_vec, lo, hi)
        print(f'baseline policy on {label}: ann {r["full"]*100:6.1f}%  '
              f'DD {r["maxdd"]*100:4.1f}%', flush=True)

    for fit_label, flo, fhi, slo, shi in [
            ('fit H1 -> score H2', None, day_before, split, None),
            ('fit H2 -> score H1', split, None, None, day_before)]:
        vec = fit(ds, flo, fhi)
        rf = run_policy(ds, vec, flo, fhi)
        rs = run_policy(ds, vec, slo, shi)
        rb = run_policy(ds, base_vec, slo, shi)
        print(f'\n{fit_label}', flush=True)
        print('  fitted policy:', show(vec), flush=True)
        print(f'  fitted half : ann {rf["full"]*100:6.1f}%  DD {rf["maxdd"]*100:4.1f}%',
              flush=True)
        print(f'  UNSEEN half : ann {rs["full"]*100:6.1f}%  DD {rs["maxdd"]*100:4.1f}%'
              f'   vs baseline {rb["full"]*100:6.1f}% / {rb["maxdd"]*100:4.1f}%',
              flush=True)


if __name__ == '__main__':
    main()
