"""Walk-forward the close-conditional premium on the VERIFIED (minute/5-min) fill basis."""
import statistics
from collections import Counter
from stop_sweep import load_book
from engine import run_model
from five_min import make_checker, FILES
from minute_engine import make_checker as nvda_checker

data, params, cached = load_book()
CHK = {}
for s in FILES:
    dts, O, H, L, C = data[s]; CHK[s], _ = make_checker(s, dts, O)
dts, O, H, L, C = data['NVDA']; CHK['NVDA'], _ = nvda_checker(dts, O)
NAMES = list(CHK)
UPS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
CUTS = (0.5, 0.667, 0.833, 1.0)

def fr(s, cu):
    d, O, H, L, C = data[s]
    return run_model(d, O, H, L, C, params[s], collect=True, same_day_exit=CHK[s],
                     cc_up=cu, cc_down=(None if cu is None else 1.0)).frames

def seg(f, lo, hi):
    eq = f['equity']
    return eq[hi]/eq[lo]-1 if eq[lo] > 0 else -1.0

F = {s: {cu: fr(s, cu) for cu in UPS} for s in NAMES}
FIX = {s: fr(s, None) for s in NAMES}
print(f'{"stock":6s}{"fold":>5s}{"cc_up*":>8s}{"cc OOS":>9s}{"fixed OOS":>11s}{"winner":>9s}')
print('-'*48)
wins = tot = 0; diffs = []; chosen = []
for s in NAMES:
    N = len(data[s][4]); cuts = [int(N*f) for f in CUTS]
    for k in range(3):
        trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
        bcu, btr = None, -9e9
        for cu in UPS:
            t = seg(F[s][cu], 0, trhi-1)
            if t > btr: btr, bcu = t, cu
        cc = seg(F[s][bcu], telo, tehi); fx = seg(FIX[s], telo, tehi)
        wins += (cc > fx); tot += 1; diffs.append((cc-fx)*100); chosen.append(bcu)
        print(f'{s:6s}{k+1:>5d}{bcu:>8.2f}{cc*100:>8.1f}%{fx*100:>10.1f}%{("cc" if cc>fx else "fixed"):>9s}')
print('-'*48)
print(f'close-conditional beats fixed OOS in {wins}/{tot} folds')
print(f'mean {statistics.mean(diffs):+.1f}pp  median {statistics.median(diffs):+.1f}pp')
print(f'cc_up chosen on train: {dict(sorted(Counter(chosen).items()))}')
print('DONE')
