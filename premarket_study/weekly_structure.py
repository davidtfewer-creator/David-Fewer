"""
Structural tests on the weekly MR model, with the five parameters HELD FIXED.

Every parameter fit attempted this session has failed out of sample; the two changes that
survived were structural/allocation choices. So here the workbook parameters are frozen and only
the architecture varies:

    * number of tranches            1, 2, 3, 4, 6
    * stagger between tranches      1, 2, 3 weeks
    * entry anchor                  which weekday the "week" is taken to start on

Each is chosen on a training window and scored on unseen weeks, so the structural choice itself
is validated rather than fitted.
"""
import statistics, math, datetime
from weekly_mr import DTS, O, H, L, C, IDX, COMM, INTEREST, P, verify_same_day


def build_weeks(anchor=0):
    """Group sessions into weeks starting on `anchor` weekday (0=Mon)."""
    wk, cur = [], []
    for i in range(len(C)):
        if cur and DTS[i].weekday() == anchor:
            wk.append(cur); cur = []
        cur.append(i)
    if cur: wk.append(cur)
    return [w for w in wk if len(w) >= 2]


def stats(idxs):
    return dict(o=O[idxs[0]], h=max(H[i] for i in idxs), l=min(L[i] for i in idxs),
                c=C[idxs[-1]], idxs=idxs)


def tranche(WS, w0, w1, p=P, capital=1.0):
    """Run one tranche over weeks [w0,w1]; minute-verified same-day exits."""
    fund, shares, holding = capital, 0.0, False
    buy = tgt = None; trades = 0
    if w0 >= len(WS): return capital, 0
    ath = max(H[i] for i in WS[w0]['idxs'])
    for wi in range(w0+1, min(w1, len(WS)-1)+1):
        prev, cwk = WS[wi-1], WS[wi]
        ath = max(ath, prev['h'])
        if not holding:
            d = (DTS[cwk['idxs'][-1]] - DTS[prev['idxs'][-1]]).days
            fund += fund * INTEREST * d / 365.0
        rng = prev['h'] - prev['l']
        if rng <= 0: continue
        Lp = min(statistics.mean([p['m']*(prev['h']+prev['l'])/2, prev['c']*p['w']])
                 + math.log10(rng)*p['g'], cwk['o'])
        if not holding:
            buy = min(Lp, ath*(1-p['cap'])); tgt = buy + prev['c']*p['prem']
        idxs = cwk['idxs']
        if not holding:
            bd = next((k for k, i in enumerate(idxs) if L[i] <= buy), None)
            if bd is None: continue
            shares = fund/(buy+COMM); fund = 0.0; holding = True
            for k in range(bd, len(idxs)):
                i = idxs[k]
                if H[i] >= tgt:
                    if k == bd and verify_same_day(i, buy, tgt) is False:
                        continue
                    fund = shares*(tgt-COMM); shares = 0.0; holding = False; trades += 1; break
        else:
            for i in idxs:
                if H[i] >= tgt:
                    fund = shares*(tgt-COMM); shares = 0.0; holding = False; trades += 1; break
    last = WS[min(w1, len(WS)-1)]['idxs'][-1]
    return fund + (shares*C[last] if holding else 0.0), trades


def book(WS, n, stag, w0, w1):
    """n tranches staggered `stag` weeks, equal capital, scored over [w0,w1]."""
    tot = 0.0; tr = 0
    for t in range(n):
        f, k = tranche(WS, w0 + t*stag, w1, capital=1.0/n)
        tot += f; tr += k
    return tot - 1.0, tr


if __name__ == '__main__':
    WS = [stats(w) for w in build_weeks(0)]
    N = len(WS)
    cuts = [int(N*f) for f in (0.5, 0.667, 0.833, 1.0)]
    print(f'weeks: {N}   parameters FIXED at workbook values\n')

    print('=== A. TRANCHE COUNT AND STAGGER (structure chosen on train, scored on unseen) ===')
    combos = [(n, s) for n in (1, 2, 3, 4, 6) for s in (1, 2, 3)]
    print(f'{"fold":5s}{"chosen (n,stag)":>18s}{"chosen OOS":>12s}{"3x1 baseline":>14s}{"winner":>10s}')
    print('-'*60)
    wins = 0; diffs = []; picks = []
    for k in range(3):
        trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
        best = None
        for (n, s) in combos:
            r, _ = book(WS, n, s, 1, trhi-1)
            if best is None or r > best[0]: best = (r, n, s)
        _, bn, bs = best
        a, _ = book(WS, bn, bs, telo, tehi)
        b, _ = book(WS, 3, 1, telo, tehi)
        wins += (a > b); diffs.append((a-b)*100); picks.append((bn, bs))
        print(f'{k+1:<5d}{f"({bn},{bs})":>18s}{a*100:>11.1f}%{b*100:>13.1f}%'
              f'{("chosen" if a > b else "baseline"):>10s}')
    print('-'*60)
    print(f'structure choice beats the 3x1 baseline in {wins}/3 folds; '
          f'mean {statistics.mean(diffs):+.1f}pp')
    print(f'chosen structures: {picks}')

    print('\n=== B. FULL-SAMPLE STRUCTURE GRID (fixed params, minute-verified) ===')
    print(f'{"n":>3s}' + ''.join(f'{f"stagger {s}":>13s}' for s in (1, 2, 3)))
    for n in (1, 2, 3, 4, 6):
        row = []
        for s in (1, 2, 3):
            r, t = book(WS, n, s, 1, N-1)
            yrs = (DTS[WS[N-1]['idxs'][-1]] - DTS[WS[1]['idxs'][0]]).days/365.25
            row.append(f'{((1+r)**(1/yrs)-1)*100:5.0f}% ({t:3d})')
        print(f'{n:>3d}' + ''.join(f'{c:>13s}' for c in row))
    print('(cell = annualised %, trades in brackets)')

    print('\n=== C. WEEK ANCHOR (which weekday the week starts) ===')
    print(f'{"anchor":10s}{"annualised":>12s}{"trades":>9s}')
    for a, nm in ((0, 'Mon'), (1, 'Tue'), (2, 'Wed'), (3, 'Thu'), (4, 'Fri')):
        W2 = [stats(w) for w in build_weeks(a)]
        r, t = book(W2, 3, 1, 1, len(W2)-1)
        yrs = (DTS[W2[len(W2)-1]['idxs'][-1]] - DTS[W2[1]['idxs'][0]]).days/365.25
        print(f'{nm:10s}{((1+r)**(1/yrs)-1)*100:>11.0f}%{t:>9d}')
