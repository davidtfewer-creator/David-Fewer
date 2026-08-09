"""
The fresh optimisation, from the top, one blade and no layers.

Basis: the uploaded live workbook (engine mirror-checked to the dollar), residual OU
sigma, and VERIFIED same-day fills — a same-day round trip is kept only where the
5-minute bars prove the low reached the bid before the high reached the target
(sessions without bar coverage fall back to the provable at-open case only).

Protocol (the one that decided the book): fit on the first half, boundary 2025-05-23,
freeze, score the second half. The deployed configuration is scored frozen on the same
test slice. Whatever wins on the tested half is the answer.

Two search variants, both smaller than the old 10-dim search:

  A "8-dim"  lam is FIXED at 1. The model is exactly invariant under
             (lam, phi_L, psi, k) -> (c*lam, c*phi_L, c*psi, k/c): gains depend only
             on noise ratios and the bid only on k*sigma. The old search carried a
             pure flat direction; this removes it with zero loss of expressiveness.
             ou_W is frozen at deployed (the one parameter that held still between
             halves). Searched: phi_L (log-scale), psi, k, premium, peak_cap,
             ou_buf_k, ou_prem, ou_cap.

  B "6-dim"  the filter (lam, phi_L, psi) is pinned at its maximum-likelihood
             estimate ON THE TRAIN HALF ONLY (prices identify it; P&L does not),
             ou_W frozen at deployed. Searched: the six policy knobs.

Objective: the established robust one — 0.5*base + 0.5*mean(+/-3% on the six policy
knobs), minimum-trade floor — computed on the VERIFIED train-segment return.
"""
import json
import math
import sys

import numpy as np
from scipy.optimize import differential_evolution

from engine import Params, run_model
from live5_load import load, STOCKS
from minute_index import make_checker
from rolling_mle import fit_window

SPLIT = __import__('datetime').date(2025, 5, 23)
PERTURB = [0.97, 1.03]

# variant A vector: [log_phi_L, psi, k, premium, peak_cap, ou_buf_k, ou_prem, ou_cap]
A_BOUNDS = [(math.log(0.2), math.log(10.0)), (0.0, 0.5), (0.05, 2.0),
            (0.005, 0.05), (0.002, 0.07), (0.1, 2.5), (0.008, 0.06), (0.005, 0.12)]
A_POLICY = [2, 3, 4, 5, 6, 7]
# variant B vector: [k, premium, peak_cap, ou_buf_k, ou_prem, ou_cap]
B_BOUNDS = [(0.05, 3.0), (0.005, 0.05), (0.002, 0.07),
            (0.1, 2.5), (0.008, 0.06), (0.005, 0.12)]
B_POLICY = [0, 1, 2, 3, 4, 5]


def a_params(vec, t):
    return Params(lam=1.0, phi_L=math.exp(vec[0]), psi=vec[1], k=vec[2],
                  premium=vec[3], peak_cap=vec[4], ou_buf_k=vec[5], ou_prem=vec[6],
                  ou_cap=vec[7], ou_W=t.ou_W, comm=t.comm, capital=t.capital,
                  interest=t.interest, stop_days=t.stop_days, bayes_pct=t.bayes_pct,
                  years=t.years)


def a_x0(t):
    # the deployed vector, re-expressed at lam=1 via the exact degeneracy
    return [math.log(min(max(t.phi_L / t.lam, 0.21), 9.9)),
            min(t.psi / t.lam, 0.5), t.k * t.lam, t.premium, t.peak_cap,
            t.ou_buf_k, t.ou_prem, t.ou_cap]


def b_params(vec, t, mle):
    return Params(lam=mle[0], phi_L=mle[1], psi=mle[2], k=vec[0], premium=vec[1],
                  peak_cap=vec[2], ou_buf_k=vec[3], ou_prem=vec[4], ou_cap=vec[5],
                  ou_W=t.ou_W, comm=t.comm, capital=t.capital, interest=t.interest,
                  stop_days=t.stop_days, bayes_pct=t.bayes_pct, years=t.years)


def seg(dts, O, H, L, C, p, chk, lo, hi):
    """Verified segment return over rows [lo, hi] on the combined equity, plus buys."""
    r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk, collect=True)
    eq = r.frames['equity']
    buys = (sum(r.frames['t1']['Z'][lo:hi + 1]) + sum(r.frames['t2']['Z'][lo:hi + 1]))
    ret = eq[hi] / eq[lo] - 1.0 if eq[lo] > 0 else -1.0
    return ret, buys


def make_objective(dts, O, H, L, C, t, chk, lo, hi, floor, mk_params, policy):
    def one(vec):
        ret, buys = seg(dts, O, H, L, C, mk_params(vec), chk, lo, hi)
        return -5.0 + buys * 1e-3 if buys < floor else ret

    def robust(vec):
        base = one(vec)
        s = []
        for i in policy:
            for f in PERTURB:
                v = list(vec)
                v[i] = v[i] * f
                s.append(one(v))
        return 0.5 * base + 0.5 * sum(s) / len(s)

    return lambda vec: -robust(vec)


def annualise(ret, dts, lo, hi):
    days = (dts[hi] - dts[lo]).days or 1
    return (1 + ret) ** (365.25 / days) - 1


def main(only=None):
    data, params, cached = load()
    results = {}
    for s in (only or STOCKS):
        dts, O, H, L, C = data[s]
        t = params[s]
        chk = make_checker(s, dts, O)
        N = len(C)
        cut = next(i for i, d in enumerate(dts) if d >= SPLIT)   # first test row
        trlo, trhi, telo, tehi = 0, cut - 1, cut, N - 1

        # deployed baseline, verified, on both halves
        ret_tr, buys_tr = seg(dts, O, H, L, C, t, chk, trlo, trhi)
        ret_te, buys_te = seg(dts, O, H, L, C, t, chk, telo, tehi)
        ret_full, buys_full = seg(dts, O, H, L, C, t, chk, 0, N - 1)
        print(f'\n===== {s} =====', flush=True)
        print(f'  deployed verified: full {annualise(ret_full, dts, 0, N-1)*100:6.1f}%/yr '
              f'({buys_full} buys) | train {annualise(ret_tr, dts, trlo, trhi)*100:6.1f}%/yr '
              f'| TEST {annualise(ret_te, dts, telo, tehi)*100:6.1f}%/yr ({buys_te} buys)',
              flush=True)
        res = dict(deployed=dict(
            full=annualise(ret_full, dts, 0, N - 1), test=annualise(ret_te, dts, telo, tehi),
            train=annualise(ret_tr, dts, trlo, trhi), buys_test=buys_te))

        floor = max(4, int(0.4 * buys_tr))

        # ---- variant A: 8-dim, lam = 1
        obj = make_objective(dts, O, H, L, C, t, chk, trlo, trhi, floor,
                             lambda v: a_params(v, t), A_POLICY)
        rA = differential_evolution(obj, A_BOUNDS, x0=a_x0(t), init='sobol', seed=42,
                                    maxiter=8, popsize=8, mutation=(0.5, 1.0),
                                    recombination=0.7, tol=1e-3, polish=False,
                                    updating='immediate', workers=1)
        pA = a_params(rA.x, t)
        a_tr, _ = seg(dts, O, H, L, C, pA, chk, trlo, trhi)
        a_te, a_b = seg(dts, O, H, L, C, pA, chk, telo, tehi)
        print(f'  A 8-dim   : train {annualise(a_tr, dts, trlo, trhi)*100:6.1f}%/yr '
              f'| TEST {annualise(a_te, dts, telo, tehi)*100:6.1f}%/yr ({a_b} buys)', flush=True)
        res['A'] = dict(train=annualise(a_tr, dts, trlo, trhi),
                        test=annualise(a_te, dts, telo, tehi), buys_test=a_b,
                        vec=list(rA.x))

        # ---- variant B: filter pinned at TRAIN-half MLE, 6 policy dims
        F = [H[i] - L[i] for i in range(N)]
        mle, _, _ = fit_window(np.array(C[:cut]), np.array(F[:cut]),
                               [np.array([0.1, 0.7, 0.005]),
                                np.array([t.lam, t.phi_L, max(t.psi, 1e-3)])])
        print(f'  B filter pinned at train-MLE lam/phi_L/psi = '
              f'{mle[0]:.3f}/{mle[1]:.3f}/{mle[2]:.4f}', flush=True)
        objB = make_objective(dts, O, H, L, C, t, chk, trlo, trhi, floor,
                              lambda v: b_params(v, t, mle), B_POLICY)
        x0B = [t.k, t.premium, t.peak_cap, t.ou_buf_k, t.ou_prem, t.ou_cap]
        rB = differential_evolution(objB, B_BOUNDS, x0=x0B, init='sobol', seed=42,
                                    maxiter=8, popsize=8, mutation=(0.5, 1.0),
                                    recombination=0.7, tol=1e-3, polish=False,
                                    updating='immediate', workers=1)
        pB = b_params(rB.x, t, mle)
        b_tr, _ = seg(dts, O, H, L, C, pB, chk, trlo, trhi)
        b_te, b_b = seg(dts, O, H, L, C, pB, chk, telo, tehi)
        print(f'  B 6-dim   : train {annualise(b_tr, dts, trlo, trhi)*100:6.1f}%/yr '
              f'| TEST {annualise(b_te, dts, telo, tehi)*100:6.1f}%/yr ({b_b} buys)', flush=True)
        res['B'] = dict(train=annualise(b_tr, dts, trlo, trhi),
                        test=annualise(b_te, dts, telo, tehi), buys_test=b_b,
                        vec=list(rB.x), mle=[float(x) for x in mle])
        results[s] = res
        with open('fresh_opt_results.json', 'w') as fh:      # incremental: survive kills
            json.dump(results, fh, indent=1, default=str)
        print(f'  wrote fresh_opt_results.json ({len(results)} names)', flush=True)

    print(f'\n{"name":6s}{"deployed TEST":>14s}{"A TEST":>10s}{"B TEST":>10s}', flush=True)
    for s, r in results.items():
        print(f'{s:6s}{r["deployed"]["test"]*100:>13.1f}%{r["A"]["test"]*100:>9.1f}%'
              f'{r["B"]["test"]*100:>9.1f}%', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:] or None)
