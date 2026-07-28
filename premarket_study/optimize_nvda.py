"""
Walk-forward re-optimization for NVDA under the PM-VWAP open cap.

Question: the frozen params were tuned for the close-cap model. Does re-optimizing
for the VWAP-cap variant help OUT OF SAMPLE, or is it the usual in-sample mirage (§2)?

Protocol (faithful to §5 of the handoff):
  * objective  = annualized return on the TRAIN slice, min-trade floor, + neighbourhood
                 robustness (0.5*score + 0.5*mean over +/-3% perturbations)
  * optimizer  = differential evolution (Sobol init, frozen params seeded as incumbent),
                 over 9 continuous params + discrete OU window W (rounded inside objective)
  * evaluation = expanding-window walk-forward; score the UNSEEN test slice for
                 frozen-VWAP vs reopt-VWAP vs close-cap reference.

Return is scale-invariant (equity[end]/equity[start]-1), so scoring a slice of one
full-series run keeps Kalman/OU warmup and compounding state consistent.
"""
import numpy as np
from scipy.optimize import differential_evolution
from engine import Params, run_model
from experiment_nvda import load, prev_close_series

# param vector order and bounds (base value sits inside each bound)
NAMES  = ['lam','phi_L','psi','k','premium','peak_cap','ou_buf_k','ou_prem','ou_cap','ou_W']
BASE   = [0.604475,0.320751,0.007398,1.140966,0.017306,0.019635,0.907335,0.024772,0.056198,51]
BOUNDS = [(0.2,1.5),(0.1,1.0),(0.001,0.05),(0.3,3.0),(0.005,0.05),(0.002,0.06),
          (0.3,2.5),(0.008,0.06),(0.01,0.12),(20,90)]
PERTURB = [0.97, 1.03]  # +/-3% neighbourhood samples for robustness


def make_params(vec):
    v = list(vec)
    return Params(lam=v[0], phi_L=v[1], psi=v[2], k=v[3], premium=v[4], peak_cap=v[5],
                  ou_buf_k=v[6], ou_prem=v[7], ou_cap=v[8], ou_W=int(round(v[9])))


def seg_return(equity, lo, hi):
    if equity[lo] <= 0:
        return -1.0
    return equity[hi] / equity[lo] - 1.0


def seg_buys(frames, lo, hi):
    z = frames['t1']['Z']; g = frames['t2']['Z']
    return sum(z[lo:hi + 1]) + sum(g[lo:hi + 1])


def evaluate(data, vec, cap, lo, hi):
    """Run full series with params `vec` and cap series, return (seg_return, seg_buys)."""
    p = make_params(vec)
    r = run_model(data['dates'], data['O'], data['H'], data['L'], data['C'], p,
                  open_cap=cap, collect=True)
    return seg_return(r.frames['equity'], lo, hi), seg_buys(r.frames, lo, hi)


def robust_train_score(data, vec, cap, lo, hi, min_buys):
    def one(v):
        ret, buys = evaluate(data, v, cap, lo, hi)
        if buys < min_buys:                      # frequency-collapse guard (§3)
            return -5.0 + buys * 0.001
        return ret
    base = one(vec)
    # perturb only the continuous params (indices 0..8), not the discrete W
    samples = []
    for i in range(9):
        for f in PERTURB:
            v = list(vec); v[i] = v[i] * f
            lo_b, hi_b = BOUNDS[i]
            v[i] = min(max(v[i], lo_b), hi_b)
            samples.append(one(v))
    mean_pert = sum(samples) / len(samples)
    return 0.5 * base + 0.5 * mean_pert


def optimize(data, cap, lo, hi, min_buys, maxiter=15, popsize=8, seed=42):
    neg = lambda v: -robust_train_score(data, v, cap, lo, hi, min_buys)
    res = differential_evolution(
        neg, BOUNDS, x0=BASE, init='sobol', seed=seed,
        maxiter=maxiter, popsize=popsize, mutation=(0.5, 1.0), recombination=0.7,
        tol=1e-4, polish=False, disp=False, updating='immediate', workers=1)
    return res.x


if __name__ == '__main__':
    data = load('nvda_joined.csv')
    N = len(data['C'])
    prevC = prev_close_series(data['C'])
    pmV = data['pmV']

    # expanding-window walk-forward: 3 test folds over the back half of the sample
    cuts = [int(N * f) for f in (0.5, 0.667, 0.833, 1.0)]
    folds = [(0, cuts[i] - 1, cuts[i], cuts[i + 1] - 1) for i in range(3)]

    print(f'NVDA walk-forward re-optimization under PM-VWAP cap  (N={N})\n')
    print(f'{"fold":5s}{"train":>14s}{"test":>14s}'
          f'{"frozen+close":>15s}{"frozen+VWAP":>14s}{"reopt+VWAP":>13s}   winner')
    print('-' * 92)

    wins_reopt = 0
    for k, (tr_lo, tr_hi, te_lo, te_hi) in enumerate(folds, 1):
        # min-trade floor for the train window: 40% of frozen-param train buys
        _, base_train_buys = evaluate(data, BASE, pmV, tr_lo, tr_hi)
        floor = max(4, int(0.4 * base_train_buys))
        theta = optimize(data, pmV, tr_lo, tr_hi, floor)

        froz_close, _ = evaluate(data, BASE, prevC, te_lo, te_hi)
        froz_vwap,  _ = evaluate(data, BASE, pmV,  te_lo, te_hi)
        reopt_vwap, _ = evaluate(data, theta, pmV, te_lo, te_hi)
        win = 'reopt' if reopt_vwap > froz_vwap else 'frozen'
        if reopt_vwap > froz_vwap:
            wins_reopt += 1
        print(f'{k:<5d}[{tr_lo:>3d}:{tr_hi:<3d}]  [{te_lo:>3d}:{te_hi:<3d}]  '
              f'{froz_close*100:>13.1f}%{froz_vwap*100:>13.1f}%{reopt_vwap*100:>12.1f}%   {win}')
        # record last fold's params for inspection
        last_theta = theta

    print(f'\nReopt beats frozen (VWAP cap) out-of-sample in {wins_reopt}/3 folds.')
    print('\nLast-fold re-optimized params vs frozen (drift = optimum moved):')
    for nm, b, t in zip(NAMES, BASE, last_theta):
        t = int(round(t)) if nm == 'ou_W' else t
        drift = '' if nm == 'ou_W' else f'  ({(t/b-1)*100:+.0f}%)'
        print(f'  {nm:10s} frozen={b:<10.5g} reopt={t:<10.5g}{drift}')
