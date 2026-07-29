"""
Walk-forward + full-sample re-optimisation for the four candidates (CCL, LLY, CVNA, MU).

Two honest OOS questions:
  (A) FROZEN params on the unseen test slice -> does the edge persist WITHOUT refitting?
      This is instant (no fitting) and is the primary suitability signal.
  (B) full-sample robust re-optimisation -> the "optimised" deliverable, plus a single
      confirmatory walk-forward fold (reopt-on-train vs frozen, scored OOS) to check that
      refitting is still the in-sample mirage established earlier (30 folds / 10 names).

Optimiser: differential evolution over 10 params, robust objective
  = 0.5*base + 0.5*mean(+/-3% on the 6 policy params), min-trade floor guard.
Cap = true open (matches the workbook; reproduces 3/4 caches to the dollar).
"""
import sys
from scipy.optimize import differential_evolution
from engine import Params, run_model
from newcands import load, FILES

NAMES  = ['lam', 'phi_L', 'psi', 'k', 'premium', 'peak_cap',
          'ou_buf_k', 'ou_prem', 'ou_cap', 'ou_W']
BOUNDS = [(0.2, 1.6), (0.1, 1.0), (0.001, 0.1), (0.3, 3.0), (0.005, 0.05),
          (0.002, 0.07), (0.1, 2.5), (0.008, 0.06), (0.005, 0.12), (30, 150)]
POLICY = [3, 4, 5, 6, 7, 8]          # k, premium, peak_cap, ou_buf_k, ou_prem, ou_cap
PERTURB = [0.97, 1.03]


def bvec(p):
    return [p.lam, p.phi_L, p.psi, p.k, p.premium, p.peak_cap,
            p.ou_buf_k, p.ou_prem, p.ou_cap, p.ou_W]


def mp(vec, t):
    return Params(lam=vec[0], phi_L=vec[1], psi=vec[2], k=vec[3], premium=vec[4],
                  peak_cap=vec[5], ou_buf_k=vec[6], ou_prem=vec[7], ou_cap=vec[8],
                  ou_W=int(round(vec[9])), comm=t.comm, capital=t.capital,
                  interest=t.interest, stop_days=t.stop_days, bayes_pct=t.bayes_pct,
                  years=t.years)


def segret(eq, lo, hi):
    return eq[hi] / eq[lo] - 1.0 if eq[lo] > 0 else -1.0


def run(data, vec, t):
    p = mp(vec, t)
    return run_model(data['dts'], data['O'], data['H'], data['L'], data['C'], p, collect=True)


def seg(data, vec, t, lo, hi):
    r = run(data, vec, t)
    fr = r.frames
    buys = sum(fr['t1']['Z'][lo:hi + 1]) + sum(fr['t2']['Z'][lo:hi + 1])
    return segret(fr['equity'], lo, hi), buys


def robust(data, vec, t, lo, hi, floor):
    def one(v):
        rr, b = seg(data, v, t, lo, hi)
        return -5.0 + b * 1e-3 if b < floor else rr
    base = one(vec)
    s = []
    for i in POLICY:
        for f in PERTURB:
            v = list(vec); v[i] = min(max(v[i] * f, BOUNDS[i][0]), BOUNDS[i][1])
            s.append(one(v))
    return 0.5 * base + 0.5 * sum(s) / len(s)


def optimise(data, t, lo, hi, floor, maxiter=6, popsize=6, seed=42):
    neg = lambda v: -robust(data, v, t, lo, hi, floor)
    res = differential_evolution(neg, BOUNDS, x0=bvec(t), init='sobol', seed=seed,
                                 maxiter=maxiter, popsize=popsize, mutation=(0.5, 1.0),
                                 recombination=0.7, tol=1e-3, polish=False, disp=False,
                                 updating='immediate', workers=1)
    return list(res.x)


def run_stock(stock):
    dts, O, H, L, C, p, _ = load(stock)
    data = dict(dts=dts, O=O, H=H, L=L, C=C)
    N = len(C); bv = bvec(p)
    print(f'\n===== {stock}  (N={N}) =====', flush=True)

    # (A) FROZEN out-of-sample persistence: expanding train, score the unseen tail
    cuts = [int(N * f) for f in (0.5, 0.667, 0.833, 1.0)]
    folds = [(0, cuts[i] - 1, cuts[i], cuts[i + 1] - 1) for i in range(3)]
    print('  FROZEN OOS (no refit) — annualised on the unseen test slice:', flush=True)
    for k, (trlo, trhi, telo, tehi) in enumerate(folds, 1):
        r_te, b_te = seg(data, bv, p, telo, tehi)
        days = (dts[tehi] - dts[telo]).days or 1
        ann = (1 + r_te) ** (365.25 / days) - 1
        print(f'    fold {k}: test[{telo:>3d}:{tehi:<3d}] {days/365.25:.2f}y  '
              f'ret {r_te*100:>6.1f}%  ann {ann*100:>6.1f}%  buys {b_te}', flush=True)

    # (B1) one confirmatory walk-forward fold: reopt-on-train vs frozen, scored OOS (middle fold)
    trlo, trhi, telo, tehi = folds[1]
    _, tr_buys = seg(data, bv, p, trlo, trhi)
    theta_wf = optimise(data, p, trlo, trhi, max(4, int(0.4 * tr_buys)))
    froz, _ = seg(data, bv, p, telo, tehi)
    reop, _ = seg(data, theta_wf, p, telo, tehi)
    print(f'  WALK-FWD fold2: frozen OOS {froz*100:.1f}%  vs  reopt-on-train OOS '
          f'{reop*100:.1f}%  ->  {"reopt" if reop>froz else "FROZEN"} wins', flush=True)

    # (B2) full-sample robust optimise = the "optimised" deliverable
    _, allb = seg(data, bv, p, 0, N - 1)
    theta = optimise(data, p, 0, N - 1, max(8, int(0.5 * allb)), maxiter=8, popsize=8)
    base_ann = run_model(dts, O, H, L, C, p).annual_return
    opt_r = run_model(dts, O, H, L, C, mp(theta, p))
    print(f'  FULL-SAMPLE optimise: base ann {base_ann:.1%} -> opt ann {opt_r.annual_return:.1%} '
          f'(IN-SAMPLE ceiling); trades {opt_r.total_buys} sharpe {opt_r.sharpe:.2f}', flush=True)
    print('    opt params:', {NAMES[i]: (round(theta[i], 4) if i < 9 else int(round(theta[i])))
                              for i in range(10)}, flush=True)
    return dict(stock=stock, base_ann=base_ann, opt_ann=opt_r.annual_return,
                reopt_win=reop > froz, theta=theta)


if __name__ == '__main__':
    only = sys.argv[1:] or list(FILES)
    res = [run_stock(s) for s in only]
    print('\n===== SUMMARY =====', flush=True)
    for r in res:
        print(f'{r["stock"]:5s} base {r["base_ann"]:.0%} -> in-sample opt {r["opt_ann"]:.0%} | '
              f'walk-fwd reopt beats frozen OOS: {r["reopt_win"]}', flush=True)
