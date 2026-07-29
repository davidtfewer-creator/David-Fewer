"""
Walk-forward + full-sample re-optimisation for the four candidates.

The suitability question has two honest OOS parts:
  (A) FROZEN params on the unseen test slice  -> does the edge persist without refitting?
      This is the real "will this name keep working" signal.
  (B) REOPT-on-train vs frozen, scored on the same unseen test slice -> does refitting add
      value OOS, or is it the in-sample mirage established earlier?

Then a full-sample robust DE fit per stock, reported as the "optimised" deliverable with an
honest in-sample-gain caveat.

Optimiser: differential evolution over 10 params, robust objective = 0.5*base +
0.5*mean(+/-3% one-at-a-time perturbations), with a min-trade floor (frequency-collapse guard).
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
PERTURB = [0.97, 1.03]


def base_vec(p):
    return [p.lam, p.phi_L, p.psi, p.k, p.premium, p.peak_cap,
            p.ou_buf_k, p.ou_prem, p.ou_cap, p.ou_W]


def make_params(vec, tmpl):
    return Params(lam=vec[0], phi_L=vec[1], psi=vec[2], k=vec[3], premium=vec[4],
                  peak_cap=vec[5], ou_buf_k=vec[6], ou_prem=vec[7], ou_cap=vec[8],
                  ou_W=int(round(vec[9])), comm=tmpl.comm, capital=tmpl.capital,
                  interest=tmpl.interest, stop_days=tmpl.stop_days,
                  bayes_pct=tmpl.bayes_pct, years=tmpl.years)


def seg_return(eq, lo, hi):
    return eq[hi] / eq[lo] - 1.0 if eq[lo] > 0 else -1.0


def seg_buys(fr, lo, hi):
    return sum(fr['t1']['Z'][lo:hi + 1]) + sum(fr['t2']['Z'][lo:hi + 1])


def evaluate(data, vec, tmpl, lo, hi):
    p = make_params(vec, tmpl)
    r = run_model(data['dts'], data['O'], data['H'], data['L'], data['C'], p, collect=True)
    return seg_return(r.frames['equity'], lo, hi), seg_buys(r.frames, lo, hi)


def robust_train(data, vec, tmpl, lo, hi, min_buys):
    def one(v):
        ret, buys = evaluate(data, v, tmpl, lo, hi)
        return -5.0 + buys * 0.001 if buys < min_buys else ret
    base = one(vec)
    samples = []
    for i in range(9):
        for f in PERTURB:
            v = list(vec); v[i] = min(max(v[i] * f, BOUNDS[i][0]), BOUNDS[i][1])
            samples.append(one(v))
    return 0.5 * base + 0.5 * sum(samples) / len(samples)


def optimise(data, tmpl, lo, hi, min_buys, seed=42, maxiter=10, popsize=8):
    neg = lambda v: -robust_train(data, v, tmpl, lo, hi, min_buys)
    res = differential_evolution(
        neg, BOUNDS, x0=base_vec(tmpl), init='sobol', seed=seed, maxiter=maxiter,
        popsize=popsize, mutation=(0.5, 1.0), recombination=0.7, tol=1e-4,
        polish=False, disp=False, updating='immediate', workers=1)
    return res.x


def run_stock(stock):
    dts, O, H, L, C, p, _ = load(stock)
    data = dict(dts=dts, O=O, H=H, L=L, C=C)
    N = len(C)
    bv = base_vec(p)

    # expanding-window walk-forward, 3 test folds over the back half
    cuts = [int(N * f) for f in (0.5, 0.667, 0.833, 1.0)]
    folds = [(0, cuts[i] - 1, cuts[i], cuts[i + 1] - 1) for i in range(3)]
    print(f'\n===== {stock}  (N={N}) =====', flush=True)
    print(f'{"fold":5s}{"train":>13s}{"test":>13s}{"frozen OOS":>12s}{"reopt OOS":>11s}   winner',
          flush=True)
    reopt_wins = 0
    for k, (trlo, trhi, telo, tehi) in enumerate(folds, 1):
        _, base_tr_buys = evaluate(data, bv, p, trlo, trhi)
        floor = max(4, int(0.4 * base_tr_buys))
        theta = optimise(data, p, trlo, trhi, floor, maxiter=8, popsize=8)
        froz, _ = evaluate(data, bv, p, telo, tehi)
        reop, _ = evaluate(data, theta, p, telo, tehi)
        win = 'reopt' if reop > froz else 'frozen'
        reopt_wins += (reop > froz)
        print(f'{k:<5d}[{trlo:>3d}:{trhi:<3d}]  [{telo:>3d}:{tehi:<3d}]  '
              f'{froz*100:>10.1f}%{reop*100:>10.1f}%   {win}', flush=True)
    print(f'  -> reopt beats frozen OOS in {reopt_wins}/3 folds', flush=True)

    # full-sample robust optimise
    _, all_buys = evaluate(data, bv, p, 0, N - 1)
    theta = optimise(data, p, 0, N - 1, max(8, int(0.5 * all_buys)), maxiter=12, popsize=10)
    base_ann = run_model(dts, O, H, L, C, p).annual_return
    opt_ann = run_model(dts, O, H, L, C, make_params(theta, p)).annual_return
    print(f'  full-sample: base ann {base_ann:.1%}  ->  robust-opt ann {opt_ann:.1%} '
          f'(in-sample; treat as ceiling)', flush=True)
    print('  opt params:', {NAMES[i]: (round(theta[i], 4) if i < 9 else int(round(theta[i])))
                             for i in range(10)}, flush=True)
    return dict(stock=stock, reopt_wins=reopt_wins, base_ann=base_ann, opt_ann=opt_ann,
                theta=list(theta))


if __name__ == '__main__':
    only = sys.argv[1:] or list(FILES)
    results = [run_stock(s) for s in only]
    print('\n===== SUMMARY =====', flush=True)
    for r in results:
        print(f'{r["stock"]:5s} reopt OOS wins {r["reopt_wins"]}/3 | '
              f'base {r["base_ann"]:.0%} -> in-sample opt {r["opt_ann"]:.0%}', flush=True)
