"""
Like-for-like head-to-head: old heuristic vs Bayes+OU, both refit on the first half only.

The heuristic_fixed.py comparison had an asymmetry: the heuristic was fitted on the first
half (honest OOS) while the incumbent's deployed parameters are full-sample fits that saw
the tested half. Here BOTH methods get the identical protocol:

    fit on [0:cut] (2025-05-23 boundary), robust objective (0.5·base + 0.5·mean of ±3%
    on the policy parameters), min-trade floor, differential evolution, at-open fill basis,
    residual OU sigma; freeze; score [cut:N-1] annualised, at-open.

Three columns per name: heuristic (frozen first-half fit), Bayes+OU refit-on-train, and
the deployed full-sample Bayes+OU for reference (carries lookahead into the test window —
quoted, not competed). Per §3.1 the refit column is expected to sit below deployed; the
like-for-like question is heuristic-vs-refit, same data diet.
"""
import copy, json, sys

from scipy.optimize import differential_evolution

from engine import Params, run_model
from heuristic_fixed import load, seg_ann, hseg, CUT, NAMES

BO_NAMES = ['lam', 'phi_L', 'psi', 'k', 'premium', 'peak_cap',
            'ou_buf_k', 'ou_prem', 'ou_cap', 'ou_W']
BO_BOUNDS = [(0.2, 1.6), (0.1, 1.0), (0.001, 0.1), (0.3, 3.0), (0.005, 0.05),
             (0.002, 0.07), (0.1, 2.5), (0.008, 0.06), (0.005, 0.12), (30, 150)]
POLICY = [3, 4, 5, 6, 7, 8]
PERTURB = [0.97, 1.03]

# frozen first-half heuristic fits from heuristic_fixed.py (w, a, rho, prem, cap)
HEUR = {
    'TSM':  [0.9557, 1.0440, 7.2990, 0.0400, 0.0278],
    'VRT':  [0.8010, 1.0291, 3.4803, 0.0271, 0.0498],
    'VST':  [0.8766, 1.0644, 0.8708, 0.0477, 0.0552],
    'RKLB': [0.9148, 0.9797, -2.9644, 0.0490, 0.0469],
    'MU':   [1.0674, 1.0579, -29.9616, 0.0324, 0.0331],
    'GM':   [1.0845, 1.0008, 4.0926, 0.0098, 0.0463],
    'VLO':  [1.0050, 0.8594, 8.0132, 0.0287, 0.0380],
    'CF':   [1.0142, 0.9982, -28.9377, 0.0465, 0.0166],
    'MRVL': [1.0467, 1.0981, -26.5767, 0.0186, 0.0116],
}


def mp(vec, t: Params):
    return Params(lam=vec[0], phi_L=vec[1], psi=vec[2], k=vec[3], premium=vec[4],
                  peak_cap=vec[5], ou_buf_k=vec[6], ou_prem=vec[7], ou_cap=vec[8],
                  ou_W=int(round(vec[9])), comm=t.comm, capital=t.capital,
                  interest=t.interest, stop_days=t.stop_days, bayes_pct=t.bayes_pct,
                  years=t.years)


def bo_run(data, vec_or_p, sd='at_open'):
    dts, O, H, L, C, p = data
    q = vec_or_p if isinstance(vec_or_p, Params) else mp(vec_or_p, p)
    return run_model(dts, O, H, L, C, q, ou_sigma='resid', collect=True, same_day_exit=sd)


def bo_seg(data, vec_or_p, lo, hi, sd='at_open'):
    r = bo_run(data, vec_or_p, sd)
    fr = r.frames
    eq = fr['equity']
    buys = sum(fr['t1']['Z'][lo:hi + 1]) + sum(fr['t2']['Z'][lo:hi + 1])
    return (eq[hi] / eq[lo] - 1.0 if eq[lo] > 0 else -1.0), buys, eq


def bo_robust(data, vec, lo, hi, floor):
    def one(v):
        rr, b, _ = bo_seg(data, v, lo, hi)
        return -5.0 + b * 1e-3 if b < floor else rr
    base = one(vec)
    s = []
    for i in POLICY:
        for f in PERTURB:
            v = list(vec)
            v[i] = min(max(v[i] * f, BO_BOUNDS[i][0]), BO_BOUNDS[i][1])
            s.append(one(v))
    return 0.5 * base + 0.5 * sum(s) / len(s)


def bo_optimise(data, lo, hi, floor, maxiter=8, popsize=8, seed=42):
    dts, O, H, L, C, p = data
    x0 = [p.lam, p.phi_L, p.psi, p.k, p.premium, p.peak_cap,
          p.ou_buf_k, p.ou_prem, p.ou_cap, p.ou_W]
    x0 = [min(max(x0[i], BO_BOUNDS[i][0]), BO_BOUNDS[i][1]) for i in range(10)]
    neg = lambda v: -bo_robust(data, v, lo, hi, floor)
    res = differential_evolution(neg, BO_BOUNDS, x0=x0, init='sobol', seed=seed,
                                 maxiter=maxiter, popsize=popsize, mutation=(0.5, 1.0),
                                 recombination=0.7, tol=1e-4, polish=False, disp=False,
                                 updating='immediate', workers=1)
    return list(res.x)


def run_stock(stock):
    data = load(stock)
    dts = data[0]
    N = len(dts)
    cut = next(i for i, d in enumerate(dts) if d >= CUT)

    _, tr_buys, _ = bo_seg(data, data[5], 0, cut)
    floor = max(8, int(0.4 * tr_buys))
    theta = bo_optimise(data, 0, cut, floor)

    h_te = seg_ann(hseg(data, HEUR[stock], cut, N - 1, 'at_open')[2].frames['equity'],
                   dts, cut, N - 1)
    _, _, eq_re = bo_seg(data, theta, cut, N - 1)
    re_te = seg_ann(eq_re, dts, cut, N - 1)
    _, _, eq_dep = bo_seg(data, data[5], cut, N - 1)
    dep_te = seg_ann(eq_dep, dts, cut, N - 1)

    print(f'{stock:6s} heur {h_te * 100:>7.1f}%   BO-refit {re_te * 100:>7.1f}%   '
          f'BO-deployed {dep_te * 100:>7.1f}%   floor {floor}', flush=True)
    print(f'       refit params: ' + ', '.join(
        f'{n}={theta[i]:.4f}' if i < 9 else f'{n}={int(round(theta[i]))}'
        for i, n in enumerate(BO_NAMES)), flush=True)
    return dict(stock=stock, heur=h_te, refit=re_te, deployed=dep_te, theta=theta)


if __name__ == '__main__':
    only = sys.argv[1:] or NAMES
    print('tested half, annualised, at-open basis, residual OU sigma\n', flush=True)
    rows = [run_stock(s) for s in only]
    print('\n===== LIKE-FOR-LIKE SUMMARY (both methods fit on first half only) =====', flush=True)
    hw = sum(1 for r in rows if r['heur'] > r['refit'])
    print(f'{"stock":6s}{"heuristic":>11s}{"BO refit":>10s}{"delta":>9s}{"BO deployed*":>14s}', flush=True)
    for r in rows:
        print(f'{r["stock"]:6s}{r["heur"] * 100:>10.1f}%{r["refit"] * 100:>9.1f}%'
              f'{(r["heur"] - r["refit"]) * 100:>+8.1f}{r["deployed"] * 100:>13.1f}%', flush=True)
    n = len(rows)
    print(f'\nheuristic wins {hw}/{n}; means: heur '
          f'{sum(r["heur"] for r in rows) / n * 100:.1f}%  BO refit '
          f'{sum(r["refit"] for r in rows) / n * 100:.1f}%  BO deployed '
          f'{sum(r["deployed"] for r in rows) / n * 100:.1f}%', flush=True)
    print('* deployed = full-sample fit, saw the test window; reference only', flush=True)
    with open('heur_symmetric_out.json', 'w') as f:
        json.dump(rows, f, indent=1)
