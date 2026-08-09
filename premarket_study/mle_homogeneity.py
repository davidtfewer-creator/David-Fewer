"""
Likelihood-ratio homogeneity tests — the omnibus answer to "is the process
non-stationary?", free of the Hessian standard errors the chi2 table leans on.

TEST 1 (windows): cut the sample into K non-overlapping windows (63d and 126d).
  H0: one (lam, phi_L, psi) for all windows.  H1: each window its own vector.
  Each window's filter restarts with the same burn-in under both hypotheses, so
  the only difference is the parameter vector. LR = 2*(sum_w ll_w(theta_w) -
  sum_w ll_w(theta_full)), dof = 3*(K-1), p from chi2.

TEST 2 (the crash): the only AI drawdown episode in sample, 2025-01-01 to
  2025-04-30, as its own segment vs everything else. 2 segments, dof 3. This is
  the sharpest version of the user's hypothesis — if the market view change
  shows up anywhere in the price process, it is here.

A small p means the process genuinely moved. A large p means a single vector
explains the data as well as window-by-window refits — the non-stationarity
hypothesis fails at the level of the price process itself.
"""
from datetime import date

import numpy as np
from scipy import stats

from mle_load import load_csv_dir
from rolling_mle import DEPLOYED, fit_window, loglik

CRASH = (date(2025, 1, 1), date(2025, 4, 30))


def seg_ll(C, F, theta):
    return loglik(np.asarray(C, float), np.asarray(F, float), *theta)


def lr_test(segs, x0s):
    """segs: list of (C, F) arrays. Returns (LR, dof, p, thetas)."""
    th_all = []
    ll_h1 = 0.0
    for C, F in segs:
        th, _, ll = fit_window(np.asarray(C), np.asarray(F), x0s)
        th_all.append(th)
        ll_h1 += ll
    # H0: single theta maximised over the SUM of segment likelihoods
    from scipy.optimize import minimize
    neg = lambda z: -sum(seg_ll(C, F, np.exp(z)) for C, F in segs)
    z0 = np.log(np.mean(th_all, axis=0))
    best = None
    for start in [z0] + [np.log(t) for t in th_all[:2]]:
        r = minimize(neg, start, method='Nelder-Mead',
                     options=dict(xatol=1e-5, fatol=1e-7, maxiter=2000))
        if best is None or r.fun < best.fun:
            best = r
    ll_h0 = -best.fun
    LR = 2 * (ll_h1 - ll_h0)
    dof = 3 * (len(segs) - 1)
    p = 1 - stats.chi2.cdf(LR, dof)
    return LR, dof, p, th_all, np.exp(best.x)


def main():
    data = load_csv_dir('data_mle')
    print(f'{"name":6s}{"test":>14s}{"K":>4s}{"LR":>10s}{"dof":>5s}{"p":>10s}')
    for name in sorted(data):
        dts, O, H, L, C = data[name]
        F = [H[i] - L[i] for i in range(len(C))]
        dep = DEPLOYED.get(name, dict(lam=0.5, phi_L=0.3, psi=0.05))
        x0s = [np.array([dep['lam'], dep['phi_L'], dep['psi']]),
               np.array([0.1, 0.7, 0.005])]
        N = len(C)

        for W in (63, 126):
            K = N // W
            segs = [(C[k * W:(k + 1) * W], F[k * W:(k + 1) * W]) for k in range(K)]
            LR, dof, p, _, _ = lr_test(segs, x0s)
            print(f'{name:6s}{f"{W}d windows":>14s}{K:>4d}{LR:>10.1f}{dof:>5d}{p:>10.4f}',
                  flush=True)

        # crash episode vs the rest (rest split at the crash, filter cannot skip a gap:
        # segments must be contiguous -> three segments, but H1 gives the crash its own
        # theta while the two rest-pieces SHARE one. dof = 3.
        i0 = next(i for i, d in enumerate(dts) if d >= CRASH[0])
        i1 = next(i for i, d in enumerate(dts) if d > CRASH[1])
        pre = (C[:i0], F[:i0])
        mid = (C[i0:i1], F[i0:i1])
        post = (C[i1:], F[i1:])
        from scipy.optimize import minimize
        def neg_h0(z):
            t = np.exp(z)
            return -(seg_ll(*pre, t) + seg_ll(*mid, t) + seg_ll(*post, t))
        def neg_h1(z):
            t_rest, t_crash = np.exp(z[:3]), np.exp(z[3:])
            return -(seg_ll(*pre, t_rest) + seg_ll(*mid, t_crash) + seg_ll(*post, t_rest))
        z0 = np.log([dep['lam'], dep['phi_L'], max(dep['psi'], 1e-3)])
        r0 = min((minimize(neg_h0, s, method='Nelder-Mead',
                           options=dict(xatol=1e-5, fatol=1e-7, maxiter=3000))
                  for s in [z0, np.log([0.1, 0.7, 0.005])]), key=lambda r: r.fun)
        r1 = min((minimize(neg_h1, np.concatenate([s, s]), method='Nelder-Mead',
                           options=dict(xatol=1e-5, fatol=1e-7, maxiter=6000))
                  for s in [z0, np.log([0.1, 0.7, 0.005])]), key=lambda r: r.fun)
        LR = 2 * (-r1.fun + r0.fun)
        p = 1 - stats.chi2.cdf(LR, 3)
        t_rest, t_crash = np.exp(r1.x[:3]), np.exp(r1.x[3:])
        print(f'{name:6s}{"crash vs rest":>14s}{2:>4d}{LR:>10.1f}{3:>5d}{p:>10.4f}'
              f'   rest lam/phi_L/psi {t_rest[0]:.2f}/{t_rest[1]:.2f}/{t_rest[2]:.3f}'
              f'  crash {t_crash[0]:.2f}/{t_crash[1]:.2f}/{t_crash[2]:.3f}', flush=True)


if __name__ == '__main__':
    main()
