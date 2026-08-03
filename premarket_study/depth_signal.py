"""
Does a DEEPER fill earn a BIGGER bounce?  (the premise behind a fluid/state-dependent premium)

For every actual Bayes buy we measure, using only order-time information:
    depth = (fair_value - fill_price) / sigma        -- how many sigmas below fair we filled
and then the realised outcome:
    MFE_n = (max High over the next n sessions - fill) / fill   -- max favourable excursion
If MFE rises with depth, a premium that scales with depth has a real basis. If it is flat, the
idea has no edge and a fixed premium is correct.

Deciles reported, plus the same split for the OU tranche.
"""
import statistics
from stop_sweep import load_book
from engine import run_model

data, params, cached = load_book()


def analyse(stock, horizon=10):
    dts, O, H, L, C = data[stock]
    p = params[stock]
    r = run_model(dts, O, H, L, C, p, collect=True)
    fr = r.frames
    Lvl, Slp, W = fr['Lvl'], fr['Slp'], fr['W']
    X, AM = fr['X'], fr['AM']
    N = len(C)
    rows = {'Bayes': [], 'OU': []}
    for tkey, tname, bids in (('t1', 'Bayes', X), ('t2', 'OU', AM)):
        t = fr[tkey]
        for i in range(1, N):
            if t['Z'][i] != 1:
                continue
            bp = bids[i]
            if bp is None or W[i-1] <= 0:
                continue
            fair = Lvl[i-1] + Slp[i-1]
            depth = (fair - bp) / W[i-1]              # sigmas below fair value
            hi = min(i + horizon, N - 1)
            mfe = (max(H[i:hi+1]) - bp) / bp * 100    # % max favourable excursion
            rows[tname].append((depth, mfe))
    return rows


def deciles(pairs, nb=5):
    pairs = sorted(pairs)
    n = len(pairs)
    out = []
    for b in range(nb):
        lo, hi = b*n//nb, (b+1)*n//nb
        chunk = pairs[lo:hi]
        if not chunk:
            continue
        d = [c[0] for c in chunk]; m = [c[1] for c in chunk]
        out.append((statistics.mean(d), statistics.median(m), statistics.mean(m), len(chunk)))
    return out


if __name__ == '__main__':
    for stock in ('NVDA', 'RKLB', 'AVGO', 'VST'):
        rows = analyse(stock)
        print(f'\n===== {stock} =====')
        for tname in ('Bayes', 'OU'):
            pr = rows[tname]
            if len(pr) < 20:
                continue
            ds = [x[0] for x in pr]
            print(f'  {tname}: {len(pr)} fills, depth range {min(ds):.2f}..{max(ds):.2f} sigma '
                  f'(median {statistics.median(ds):.2f})')
            print(f'    {"depth bucket":>14s}{"mean depth":>12s}{"median MFE":>12s}{"mean MFE":>10s}{"n":>5s}')
            for md, medm, mm, n in deciles(pr):
                print(f'    {"":>14s}{md:>12.2f}{medm:>11.2f}%{mm:>9.2f}%{n:>5d}')
            # correlation
            xs = [x[0] for x in pr]; ys = [x[1] for x in pr]
            mx, my = statistics.mean(xs), statistics.mean(ys)
            cov = sum((xs[i]-mx)*(ys[i]-my) for i in range(len(xs)))
            vx = sum((x-mx)**2 for x in xs); vy = sum((y-my)**2 for y in ys)
            c = cov/(vx*vy)**0.5 if vx > 0 and vy > 0 else 0
            print(f'    corr(depth, MFE) = {c:+.2f}')
