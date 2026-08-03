"""
Walk-forward the CLOSE-CONDITIONAL premium.

The rule adds one parameter (cc_up), so the honest test is: choose cc_up on the TRAIN window of
each fold, freeze it, and score the unseen TEST slice against the fixed-premium model on the
same slice. Three expanding folds x ten names = 30 independent out-of-sample comparisons.

Basis: 'at_open' (realistic overnight holds, available for every name). cc_down fixed at 1.0
-- the grid showed the rule should be one-sided (widen on strong closes, never tighten).
"""
import statistics
from stop_sweep import load_book
from engine import run_model

data, params, cached = load_book()
STOCKS = list(data)
UPS = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
CUTS = (0.5, 0.667, 0.833, 1.0)
BASIS = 'at_open'


def frames(s, cu):
    dts, O, H, L, C = data[s]
    return run_model(dts, O, H, L, C, params[s], collect=True, same_day_exit=BASIS,
                     cc_up=(None if cu is None else cu),
                     cc_down=(None if cu is None else 1.0)).frames


def seg(fr, lo, hi):
    eq = fr['equity']
    return eq[hi]/eq[lo]-1 if eq[lo] > 0 else -1.0


if __name__ == '__main__':
    print('Walk-forward: close-conditional premium (cc_up chosen on train, cc_down=1.0)')
    print(f'basis = {BASIS}; 3 expanding folds x 10 names\n')
    print(f'{"stock":6s}{"fold":>5s}{"cc_up*":>8s}{"cc OOS":>9s}{"fixed OOS":>11s}{"winner":>9s}')
    print('-' * 48)
    wins = 0; tot = 0; d_all = []; chosen = []
    # pre-compute frames per cc_up per stock (cheap on daily data)
    F = {s: {cu: frames(s, cu) for cu in UPS} for s in STOCKS}
    FIX = {s: frames(s, None) for s in STOCKS}
    for s in STOCKS:
        N = len(data[s][4])
        cuts = [int(N*f) for f in CUTS]
        for k in range(3):
            trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
            # choose cc_up on TRAIN only
            best_cu, best_tr = None, -9e9
            for cu in UPS:
                tr = seg(F[s][cu], 0, trhi-1)
                if tr > best_tr:
                    best_tr, best_cu = tr, cu
            cc = seg(F[s][best_cu], telo, tehi)
            fx = seg(FIX[s], telo, tehi)
            wins += (cc > fx); tot += 1; d_all.append((cc-fx)*100); chosen.append(best_cu)
            print(f'{s:6s}{k+1:>5d}{best_cu:>8.2f}{cc*100:>8.1f}%{fx*100:>10.1f}%'
                  f'{("cc" if cc > fx else "fixed"):>9s}')
    print('-' * 48)
    print(f'close-conditional beats fixed OOS in {wins}/{tot} folds')
    print(f'mean OOS advantage: {statistics.mean(d_all):+.1f}pp   median {statistics.median(d_all):+.1f}pp')
    from collections import Counter
    print(f'cc_up chosen on train: {dict(sorted(Counter(chosen).items()))}')
    print('DONE')
