"""
Buy/sell levels anchored to the post-earnings price.

Calendar quarters are arbitrary. Earnings is the natural regime boundary: the stock gaps to a
new level, then oscillates around it until the next report. A reference set shortly AFTER
earnings should therefore stay relevant for the whole inter-earnings period, unlike a calendar
anchor that goes stale.

Window: starts the first Monday at least `lag_days` after the earnings reaction, ends on the
day before the next earnings reaction. P0 = the open on the window's first session.
    buy  at  a * P0        sell at  b * P0

Reports the best (a,b) per window, whether those ratios cluster, and an out-of-sample test with
the pair chosen on earlier windows applied to later ones.
"""
import datetime, statistics
from stop_sweep import load_book

data, params, cached = load_book()
COMM = 0.005
dts, O, H, L, C = data['NVDA']

# earnings reactions detected from the largest overnight gap in each reporting window
EARN = [datetime.date(2024, 5, 23), datetime.date(2024, 8, 29), datetime.date(2024, 11, 21),
        datetime.date(2025, 2, 27), datetime.date(2025, 5, 29), datetime.date(2025, 8, 22),
        datetime.date(2025, 11, 20), datetime.date(2026, 2, 18), datetime.date(2026, 5, 18)]


def build_windows(lag_days=7):
    """(start_idx, end_idx) per inter-earnings period, starting the first Monday >= lag."""
    out = []
    for k, e in enumerate(EARN):
        target = e + datetime.timedelta(days=lag_days)
        while target.weekday() != 0:                       # advance to Monday
            target += datetime.timedelta(days=1)
        nxt = EARN[k+1] if k+1 < len(EARN) else dts[-1] + datetime.timedelta(days=1)
        idx = [i for i in range(len(dts)) if target <= dts[i] < nxt]
        if len(idx) >= 20:
            out.append((idx[0], idx[-1]))
    return out


def sim(a, b, lo, hi):
    P0 = O[lo]; B, S = a*P0, b*P0
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


GA = [round(0.88+0.01*i, 3) for i in range(14)]        # 0.88 .. 1.01
GB = [round(0.94+0.01*i, 3) for i in range(20)]        # 0.94 .. 1.13


def best(lo, hi, min_trips=2):
    b_ = None
    for a in GA:
        for bb in GB:
            if bb <= a + 0.01: continue
            r, n = sim(a, bb, lo, hi)
            if n < min_trips: continue
            if b_ is None or r > b_[0]: b_ = (r, a, bb, n)
    return b_


if __name__ == '__main__':
    for lag in (7, 14):
        W = build_windows(lag)
        print(f'\n=== EARNINGS-ANCHORED WINDOWS (start Monday >= {lag} days after the reaction) ===')
        print(f'{"window":26s}{"P0":>8s}{"buy a":>7s}{"sell b":>8s}{"spread":>9s}{"trips":>7s}{"return":>9s}')
        print('-'*74)
        picks = []
        for (lo, hi) in W:
            bp = best(lo, hi)
            if bp is None:
                print(f'{str(dts[lo])+" -> "+str(dts[hi]):26s}{O[lo]:>8.0f}{"-":>7s}{"-":>8s}{"-":>9s}{0:>7d}{"-":>9s}')
                continue
            r, a, b, n = bp
            picks.append((a, b))
            print(f'{str(dts[lo])+" -> "+str(dts[hi]):26s}{O[lo]:>8.0f}{a:>7.2f}{b:>8.2f}'
                  f'{(b/a-1)*100:>8.1f}%{n:>7d}{r*100:>8.1f}%')
        print('-'*74)
        if picks:
            print(f'buy  a: {min(p[0] for p in picks):.2f}-{max(p[0] for p in picks):.2f} '
                  f'(median {statistics.median(p[0] for p in picks):.2f})   '
                  f'sell b: {min(p[1] for p in picks):.2f}-{max(p[1] for p in picks):.2f} '
                  f'(median {statistics.median(p[1] for p in picks):.2f})')

    # out-of-sample on the 7-day-lag windows
    W = build_windows(7)
    half = len(W)//2
    cand = {}
    for a in GA:
        for b in GB:
            if b <= a + 0.01: continue
            tot, ok = 0.0, True
            for (lo, hi) in W[:half]:
                r, n = sim(a, b, lo, hi)
                if n < 1: ok = False
                tot += r
            if ok: cand[(a, b)] = tot
    print('\n=== OUT OF SAMPLE (pair chosen on the earlier windows) ===')
    if cand:
        ba, bb = max(cand, key=cand.get)
        print(f'chosen: buy {ba:.2f}*P0, sell {bb:.2f}*P0  (spread {(bb/ba-1)*100:.1f}%)\n')
        print(f'{"later window":26s}{"trips":>7s}{"return":>9s}')
        print('-'*42)
        tot = 0; nz = 0
        for (lo, hi) in W[half:]:
            r, n = sim(ba, bb, lo, hi)
            tot += r; nz += (n == 0)
            print(f'{str(dts[lo])+" -> "+str(dts[hi]):26s}{n:>7d}{r*100:>8.1f}%')
        print('-'*42)
        print(f'{"MEAN per window":26s}{"":>7s}{tot/len(W[half:])*100:>8.1f}%'
              f'   ({nz} dormant of {len(W[half:])})')
