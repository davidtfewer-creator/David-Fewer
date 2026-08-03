"""
Better formulation of the fluid-premium idea.

The fill DEPTH is near-constant (the bid is normally fair - k*sigma), so it carries no signal.
What genuinely varies is how far the market kept falling AFTER we filled -- the severity of the
day's dislocation. Test two conditioning variables, both observable by the close of the fill day
(so a live GTC sell order could be amended that evening):

    overshoot = (fill - Low_i)  / sigma      how far below our fill the day traded
    closegap  = (fill - Close_i)/ fill * 100 did it close below our fill, and by how much

Outcome: MFE measured from the NEXT session onward (so the fill day's own move cannot
contaminate the result):
    MFE = (max High over sessions i+1..i+n - fill) / fill

If deeply-dislocated fills bounce further, a premium that scales with dislocation has a basis.
"""
import statistics
from stop_sweep import load_book
from engine import run_model

data, params, cached = load_book()
STOCKS = ['NVDA', 'TSM', 'TSLA', 'VRT', 'VST', 'AVGO', 'PLTR', 'RKLB', 'SOFI', 'SPOT']


def corr(xs, ys):
    n = len(xs)
    if n < 5: return 0.0
    mx, my = statistics.mean(xs), statistics.mean(ys)
    cov = sum((xs[i]-mx)*(ys[i]-my) for i in range(n))
    vx = sum((x-mx)**2 for x in xs); vy = sum((y-my)**2 for y in ys)
    return cov/(vx*vy)**0.5 if vx > 0 and vy > 0 else 0.0


def analyse(stock, horizon=10):
    dts, O, H, L, C = data[stock]
    p = params[stock]
    fr = run_model(dts, O, H, L, C, p, collect=True).frames
    W, X, AM = fr['W'], fr['X'], fr['AM']
    N = len(C)
    out = {}
    for tkey, tname, bids in (('t1', 'Bayes', X), ('t2', 'OU', AM)):
        t = fr[tkey]; rows = []
        for i in range(1, N - 1):
            if t['Z'][i] != 1:
                continue
            bp = bids[i]
            if bp is None or W[i-1] <= 0:
                continue
            overshoot = (bp - L[i]) / W[i-1]              # sigmas the day fell below our fill
            closegap = (bp - C[i]) / bp * 100             # % it closed below our fill
            hi = min(i + 1 + horizon, N - 1)
            if hi <= i:
                continue
            mfe = (max(H[i+1:hi+1]) - bp) / bp * 100      # bounce from the NEXT day onward
            rows.append((overshoot, closegap, mfe))
        out[tname] = rows
    return out


def buckets(rows, key, nb=4):
    rows = sorted(rows, key=lambda r: r[key])
    n = len(rows); res = []
    for b in range(nb):
        lo, hi = b*n//nb, (b+1)*n//nb
        ch = rows[lo:hi]
        if ch:
            res.append((statistics.mean(r[key] for r in ch),
                        statistics.median(r[2] for r in ch),
                        statistics.mean(r[2] for r in ch), len(ch)))
    return res


if __name__ == '__main__':
    print('Does a deeper DISLOCATION on the fill day predict a bigger bounce afterwards?')
    print('(MFE measured from the next session onward, 10-day horizon)\n')
    agg = {'Bayes': {'os': [], 'cg': []}, 'OU': {'os': [], 'cg': []}}
    print(f'{"stock":6s}{"tranche":9s}{"n":>5s}{"corr(overshoot,MFE)":>21s}{"corr(closegap,MFE)":>20s}')
    print('-' * 61)
    for s in STOCKS:
        a = analyse(s)
        for tname in ('Bayes', 'OU'):
            rows = a[tname]
            if len(rows) < 20:
                continue
            c1 = corr([r[0] for r in rows], [r[2] for r in rows])
            c2 = corr([r[1] for r in rows], [r[2] for r in rows])
            agg[tname]['os'].append(c1); agg[tname]['cg'].append(c2)
            print(f'{s:6s}{tname:9s}{len(rows):>5d}{c1:>21.2f}{c2:>20.2f}')
    print('-' * 61)
    for tname in ('Bayes', 'OU'):
        o = agg[tname]['os']; g = agg[tname]['cg']
        pos_o = sum(1 for x in o if x > 0); pos_g = sum(1 for x in g if x > 0)
        print(f'{tname:9s} mean corr: overshoot {statistics.mean(o):+.2f} ({pos_o}/{len(o)} positive), '
              f'closegap {statistics.mean(g):+.2f} ({pos_g}/{len(g)} positive)')

    print('\n=== pooled bucket view (all names, Bayes) ===')
    pooled = []
    for s in STOCKS:
        pooled += analyse(s)['Bayes']
    print(f'{"mean overshoot(sig)":>21s}{"median MFE":>12s}{"mean MFE":>10s}{"n":>6s}')
    for md, medm, mm, n in buckets(pooled, 0):
        print(f'{md:>21.2f}{medm:>11.2f}%{mm:>9.2f}%{n:>6d}')
    print(f'\n{"mean closegap(%)":>21s}{"median MFE":>12s}{"mean MFE":>10s}{"n":>6s}')
    for md, medm, mm, n in buckets(pooled, 1):
        print(f'{md:>21.2f}{medm:>11.2f}%{mm:>9.2f}%{n:>6d}')
