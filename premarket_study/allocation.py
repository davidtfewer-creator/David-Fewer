"""
Capital allocation across the book, tested for robustness rather than fitted.

The naive move is to weight by verified return. That is only sound if past return predicts
future return. We test that directly (rank correlation between adjacent windows), then compare
allocation schemes out of sample: weights are formed on a training window and applied to the
next unseen window.

Schemes: equal weight; return-weighted; risk-adjusted (return/vol, the Allocation sheet's
logic); inverse-volatility; inverse-drawdown. Capped and floored variants included, since
uncapped return-weighting concentrates the book in one name.
"""
import copy, statistics, math
from stop_sweep import load_book
from engine import run_model
from five_min import make_checker as fm
from minute_engine import make_checker as nv

data, params, cached = load_book()
STOCKS = list(data)
CHK = {}
for s in STOCKS:
    dts, O, H, L, C = data[s]
    CHK[s] = nv(dts, O)[0] if s == 'NVDA' else fm(s, dts, O)[0]

BAYES = 0.75                     # the validated tilt
CAP, FLOOR = 0.20, 0.02


def equity(s):
    dts, O, H, L, C = data[s]
    p = copy.copy(params[s]); p.bayes_pct = BAYES
    return run_model(dts, O, H, L, C, p, collect=True, same_day_exit=CHK[s]).frames['equity']


EQ = {s: equity(s) for s in STOCKS}
N = min(len(EQ[s]) for s in STOCKS)


def stats(s, lo, hi):
    eq = EQ[s]
    if eq[lo] <= 0: return -1.0, 1.0, 1.0
    ret = eq[hi]/eq[lo] - 1
    r = [eq[i]/eq[i-1]-1 for i in range(lo+1, hi+1) if eq[i-1] > 0]
    vol = statistics.pstdev(r)*math.sqrt(252) if len(r) > 2 else 1.0
    peak = -1e30; dd = 0
    for i in range(lo, hi+1):
        peak = max(peak, eq[i])
        if peak > 0: dd = max(dd, (peak-eq[i])/peak)
    return ret, max(vol, 1e-6), max(dd, 1e-6)


def normalise(w):
    w = {s: max(v, 0.0) for s, v in w.items()}
    t = sum(w.values()) or 1.0
    w = {s: v/t for s, v in w.items()}
    # apply cap and floor, then renormalise (single pass is adequate here)
    w = {s: min(max(v, FLOOR), CAP) for s, v in w.items()}
    t = sum(w.values())
    return {s: v/t for s, v in w.items()}


def weights(scheme, lo, hi):
    st = {s: stats(s, lo, hi) for s in STOCKS}
    if scheme == 'equal':
        return {s: 1/len(STOCKS) for s in STOCKS}
    if scheme == 'return':
        return normalise({s: max(st[s][0], 0) for s in STOCKS})
    if scheme == 'riskadj':
        return normalise({s: max(st[s][0], 0)/st[s][1] for s in STOCKS})
    if scheme == 'invvol':
        return normalise({s: 1/st[s][1] for s in STOCKS})
    if scheme == 'invdd':
        return normalise({s: 1/st[s][2] for s in STOCKS})
    raise ValueError(scheme)


def book(w, lo, hi):
    """Weighted book return over [lo,hi], rebalanced at lo."""
    tot = 0.0
    for s in STOCKS:
        r, _, _ = stats(s, lo, hi)
        tot += w[s] * r
    return tot


if __name__ == '__main__':
    print('=== (1) DOES PAST RETURN PREDICT FUTURE RETURN? ===')
    print('Spearman rank correlation between adjacent windows (verified, 75% Bayes)\n')
    cuts = [0, N//4, N//2, 3*N//4, N-1]
    def rank(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        rk = [0]*len(xs)
        for pos, i in enumerate(order): rk[i] = pos
        return rk
    def spear(a, b):
        ra, rb = rank(a), rank(b); n = len(a)
        ma, mb = statistics.mean(ra), statistics.mean(rb)
        cov = sum((ra[i]-ma)*(rb[i]-mb) for i in range(n))
        va = sum((x-ma)**2 for x in ra); vb = sum((x-mb)**2 for x in rb)
        return cov/math.sqrt(va*vb) if va > 0 and vb > 0 else 0
    for k in range(len(cuts)-2):
        a = [stats(s, cuts[k], cuts[k+1])[0] for s in STOCKS]
        b = [stats(s, cuts[k+1], cuts[k+2])[0] for s in STOCKS]
        print(f'  window {k+1} -> {k+2}:  rho = {spear(a,b):+.2f}')
    # also volatility persistence, for contrast
    va = [stats(s, 0, N//2)[1] for s in STOCKS]
    vb = [stats(s, N//2, N-1)[1] for s in STOCKS]
    print(f'\n  volatility persistence (1st half -> 2nd half): rho = {spear(va,vb):+.2f}')

    print('\n=== (2) ALLOCATION SCHEMES, OUT OF SAMPLE ===')
    print('weights formed on the training window, applied to the next unseen window\n')
    SCH = ['equal', 'return', 'riskadj', 'invvol', 'invdd']
    folds = [(0, N//2, N-1), (0, int(N*0.667), int(N*0.833)), (0, int(N*0.833), N-1)]
    print(f'{"scheme":10s}' + ''.join(f'{f"fold {i+1}":>10s}' for i in range(len(folds))) + f'{"mean":>10s}')
    print('-'*52)
    res = {}
    for sc in SCH:
        rs = []
        for (a, b, c) in folds:
            w = weights(sc, a, b-1)
            rs.append(book(w, b, c)*100)
        res[sc] = statistics.mean(rs)
        print(f'{sc:10s}' + ''.join(f'{r:>9.1f}%' for r in rs) + f'{res[sc]:>9.1f}%')
    best = max(res, key=res.get)
    print(f'\nbest out-of-sample scheme: {best} ({res[best]:.1f}% mean)')

    print('\n=== (3) RECOMMENDED WEIGHTS (full sample, best scheme + equal for reference) ===')
    wf = weights(best, 0, N-1); we = weights('equal', 0, N-1)
    print(f'{"stock":6s}{"verified ret":>14s}{"vol":>8s}{best:>10s}{"equal":>8s}')
    for s in sorted(STOCKS, key=lambda x: -wf[x]):
        r, v, d = stats(s, 0, N-1)
        print(f'{s:6s}{r*100:>13.0f}%{v*100:>7.0f}%{wf[s]*100:>9.1f}%{we[s]*100:>7.1f}%')
