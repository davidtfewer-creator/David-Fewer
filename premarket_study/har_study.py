"""
HAR-RV sigma through the standard verified single-split protocol.

Question: does replacing the model's volatility proxies -- the daily range H-L in
the Kalman noise scalings, the AR(1) residual std in the OU buffer -- with a
HAR-RV forecast built from the 5-minute bars improve the TESTED half?

Protocol, identical to fresh_opt variant A per name:
  1. HAR coefficients fitted on the TRAIN half only (RV dates < 2025-05-23).
  2. Variant A (8-dim, lam=1, ou_W frozen at reference) refitted on the train half
     with the HAR series active, same optimiser budget (DE sobol seed 42,
     maxiter 8, popsize 8), same robust objective and trade floor.
  3. Frozen, scored on the tested half with verified fills.
  4. Compared against the existing variant-A baseline (same budget, deployed
     range/residual sigma) from fresh_opt_results.json / fresh_opt_cands.json.

The HAR forecast is strictly ex ante (day i uses bars through day i-1); rows
without coverage fall back to the deployed proxies inside the engine.
"""
import json
import sys

from scipy.optimize import differential_evolution

from engine import Params, run_model
from fresh_opt import SPLIT, A_BOUNDS, A_POLICY, PERTURB, a_params, a_x0, annualise
from fresh_opt_cands import daily_from_5min, ref_params, aw_params
from har_rv import rv_daily, har_fit, forecast_series, engine_series
from live5_load import load as load_book, STOCKS as BOOK
from minute_index import make_checker

NAMES = BOOK + ['GM', 'VLO', 'CF', 'MRVL']


def params_for(s, book_params):
    if s in BOOK:
        return book_params[s]
    if s == 'MRVL':
        t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                    bayes_pct=0.5, years=2.2, ou_W=80)
        return aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    return ref_params(s)


def baseline_A(s):
    src = 'fresh_opt_results.json' if s in BOOK else 'fresh_opt_cands.json'
    return json.load(open(src))[s]['A']


def seg_har(dts, O, H, L, C, p, chk, lo, hi, F_full, ou_sig):
    r = run_model(dts, O, H, L, C, p, ou_sigma='series', same_day_exit=chk,
                  collect=True, F_series=F_full, ou_sig_series=ou_sig)
    eq = r.frames['equity']
    buys = (sum(r.frames['t1']['Z'][lo:hi + 1]) + sum(r.frames['t2']['Z'][lo:hi + 1]))
    ret = eq[hi] / eq[lo] - 1.0 if eq[lo] > 0 else -1.0
    return ret, buys


def main(only=None):
    book_data, book_params, _ = load_book()
    try:
        results = json.load(open('har_study.json'))
    except FileNotFoundError:
        results = {}
    for s in (only or NAMES):
        if s in BOOK:
            dts, O, H, L, C = book_data[s]
        else:
            dts, O, H, L, C = daily_from_5min(s)
        t = params_for(s, book_params)
        chk = make_checker(s, dts, O)
        N = len(C)
        cut = next(i for i, d in enumerate(dts) if d >= SPLIT)
        trlo, trhi, telo, tehi = 0, cut - 1, cut, N - 1
        print(f'\n===== {s}  (N={N}, {dts[0]} to {dts[-1]}) =====', flush=True)

        # ---- HAR fit, train half only
        rv = rv_daily(s)
        beta, diag = har_fit(rv, SPLIT)
        sig_rel = forecast_series(dts, C, rv, beta)
        F_har, ou_sig = engine_series(dts, C, sig_rel)
        F_full = [F_har[i] if F_har[i] is not None else H[i] - L[i] for i in range(N)]
        fb = sum(1 for v in F_har if v is None)
        print(f'  HAR: beta {["%.3f" % b for b in diag["beta"]]}  '
              f'R2 train {diag["r2_train"]:.3f} / TEST {diag["r2_test"]:.3f} '
              f'(naive {diag["r2_naive_test"]:.3f}); fallback rows {fb}/{N}', flush=True)

        # ---- variant A under HAR sigma, train-half fit, same budget
        _, buys_tr = seg_har(dts, O, H, L, C, t, chk, trlo, trhi, F_full, ou_sig)
        floor = max(4, int(0.4 * buys_tr))

        def one(vec):
            ret, buys = seg_har(dts, O, H, L, C, a_params(vec, t), chk,
                                trlo, trhi, F_full, ou_sig)
            return -5.0 + buys * 1e-3 if buys < floor else ret

        def obj(vec):
            base = one(vec)
            ss = []
            for i in A_POLICY:
                for f in PERTURB:
                    v = list(vec)
                    v[i] = v[i] * f
                    ss.append(one(v))
            return -(0.5 * base + 0.5 * sum(ss) / len(ss))

        r = differential_evolution(obj, A_BOUNDS, x0=a_x0(t), init='sobol', seed=42,
                                   maxiter=8, popsize=8, mutation=(0.5, 1.0),
                                   recombination=0.7, tol=1e-3, polish=False,
                                   updating='immediate', workers=1)
        pH = a_params(r.x, t)
        h_tr, _ = seg_har(dts, O, H, L, C, pH, chk, trlo, trhi, F_full, ou_sig)
        h_te, h_b = seg_har(dts, O, H, L, C, pH, chk, telo, tehi, F_full, ou_sig)
        base = baseline_A(s)
        print(f'  A-HAR     : train {annualise(h_tr, dts, trlo, trhi)*100:6.1f}%/yr '
              f'| TEST {annualise(h_te, dts, telo, tehi)*100:6.1f}%/yr ({h_b} buys)', flush=True)
        print(f'  A-baseline: train {base["train"]*100:6.1f}%/yr '
              f'| TEST {base["test"]*100:6.1f}%/yr ({base["buys_test"]} buys)', flush=True)
        results[s] = dict(har=diag,
                          A_har=dict(train=annualise(h_tr, dts, trlo, trhi),
                                     test=annualise(h_te, dts, telo, tehi),
                                     buys_test=h_b, vec=list(r.x)),
                          A_base=dict(train=base['train'], test=base['test'],
                                      buys_test=base['buys_test']))
        with open('har_study.json', 'w') as fh:
            json.dump(results, fh, indent=1, default=str)
        print(f'  wrote har_study.json ({len(results)} names)', flush=True)

    print(f'\n{"name":6s}{"base TEST":>10s}{"HAR TEST":>10s}{"base train":>11s}{"HAR train":>10s}',
          flush=True)
    for s, rr in results.items():
        print(f'{s:6s}{rr["A_base"]["test"]*100:>9.1f}%{rr["A_har"]["test"]*100:>9.1f}%'
              f'{rr["A_base"]["train"]*100:>10.1f}%{rr["A_har"]["train"]*100:>9.1f}%', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:] or None)
