"""
Buy/sell levels anchored to the opening price of each 3-month window.

Fixed dollar levels fail because the trading range moves. Anchoring to P0 -- the open on the
first day of the period -- makes them relative:
    buy  at  a * P0
    sell at  b * P0
The question is whether the optimal (a, b) RATIOS are stable across windows. If they cluster,
the rule is usable; if they scatter, the problem has merely been restated in relative form.

Protocol: split the sample into consecutive 3-month windows, find the best (a,b) in each, then
test whether a pair chosen on earlier windows works on later ones.
"""
import datetime, statistics
from stop_sweep import load_book

data, params, cached = load_book()
COMM = 0.005


def windows(dts, months=3):
    """Consecutive ~3-month index ranges."""
    out, start = [], 0
    for i in range(1, len(dts)):
        if (dts[i] - dts[start]).days >= months*30.4:
            out.append((start, i-1)); start = i
    if len(dts)-start > 20: out.append((start, len(dts)-1))
    return out


def sim(stock, a, b, lo, hi):
    """Return (window return, trips) buying at a*P0 and selling at b*P0."""
    dts, O, H, L, C = data[stock]
    P0 = O[lo]
    B, S = a*P0, b*P0
    if S <= B: return -1.0, 0
    cap, sh, hold, n = 1.0, 0.0, False, 0
    for i in range(lo, hi+1):
        if not hold and L[i] <= B:
            px = min(B, O[i]); sh = cap/(px+COMM); cap = 0.0; hold = True
            if H[i] >= S: cap = sh*(S-COMM); hold = False; n += 1
        elif hold and H[i] >= S:
            cap = sh*(S-COMM); hold = False; n += 1
    if hold: cap = sh*C[hi]
    return cap-1.0, n


GRID_A = [round(x, 3) for x in [0.86+0.01*i for i in range(16)]]      # 0.86 .. 1.01
GRID_B = [round(x, 3) for x in [0.94+0.01*i for i in range(22)]]      # 0.94 .. 1.15


def best_pair(stock, lo, hi, min_trips=2):
    best = None
    for a in GRID_A:
        for b in GRID_B:
            if b <= a + 0.01: continue
            r, n = sim(stock, a, b, lo, hi)
            if n < min_trips: continue
            if best is None or r > best[0]: best = (r, a, b, n)
    return best


if __name__ == '__main__':
    stock = 'NVDA'
    dts = data[stock][0]
    wins = windows(dts)
    print(f'=== {stock}: best (a,b) ratios per 3-month window (anchored to that window\'s open) ===\n')
    print(f'{"window":26s}{"P0":>8s}{"buy a":>8s}{"sell b":>8s}{"spread":>9s}{"trips":>7s}{"return":>9s}')
    print('-'*75)
    picks = []
    for (lo, hi) in wins:
        bp = best_pair(stock, lo, hi)
        P0 = data[stock][1][lo]
        if bp is None:
            print(f'{str(dts[lo])+" -> "+str(dts[hi]):26s}{P0:>8.0f}{"-":>8s}{"-":>8s}{"-":>9s}{0:>7d}{"-":>9s}')
            continue
        r, a, b, n = bp
        picks.append((a, b))
        print(f'{str(dts[lo])+" -> "+str(dts[hi]):26s}{P0:>8.0f}{a:>8.2f}{b:>8.2f}'
              f'{(b/a-1)*100:>8.1f}%{n:>7d}{r*100:>8.1f}%')
    print('-'*75)
    if picks:
        print(f'optimal a: {min(p[0] for p in picks):.2f} - {max(p[0] for p in picks):.2f}   '
              f'(median {statistics.median(p[0] for p in picks):.2f})')
        print(f'optimal b: {min(p[1] for p in picks):.2f} - {max(p[1] for p in picks):.2f}   '
              f'(median {statistics.median(p[1] for p in picks):.2f})')

    # ---- out-of-sample: choose on the first half of windows, apply to the rest ----
    print('\n=== OUT OF SAMPLE: pair chosen on early windows, applied to later ones ===')
    half = len(wins)//2
    cand = {}
    for a in GRID_A:
        for b in GRID_B:
            if b <= a + 0.01: continue
            tot = 0.0; ok = True
            for (lo, hi) in wins[:half]:
                r, n = sim(stock, a, b, lo, hi)
                if n < 1: ok = False
                tot += r
            if ok: cand[(a, b)] = tot
    if cand:
        (ba, bb) = max(cand, key=cand.get)
        print(f'best pair on the EARLY windows: buy {ba:.2f}*P0, sell {bb:.2f}*P0 '
              f'(spread {(bb/ba-1)*100:.1f}%)')
        print(f'\n{"later window":26s}{"trips":>7s}{"return":>9s}{"buy&hold":>10s}')
        print('-'*52)
        tot = bh = 0
        for (lo, hi) in wins[half:]:
            r, n = sim(stock, ba, bb, lo, hi)
            h = data[stock][4][hi]/data[stock][4][lo]-1
            tot += r; bh += h
            print(f'{str(dts[lo])+" -> "+str(dts[hi]):26s}{n:>7d}{r*100:>8.1f}%{h*100:>9.1f}%')
        print('-'*52)
        print(f'{"MEAN":26s}{"":>7s}{tot/len(wins[half:])*100:>8.1f}%{bh/len(wins[half:])*100:>9.1f}%')
