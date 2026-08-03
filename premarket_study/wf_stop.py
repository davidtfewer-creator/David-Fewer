"""
Walk-forward the variable calendar stop on VERIFIED fills.

Same protocol as the sleeve-split walk-forward (which passed): three expanding folds per name,
the stop period chosen on the TRAIN window only, frozen, then scored on the unseen TEST slice
against the incumbent uniform 50 days.

Also records which stop each fold selected: stability across folds is the diagnostic that
separated the one validated change from the six rejected ones.
"""
import copy, statistics
from collections import Counter
from stop_sweep import load_book
from engine import run_model
from five_min import make_checker as fm
from minute_engine import make_checker as nv

data, params, cached = load_book()
STOCKS = list(data)
CHK = {}
for s in STOCKS:
    dts, O, H, L, C = data[s]
    CHK[s] = nv(dts, O)[0] if s == 'NVDA' else fm(s, dts, O)[0]

GRID = [10, 15, 20, 25, 30, 40, 50, 60, 75, 90, 120, 150]
CUTS = (0.5, 0.667, 0.833, 1.0)


def equity(s, sd):
    dts, O, H, L, C = data[s]
    p = copy.copy(params[s]); p.stop_days = sd
    return run_model(dts, O, H, L, C, p, collect=True, same_day_exit=CHK[s]).frames['equity']


def seg(eq, lo, hi):
    return eq[hi]/eq[lo]-1 if eq[lo] > 0 else -1.0


if __name__ == '__main__':
    print('Walk-forward: calendar stop chosen on train, scored OOS vs uniform 50 days')
    print('basis = verified fills; 3 expanding folds x 10 names\n', flush=True)
    EQ = {s: {sd: equity(s, sd) for sd in GRID} for s in STOCKS}
    print(f'{"stock":6s}{"fold":>5s}{"chosen":>8s}{"var OOS":>10s}{"T2=50 OOS":>11s}{"winner":>9s}',
          flush=True)
    print('-' * 49, flush=True)
    wins = tot = 0; diffs = []; chosen = []
    per_name = {}
    for s in STOCKS:
        N = len(data[s][4]); cuts = [int(N*f) for f in CUTS]
        w_s = 0
        for k in range(3):
            trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
            bs, btr = None, -9e9
            for sd in GRID:                                  # choose on TRAIN only
                tr = seg(EQ[s][sd], 0, trhi-1)
                if tr > btr: btr, bs = tr, sd
            a = seg(EQ[s][bs], telo, tehi)
            b = seg(EQ[s][50], telo, tehi)
            wins += (a > b); w_s += (a > b); tot += 1
            diffs.append((a-b)*100); chosen.append(bs)
            print(f'{s:6s}{k+1:>5d}{bs:>8d}{a*100:>9.1f}%{b*100:>10.1f}%'
                  f'{("var" if a > b else "T2=50"):>9s}', flush=True)
        per_name[s] = w_s
    print('-' * 49, flush=True)
    print(f'variable stop beats uniform 50 in {wins}/{tot} folds', flush=True)
    print(f'mean {statistics.mean(diffs):+.1f}pp   median {statistics.median(diffs):+.1f}pp', flush=True)
    print(f'stops chosen on train: {dict(sorted(Counter(chosen).items()))}', flush=True)
    print(f'per-name folds won: {per_name}', flush=True)
    print('DONE', flush=True)
