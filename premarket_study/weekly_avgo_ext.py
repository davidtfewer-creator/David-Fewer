"""
Three checks on AVGO's optimised parameters, all of which qualify the headline.

The first grid put AVGO's optimum at prem = 0.1000, which was that grid's upper bound -- an
optimum sitting on a boundary is not an optimum, it is a statement about where the search stopped.
These checks ask:

  1  with the grid extended to prem = 0.20, is the optimum interior, and how wide is it
  2  does the walk-forward verdict survive the change of grid -- if a conclusion depends on the
     resolution and range of an arbitrary grid, it is not a conclusion
  3  what the high-premium configuration costs in holding period, since the model carries no stop
  4  how much of the ending value is an open mark-to-market position rather than realised cash

Run against weekly_avgo.py, which holds the data, the 5-minute verifier and the segment scorer.
"""
import statistics
import weekly_avgo as A
from weekly_avgo import seg, ann, pr, N, WS, DTS, CHECK
from weekly_mr import P

H, L, C = A.H, A.L, A.C
CAPS = [round(0.02 + 0.005*i, 4) for i in range(31)]       # 0.020 .. 0.170
PREMS = [round(0.02 + 0.005*i, 5) for i in range(37)]      # 0.020 .. 0.200
COMM, INTEREST = 0.005, 0.0314


def walk(p, collect_holds=False):
    """Replay the three tranches; return ending cash, ending position value, hold lengths."""
    cash = pos = 0.0; hold_days = []; still = 0
    for t0 in range(3):
        fund, shares, holding = 1/3, 0.0, False
        buy = tgt = None; entry = None
        ath = max(H[i] for i in WS[1 + t0]['idxs'])
        for wi in range(2 + t0, N):
            prev, cwk = WS[wi-1], WS[wi]
            ath = max(ath, prev['h'])
            if prev['h'] - prev['l'] <= 0: continue
            if not holding:
                fund += fund*INTEREST*(DTS[cwk['idxs'][-1]] - DTS[prev['idxs'][-1]]).days/365.0
                buy = min(cwk['o'], ath*(1 - p['cap'])); tgt = buy + prev['c']*p['prem']
            idxs = cwk['idxs']
            if not holding:
                bd = next((k for k, i in enumerate(idxs) if L[i] <= buy), None)
                if bd is None: continue
                shares = fund/(buy + COMM); fund = 0.0; holding = True; entry = DTS[idxs[bd]]
                for k in range(bd, len(idxs)):
                    i = idxs[k]
                    if H[i] >= tgt:
                        if k == bd and CHECK(i, buy, tgt) is False: continue
                        fund = shares*(tgt - COMM); shares = 0.0; holding = False
                        hold_days.append((DTS[i] - entry).days); break
            else:
                for i in idxs:
                    if H[i] >= tgt:
                        fund = shares*(tgt - COMM); shares = 0.0; holding = False
                        hold_days.append((DTS[i] - entry).days); break
        last = WS[N-1]['idxs'][-1]
        cash += fund; pos += shares*C[last]; still += holding
    return cash, pos, hold_days, still


if __name__ == '__main__':
    print('=== 1. EXTENDED GRID: interior optimum, or an artefact of the bound? ===', flush=True)
    best = None
    for c in CAPS:
        for q in PREMS:
            r, t = seg(pr(c, q), 1, N-1)
            if t < 20: continue
            if best is None or r > best[0]: best = (r, c, q, t)
    r, bc, bq, bt = best
    print(f'  best with prem up to 0.200: cap {bc:.3f} prem {bq:.4f} -> '
          f'{ann(r,1,N-1)*100:.1f}%, {bt} trades', flush=True)
    print(f'  premium profile at cap {bc:.3f}:', flush=True)
    for q in (0.04, 0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20):
        r2, t2 = seg(pr(bc, q), 1, N-1)
        print(f'    prem {q:.2f}: {ann(r2,1,N-1)*100:5.0f}%  ({t2:3d} trades)', flush=True)

    print('\n=== 2. WALK-FORWARD ON THE EXTENDED GRID ===', flush=True)
    cuts = [int(N*f) for f in (0.5, 0.667, 0.833, 1.0)]
    picks = []; wins = 0; d = []
    for k in range(3):
        trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
        b = None
        for c in CAPS:
            for q in PREMS:
                r2, t2 = seg(pr(c, q), 1, trhi-1)
                if t2 < 10: continue
                if b is None or r2 > b[0]: b = (r2, c, q)
        _, c, q = b; picks.append((c, q))
        a_, _ = seg(pr(c, q), telo, tehi); bb, _ = seg(P, telo, tehi)
        wins += (a_ > bb); d.append((a_-bb)*100)
        print(f'  fold {k+1}: fitted cap {c:.3f} prem {q:.3f} -> OOS {a_*100:6.1f}%   '
              f'NVDA params {bb*100:6.1f}%   {"fitted" if a_ > bb else "NVDA params"}', flush=True)
    print(f'  fitted beats in {wins}/3; mean {statistics.mean(d):+.1f}pp', flush=True)
    cc = statistics.median(p[0] for p in picks); cq = statistics.median(p[1] for p in picks)
    w2 = 0; d2 = []
    for k in range(3):
        telo, tehi = cuts[k], cuts[k+1]-1
        a_, _ = seg(pr(cc, cq), telo, tehi); bb, _ = seg(P, telo, tehi)
        w2 += (a_ > bb); d2.append((a_-bb)*100)
    print(f'  consensus cap {cc:.3f} prem {cq:.3f}: beats in {w2}/3, '
          f'mean {statistics.mean(d2):+.1f}pp', flush=True)

    print('\n=== 3 & 4. HOLDING PERIOD AND TERMINAL MARK (no stop loss in this model) ===',
          flush=True)
    for lbl, p in (('NVDA params', P), ('AVGO prem 0.10', pr(0.080, 0.100)),
                   ('AVGO consensus', pr(cc, cq))):
        cash, pos, hd, still = walk(p)
        hd.sort(); tot = cash + pos
        print(f'  {lbl:16s} {ann(tot-1,1,N-1)*100:5.1f}% ann   n={len(hd):3d}  '
              f'median hold {hd[len(hd)//2]:4d}d  75th {hd[int(len(hd)*0.75)]:4d}d  '
              f'95th {hd[int(len(hd)*0.95)]:4d}d  max {max(hd):4d}d', flush=True)
        print(f'  {"":16s} ending value {tot:.2f}x = cash {cash:.2f} + open position {pos:.2f} '
              f'({pos/tot*100:.0f}%); {still}/3 tranches still holding', flush=True)
        print(f'  {"":16s} open position marked 20% lower -> '
              f'{ann(cash + pos*0.8 - 1, 1, N-1)*100:.1f}% ann', flush=True)
    print('DONE', flush=True)
