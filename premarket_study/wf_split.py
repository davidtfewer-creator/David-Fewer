"""
Walk-forward the PER-STOCK Bayes/OU split on verified fills.

Per name, three expanding folds: pick the Bayes share on the TRAIN window only, freeze it, and
score the unseen TEST slice against the current uniform 50/50 on that same slice.
One parameter per name, chosen from an 11-point grid -- far less to overfit than the failed
multi-parameter refits, and the underlying curves are monotonic rather than peaked.
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

GRID = [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
CUTS = (0.5, 0.667, 0.833, 1.0)


def equity(s, bp):
    dts, O, H, L, C = data[s]
    p = copy.copy(params[s]); p.bayes_pct = bp
    return run_model(dts, O, H, L, C, p, collect=True, same_day_exit=CHK[s]).frames['equity']


def seg(eq, lo, hi):
    return eq[hi]/eq[lo]-1 if eq[lo] > 0 else -1.0


if __name__ == '__main__':
    print('Walk-forward: per-stock Bayes share chosen on train, scored OOS vs uniform 50/50')
    print('basis = verified fills; 3 expanding folds x 10 names\n', flush=True)
    EQ = {s: {g: equity(s, g) for g in GRID} for s in STOCKS}
    print(f'{"stock":6s}{"fold":>5s}{"chosen":>8s}{"split OOS":>11s}{"50/50 OOS":>11s}{"winner":>9s}',
          flush=True)
    print('-' * 50, flush=True)
    wins = tot = 0; diffs = []; chosen = []
    for s in STOCKS:
        N = len(data[s][4]); cuts = [int(N*f) for f in CUTS]
        for k in range(3):
            trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
            bg, btr = None, -9e9
            for g in GRID:                                    # choose on TRAIN only
                tr = seg(EQ[s][g], 0, trhi-1)
                if tr > btr: btr, bg = tr, g
            a = seg(EQ[s][bg], telo, tehi)
            b = seg(EQ[s][0.5], telo, tehi)
            wins += (a > b); tot += 1; diffs.append((a-b)*100); chosen.append(bg)
            print(f'{s:6s}{k+1:>5d}{bg*100:>7.0f}%{a*100:>10.1f}%{b*100:>10.1f}%'
                  f'{("split" if a > b else "50/50"):>9s}', flush=True)
    print('-' * 50, flush=True)
    print(f'per-stock split beats 50/50 OOS in {wins}/{tot} folds', flush=True)
    print(f'mean {statistics.mean(diffs):+.1f}pp   median {statistics.median(diffs):+.1f}pp', flush=True)
    print(f'chosen shares: {dict(sorted(Counter(chosen).items()))}', flush=True)
    print('DONE', flush=True)
