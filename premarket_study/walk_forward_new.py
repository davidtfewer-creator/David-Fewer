"""
Fuller expanding-window walk-forward for the shortlist (MRNA, OXY, FSLR, DVN).

Five folds. Each fold RE-OPTIMISES the parameters on its train window [0, cut) only, freezes
them, and scores the next unseen ~10% test slice. Parameters never see the slice they are
graded on. Report each fold's out-of-sample test return, the share of positive folds, and the
compounded return across all five stitched test slices (annualised) as the headline OOS figure.
Gold standard: if the edge survives every fold, it is structural, not a fit.
"""
import statistics
from engine import Params, run_model
from optimise_candidates import optimise, seg
from newfeed import load, NEW

SHORT = ['MRNA', 'OXY', 'FSLR', 'DVN']
TR_ENDS = [0.5, 0.6, 0.7, 0.8, 0.9]     # train-end fractions; each test = next 10%


def yrs(dts, lo, hi):
    return max((dts[hi] - dts[lo]).days / 365.25, 1e-6)


if __name__ == '__main__':
    data_all = load(NEW, SHORT)
    print(f'Expanding walk-forward, 5 folds, re-optimised each fold (test = unseen next 10%)\n')
    summary = {}
    for t in SHORT:
        dts, O, H, L, C = data_all[t]; N = len(C)
        total_yrs = yrs(dts, 0, N - 1)
        tmpl = Params(capital=6_000_000, comm=0.005, interest=0.0314, stop_days=50,
                      bayes_pct=0.5, years=total_yrs)
        data = dict(dts=dts, O=O, H=H, L=L, C=C)
        print(f'===== {t} (N={N}) =====', flush=True)
        print(f'{"fold":5s}{"train":>12s}{"test":>12s}{"test ret":>10s}{"ann":>8s}{"buys":>6s}',
              flush=True)
        fold_rets = []; stitched = 1.0; stitched_yrs = 0.0
        for k, f in enumerate(TR_ENDS, 1):
            tr_hi = int(N * f)
            te_lo = tr_hi
            te_hi = min(int(N * (f + 0.1)) - 1, N - 1)
            if te_hi <= te_lo:
                continue
            floor = max(8, int(0.3 * tr_hi / 5))
            theta = optimise(data, tmpl, 0, tr_hi - 1, floor, maxiter=8, popsize=8)
            ret, buys = seg(data, theta, tmpl, te_lo, te_hi)
            sy = yrs(dts, te_lo, te_hi)
            ann = (1 + ret) ** (1 / sy) - 1 if ret > -1 else -1
            fold_rets.append(ret); stitched *= (1 + ret); stitched_yrs += sy
            print(f'{k:<5d}[0:{tr_hi:<4d}]  [{te_lo:>3d}:{te_hi:<4d}]{ret*100:>9.1f}%'
                  f'{ann*100:>7.0f}%{buys:>6d}', flush=True)
        pos = sum(1 for r in fold_rets if r > 0)
        oos_ann = stitched ** (1 / stitched_yrs) - 1 if stitched_yrs > 0 else 0
        summary[t] = (pos, len(fold_rets), (stitched - 1) * 100, oos_ann * 100)
        print(f'  -> positive folds {pos}/{len(fold_rets)}; stitched OOS '
              f'{(stitched-1)*100:+.0f}% over {stitched_yrs:.1f}y = {oos_ann*100:.0f}% annualised\n',
              flush=True)

    print('===== SUMMARY (stitched out-of-sample across all folds) =====', flush=True)
    print(f'{"name":6s}{"pos folds":>11s}{"OOS total":>11s}{"OOS ann":>9s}', flush=True)
    for t in SHORT:
        pos, n, tot, ann = summary[t]
        print(f'{t:6s}{f"{pos}/{n}":>11s}{tot:>10.0f}%{ann:>8.0f}%', flush=True)
