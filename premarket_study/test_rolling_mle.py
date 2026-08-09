"""
Sanity checks for rolling_mle before it touches real data.

1. RECOVERY: simulate the exact local-linear-trend process the filter assumes
   (level+slope random walk, noises scaled by an exogenous daily range) with known
   (lam, phi_L, psi); check the MLE recovers them from 126- and 63-day windows and
   that the truth lies inside ~2 standard errors most of the time.
2. STABILITY: on a stationary simulation, rolling windows should wander inside
   their error bars — this calibrates what "no drift" looks like before we read
   the real trajectories.
3. DETECTION: simulate a mid-sample break in phi_L and check the rolling
   trajectory actually shows it — the study is pointless if the instrument
   cannot see a change of the size we care about.
"""
import math
import random

import numpy as np

from rolling_mle import fit_window, loglik


def simulate(n, lam, phi_L, psi, seed, p0=100.0):
    rng = random.Random(seed)
    # exogenous "daily range" series, lognormal around 2% of price
    lvl, slp = p0, 0.05
    C, F = [], []
    price = p0
    for i in range(n):
        rng_f = price * 0.02 * math.exp(rng.gauss(0, 0.3))
        lvl += slp + rng.gauss(0, phi_L * rng_f)
        slp += rng.gauss(0, psi * rng_f)
        price = lvl + rng.gauss(0, lam * rng_f)
        C.append(price)
        F.append(rng_f)
    return np.array(C), np.array(F)


def test_recovery():
    true = (0.45, 0.30, 0.08)
    x0s = [np.array([0.5, 0.3, 0.05]), np.array([0.8, 0.15, 0.02])]
    print('=== recovery, 126-day windows ===')
    hits = 0
    for seed in range(8):
        C, F = simulate(126, *true, seed=seed)
        th, se, _ = fit_window(C, F, x0s)
        ok = all(abs(th[j] - true[j]) < 2.5 * se[j] for j in range(3) if np.isfinite(se[j]))
        hits += ok
        print(f'  seed {seed}: lam {th[0]:.3f}±{se[0]:.3f} phi_L {th[1]:.3f}±{se[1]:.3f} '
              f'psi {th[2]:.4f}±{se[2]:.4f}  {"ok" if ok else "MISS"}')
    print(f'  truth inside 2.5 SE: {hits}/8 (want >=6)')
    assert hits >= 6

    print('=== recovery, 63-day windows ===')
    devs = []
    for seed in range(8):
        C, F = simulate(63, *true, seed=100 + seed)
        th, se, _ = fit_window(C, F, x0s)
        devs.append([th[j] / true[j] for j in range(3)])
    m = np.median(devs, axis=0)
    print(f'  median theta/truth over 8 seeds: lam {m[0]:.2f} phi_L {m[1]:.2f} psi {m[2]:.2f}')


def test_stability_and_break():
    true = (0.45, 0.30, 0.08)
    x0s = [np.array([0.5, 0.3, 0.05])]
    # stationary: 500 days, rolling 126 stepped 21
    C, F = simulate(500, *true, seed=7)
    traj = []
    for hi in range(126, 500, 21):
        th, se, _ = fit_window(C[hi - 126:hi], F[hi - 126:hi], x0s)
        traj.append((th, se))
    z = [abs(th[1] - true[1]) / se[1] for th, se in traj if np.isfinite(se[1])]
    print(f'=== stationary rolling: median |z| of phi_L vs truth {np.median(z):.2f} (want ~1) ===')

    # break: phi_L doubles at day 250. Pool several simulated paths — windows overlap
    # (step 21 vs length 126) so one path gives few independent looks.
    wins = 0
    pres, posts = [], []
    for sd in range(4):
        C1, F1 = simulate(250, 0.45, 0.30, 0.08, seed=21 + sd)
        C2, F2 = simulate(250, 0.45, 0.60, 0.08, seed=121 + sd, p0=C1[-1])
        C = np.concatenate([C1, C2]); F = np.concatenate([F1, F2])
        pre, post = [], []
        for hi in range(126, 500, 21):
            th, se, _ = fit_window(C[hi - 126:hi], F[hi - 126:hi], x0s)
            if hi <= 250:
                pre.append(th[1])          # window entirely pre-break
            elif hi - 126 >= 250:
                post.append(th[1])         # window entirely post-break; straddlers excluded
        wins += np.median(post) > np.median(pre)
        pres += pre; posts += post
    print(f'=== break detection over 4 paths: phi_L median pre {np.median(pres):.3f} '
          f'post {np.median(posts):.3f} (true 0.30 -> 0.60); '
          f'post>pre in {wins}/4 paths ===')
    assert wins >= 3 and np.median(posts) > np.median(pres) * 1.3


if __name__ == '__main__':
    test_recovery()
    test_stability_and_break()
    print('all checks passed')
