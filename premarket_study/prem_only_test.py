"""
NVDA: fit the premium alone, with the peak cap frozen and the 12-week hold cap active.

The joint re-fit put NVDA's premium at exactly 0.055 in all three folds while the peak cap
scattered 5.6x. That raises a fair question -- is the wider premium real, and was only the cap
unstable? Both no-cap fits earlier in this work also preferred a wider premium than the deployed
0.0293, and the time cap was the one change that could have justified it, by bounding the wait
that made a wide target risky.

One parameter, cap frozen at the deployed 0.0935, same three expanding folds.
"""
import statistics
from max_hold_test import run as wrun, _nvda_name, SPEC

MAXWK = 12
PREMS = [round(0.02 + 0.0025*i, 5) for i in range(65)]        # 0.0200 .. 0.1800


def seg(nm, q, w0, w1, c):
    r = wrun(nm, c, q, MAXWK, w0, w1)
    return r['ann'], r['trades']


if __name__ == '__main__':
    nm = _nvda_name(); N = nm.N
    DC, DQ = SPEC['NVDA']
    a0, t0 = seg(nm, DQ, 1, N-1, DC)
    print(f'deployed prem {DQ:.4f} (cap {DC:.4f} fixed): {a0*100:.1f}%, {t0} trades\n')
    best = max((seg(nm, q, 1, N-1, DC)[0], q) for q in PREMS
               if seg(nm, q, 1, N-1, DC)[1] >= 20)
    print(f'full-sample best prem {best[1]:.4f}: {best[0]*100:.1f}%  '
          f'({(best[0]-a0)*100:+.1f}pp)\n')
    cuts = [int(N*f) for f in (0.5, 0.667, 0.833, 1.0)]
    print(f'{"fold":5s}{"fitted prem":>13s}{"fitted OOS":>12s}{"deployed OOS":>14s}'
          f'{"winner":>11s}')
    w = 0; d = []; picks = []
    for k in range(3):
        trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
        _, ttr = seg(nm, DQ, 1, trhi-1, DC); fl = max(4, int(0.4*ttr))
        b = max((seg(nm, q, 1, trhi-1, DC)[0], q) for q in PREMS
                if seg(nm, q, 1, trhi-1, DC)[1] >= fl)
        picks.append(b[1])
        a, _ = seg(nm, b[1], telo, tehi, DC); bb, _ = seg(nm, DQ, telo, tehi, DC)
        w += (a > bb); d.append((a-bb)*100)
        print(f'{k+1:<5d}{b[1]:>13.4f}{a*100:>11.1f}%{bb*100:>13.1f}%'
              f'{("fitted" if a > bb else "deployed"):>11s}')
    print(f'\nfitted beats deployed in {w}/3; mean {statistics.mean(d):+.1f}pp')
    print(f'fold premiums {picks}  spread {max(picks)/min(picks):.2f}x')
    print('\nfull-sample sweep with the cap fixed:')
    for q in (0.025, 0.0293, 0.035, 0.045, 0.055, 0.070, 0.090, 0.120):
        a, t = seg(nm, q, 1, N-1, DC)
        print(f'   prem {q:.4f}: {a*100:6.1f}%  ({t} trades)')
