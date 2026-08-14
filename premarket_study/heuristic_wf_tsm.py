"""
Confirmatory walk-forward for the one live swap candidate: replace TSM's OU sleeve with the
old fixed-parameter heuristic.

Three expanding folds (test slices [50%:66.7%], [66.7%:83.3%], [83.3%:100%], train = all data
before the slice). Per fold, at-open basis, residual OU sigma, held construction:

    heur-refit   heuristic refit on the train window only (robust objective), frozen, OOS
    heur-frozen  the first-half fit from heuristic_fixed.py, applied unchanged
    Bayes / OU   deployed sleeves (full-sample params — flattered; the bar a swap must clear)
    B+OU vs B+H  the decision: 50/50 pairings, sleeves normalised at fold start

Caveats stated up front: fold agreement in an expanding walk-forward is NOT independent
evidence (the folds are nested), and the deployed vectors saw every test slice. A swap should
clear the bar anyway.
"""
import sys

from engine import run_model
from heuristic_fixed import load, hp, optimise, incumbent, seg_ann, HNAMES
from heuristic_engine import run_heuristic
from heuristic_symmetric import HEUR
from heuristic_book import sleeve_equity, ann_dd, corr, rets

STOCK = sys.argv[1] if len(sys.argv) > 1 else 'TSM'


def norm(e, lo, hi):
    return [v / e[lo] for v in e[lo:hi + 1]]


if __name__ == '__main__':
    data = load(STOCK)
    dts, O, H, L, C, p = data
    N = len(dts)
    cuts = [int(N * f) for f in (0.5, 2 / 3, 5 / 6, 1.0)]
    folds = [(cuts[i], cuts[i + 1] - 1) for i in range(3)]

    r = run_model(dts, O, H, L, C, p, ou_sigma='resid', collect=True, same_day_exit='at_open')
    eB = sleeve_equity(r.frames['t1'], C)
    eO = sleeve_equity(r.frames['t2'], C)
    eHf = run_heuristic(dts, O, H, L, C, hp(HEUR[STOCK], p),
                        same_day_exit='at_open').frames['equity']

    print(f'{STOCK}: N={N}, folds ' + ', '.join(f'[{a}:{b}]' for a, b in folds), flush=True)
    print(f'{"fold":5s}{"window":>24s}{"heur-refit":>11s}{"heur-frozn":>11s}{"Bayes":>8s}'
          f'{"OU":>8s} |{"B+OU":>8s}{"B+H":>8s}{"delta":>7s}', flush=True)
    wins = 0
    for k, (telo, tehi) in enumerate(folds, 1):
        trhi = telo - 1
        inc_tr = incumbent(data, 0, trhi)['open'][1]
        vec, _ = optimise(data, 0, trhi, max(8, int(0.20 * inc_tr)))
        eHr = run_heuristic(dts, O, H, L, C, hp(vec, p),
                            same_day_exit='at_open').frames['equity']
        te = dts[telo:tehi + 1]
        nB, nO = norm(eB, telo, tehi), norm(eO, telo, tehi)
        nHr, nHf = norm(eHr, telo, tehi), norm(eHf, telo, tehi)
        aB, _ = ann_dd(nB, te); aO, _ = ann_dd(nO, te)
        aHr, _ = ann_dd(nHr, te); aHf, _ = ann_dd(nHf, te)
        bo = [(nB[i] + nO[i]) / 2 for i in range(len(nB))]
        bh = [(nB[i] + nHr[i]) / 2 for i in range(len(nB))]
        aBO, dBO = ann_dd(bo, te); aBH, dBH = ann_dd(bh, te)
        wins += aBH > aBO
        print(f'{k:<5d}{dts[telo].isoformat()} {dts[tehi].isoformat():>12s}'
              f'{aHr * 100:>10.1f}%{aHf * 100:>10.1f}%{aB * 100:>7.1f}%{aO * 100:>7.1f}% |'
              f'{aBO * 100:>7.1f}%{aBH * 100:>7.1f}%{(aBH - aBO) * 100:>+7.1f}', flush=True)
        print(f'      refit: ' + ', '.join(f'{n}={v:.4f}' for n, v in zip(HNAMES, vec))
              + f'   corr(Hr,B) {corr(rets(nHr), rets(nB)):.2f}'
              + f'  corr(O,B) {corr(rets(nO), rets(nB)):.2f}'
              + f'  DD BO {dBO * 100:.1f}% BH {dBH * 100:.1f}%', flush=True)
    print(f'\nB+heuristic beats deployed B+OU in {wins}/3 folds '
          f'(nested folds — agreement is not independent evidence)', flush=True)
