"""
Walk-forward the Schwartz-Smith sleeve.

The full-sample comparison flatters SS badly and must not be believed as it stands: its six
state-space parameters are fitted by maximum likelihood on the whole price series and its
discount k is fitted to whole-sample P&L, while the Bayes and OU sleeves run frozen workbook
parameters. Seven fitted numbers against zero is not a comparison, it is a head start.

Here everything SS uses is fitted on the training window only -- the MLE is re-run on the train
prices and k is chosen on train P&L -- and scored on unseen sessions. Bayes and OU stay frozen,
which if anything still favours SS, since it gets to adapt and they do not.
"""
import statistics, sys
import numpy as np
from ss_sleeve import (DATA, PARAMS, BOOK, LAGGARDS, KGRID, bids, sleeve_run, ann, blend, _SS)
from ss_model import fit_ss, ss_signal

CUTS = (0.5, 0.667, 0.833, 1.0)


def ss_bid_from(th, s, k):
    dts, O, H, L, C = DATA[s]
    fair, sig = ss_signal(C, th)
    G = np.maximum.accumulate(np.array(H, dtype=float))
    out = np.full(len(C), np.nan)
    out[1:] = np.minimum(np.minimum(fair[1:] - k*sig[1:], np.array(O, dtype=float)[1:]),
                         G[:-1]*(1-PARAMS[s].peak_cap))
    return out


def fold_test(names, label):
    print(f'\n{"="*78}\n{label}\n{"="*78}', flush=True)
    print(f'{"stock":7s}{"fold":>5s}{"k":>5s}{"SS OOS":>9s}{"B+O OOS":>10s}{"B+O+SS":>9s}'
          f'{"winner":>10s}', flush=True)
    print('-'*78, flush=True)
    wins_s = wins_3 = tot = 0; ds = []; d3 = []
    for s in names:
        dts = DATA[s][0]; n = len(dts); cuts = [int(n*f) for f in CUTS]
        prem = PARAMS[s].premium
        eB, _ = sleeve_run(s, bids(s, 'bayes'), prem)
        eO, _ = sleeve_run(s, bids(s, 'ou'), prem)
        for j in range(3):
            trhi = cuts[j]; telo, tehi = cuts[j], cuts[j+1]-1
            th, _ = fit_ss(np.log(np.array(DATA[s][4][:trhi], dtype=float)))
            best = None
            for k in KGRID:
                b = ss_bid_from(th, s, k)
                e, t = sleeve_run(s, b, prem, lo=0, hi=trhi-1)
                if t < 4: continue
                a = e[trhi-1]/e[0]
                if best is None or a > best[0]: best = (a, k)
            k = best[1] if best else 1.0
            bS = ss_bid_from(th, s, k)
            eS, _ = sleeve_run(s, bS, prem)
            f = lambda e: (e[tehi]/e[telo]-1)*100
            vS, vBO, v3 = f(eS), f(blend([eB, eO])), f(blend([eB, eO, eS]))
            wins_s += (vS > vBO); wins_3 += (v3 > vBO); tot += 1
            ds.append(vS-vBO); d3.append(v3-vBO)
            w = 'SS' if vS >= max(vBO, v3) else ('B+O+SS' if v3 > vBO else 'B+O')
            print(f'{s:7s}{j+1:>5d}{k:>5.1f}{vS:>8.1f}%{vBO:>9.1f}%{v3:>8.1f}%{w:>10s}',
                  flush=True)
    print('-'*78, flush=True)
    print(f'  SS alone beats B+O in {wins_s}/{tot} folds; mean {statistics.mean(ds):+.1f}pp',
          flush=True)
    print(f'  B+O+SS  beats B+O in {wins_3}/{tot} folds; mean {statistics.mean(d3):+.1f}pp',
          flush=True)


if __name__ == '__main__':
    fold_test(BOOK, 'BOOK NAMES --- everything SS uses fitted on train only')
    fold_test(LAGGARDS, 'REJECTED LAGGARDS --- same protocol')
    print('\nDONE', flush=True)
