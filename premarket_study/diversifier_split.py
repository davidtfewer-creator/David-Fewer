"""
The diversifier shortlist against the half-sample test that decided the seven-name book.

The earlier diversifier work fitted parameters on the whole sample and validated on tail slices.
That is a weaker test than the one just applied to the book: PLTR passed comparable checks and
still turned out to earn 365% over the untested first half and 3.1% over the tested second.

So the protocol here is the strict one:

    fit on the FIRST half only -> freeze -> score the second half

with the boundary at 2025-05-23, the same date used for the book. Nothing that scores the second
half has seen it. A full-sample fit is also reported, purely to show the size of the gap between
what fitting produces and what survives.

Basis: these names have no minute or 5-minute coverage except COIN, so same-day round trips are
resolved by the AT-OPEN floor -- an exit is allowed only where the bid is at or above the open,
which makes the fill provably first and any later high provably after it. That is a hard lower
bound rather than an estimate. COIN is additionally run on verified 5-minute fills to show what
the at-open floor costs.

Diversification is measured as the correlation of daily equity returns against the seven-name
book, since a name that clears 50% but moves with the book adds return without adding
diversification.
"""
import copy, datetime, math, statistics
from scipy.optimize import differential_evolution
from engine import Params, run_model
from optimise_candidates import BOUNDS, POLICY, PERTURB, NAMES, mp, bvec
from newfeed import load, NEW
import five_min

five_min.FILES.setdefault('COIN', '/root/.claude/uploads/'
                          '2d71f10a-e19f-51b2-8457-2cd547c34dff/882518ff-COIN_5min_Apr2024Aug2026.xlsx')

SHORT = ['MRNA', 'OXY', 'FSLR', 'DVN', 'COIN']
CUT = datetime.date(2025, 5, 23)
SEED = Params(capital=6_000_000, comm=0.005, interest=0.0314, stop_days=50,
              bayes_pct=0.75, years=2.2)


def run(data, vec, t, sde):
    return run_model(data['dts'], data['O'], data['H'], data['L'], data['C'], mp(vec, t),
                     collect=True, same_day_exit=sde)


def seg(data, vec, t, lo, hi, sde):
    r = run(data, vec, t, sde); fr = r.frames
    buys = sum(fr['t1']['Z'][lo:hi+1]) + sum(fr['t2']['Z'][lo:hi+1])
    eq = fr['equity']
    return (eq[hi]/eq[lo] - 1.0 if eq[lo] > 0 else -1.0), buys


def robust(data, vec, t, lo, hi, floor, sde):
    def one(v):
        rr, b = seg(data, v, t, lo, hi, sde)
        return -5.0 + b*1e-3 if b < floor else rr
    base = one(vec); s = []
    for i in POLICY:
        for f in PERTURB:
            v = list(vec); v[i] = min(max(v[i]*f, BOUNDS[i][0]), BOUNDS[i][1]); s.append(one(v))
    return 0.5*base + 0.5*sum(s)/len(s)


def optimise(data, t, lo, hi, floor, sde, maxiter=12, popsize=10, seed=42):
    res = differential_evolution(lambda v: -robust(data, v, t, lo, hi, floor, sde), BOUNDS,
                                 x0=bvec(t), init='sobol', seed=seed, maxiter=maxiter,
                                 popsize=popsize, mutation=(0.5, 1.0), recombination=0.7,
                                 tol=1e-3, polish=False, disp=False, updating='immediate',
                                 workers=1)
    return list(res.x)


def ann(r, dts, lo, hi):
    y = max((dts[hi] - dts[lo]).days/365.25, 1e-6)
    return (1+r)**(1/y) - 1 if r > -1 else -1.0


def book_returns():
    """Equal-weight daily returns of the five daily book names, verified, 75% Bayes."""
    from daily_window_split import data as bdata, params as bparams
    from five_min import make_checker as fm
    from minute_engine import make_checker as nv
    curves = []
    for s in ['RKLB', 'VST', 'TSM', 'MU', 'VRT']:
        dts, O, H, L, C = bdata[s]
        chk = nv(dts, O)[0] if s == 'NVDA' else fm(s, dts, O)[0]
        p = copy.copy(bparams[s]); p.bayes_pct = 0.75
        eq = run_model(dts, O, H, L, C, p, collect=True, same_day_exit=chk).frames['equity']
        curves.append((dts, eq))
    base = curves[0][0]
    out = {}
    for i in range(1, len(base)):
        rs = []
        for dts, eq in curves:
            try:
                j = dts.index(base[i])
            except ValueError:
                continue
            if j > 0 and eq[j-1] > 0: rs.append(eq[j]/eq[j-1] - 1)
        if rs: out[base[i]] = statistics.mean(rs)
    return out


def corr(a, b):
    n = len(a)
    if n < 3: return 0.0
    ma, mb = statistics.mean(a), statistics.mean(b)
    cov = sum((a[i]-ma)*(b[i]-mb) for i in range(n))
    va = sum((x-ma)**2 for x in a); vb = sum((x-mb)**2 for x in b)
    return cov/math.sqrt(va*vb) if va > 0 and vb > 0 else 0.0


if __name__ == '__main__':
    feed = load(NEW, SHORT)
    bk = book_returns()
    print(f'boundary {CUT}; fit on the first half only, score the second\n', flush=True)
    print(f'{"name":6s}{"fit 1st half":>14s}{"TESTED 2nd half":>18s}{"full-sample fit":>18s}'
          f'{"buys/yr":>9s}{"corr to book":>14s}', flush=True)
    print('-'*79, flush=True)
    rows = []
    for t in SHORT:
        dts, O, H, L, C = feed[t]
        N = len(C); k = next(i for i, d in enumerate(dts) if d >= CUT)
        tmpl = copy.copy(SEED); tmpl.years = (dts[-1]-dts[0]).days/365.25
        d = dict(dts=dts, O=O, H=H, L=L, C=C)

        # fit on the first half only, then score the unseen second half
        th = optimise(d, tmpl, 0, k-1, max(8, int(0.03*k)), 'at_open')
        r1, b1 = seg(d, th, tmpl, 0, k-1, 'at_open')
        r2, b2 = seg(d, th, tmpl, k, N-1, 'at_open')
        # full-sample fit, for the size of the gap only
        thf = optimise(d, tmpl, 0, N-1, max(8, int(0.03*N)), 'at_open')
        rf, bf = seg(d, thf, tmpl, 0, N-1, 'at_open')

        eq = run(d, th, tmpl, 'at_open').frames['equity']
        pa, pb = [], []
        for i in range(1, N):
            if dts[i] in bk and eq[i-1] > 0:
                pa.append(eq[i]/eq[i-1]-1); pb.append(bk[dts[i]])
        c = corr(pa, pb)
        a1 = ann(r1, dts, 0, k-1)*100; a2 = ann(r2, dts, k, N-1)*100
        af = ann(rf, dts, 0, N-1)*100
        rows.append((t, a1, a2, af, c, th))
        print(f'{t:6s}{a1:>13.1f}%{a2:>17.1f}%{af:>17.1f}%'
              f'{b2/max((dts[N-1]-dts[k]).days/365.25,1e-6):>9.0f}{c:>14.2f}', flush=True)
    print('-'*79, flush=True)

    print('\nCOIN on verified 5-minute fills, for what the at-open floor costs:', flush=True)
    dts, O, H, L, C = feed['COIN']
    N = len(C); k = next(i for i, d in enumerate(dts) if d >= CUT)
    tmpl = copy.copy(SEED); tmpl.years = (dts[-1]-dts[0]).days/365.25
    d = dict(dts=dts, O=O, H=H, L=L, C=C)
    chk = five_min.make_checker('COIN', dts, O)[0]
    th = optimise(d, tmpl, 0, k-1, max(8, int(0.03*k)), chk)
    r1, _ = seg(d, th, tmpl, 0, k-1, chk); r2, _ = seg(d, th, tmpl, k, N-1, chk)
    print(f'  fit 1st half {ann(r1,dts,0,k-1)*100:.1f}%   TESTED 2nd half '
          f'{ann(r2,dts,k,N-1)*100:.1f}%', flush=True)

    print('\nparameters fitted on the first half (the frozen set scored above):', flush=True)
    for t, a1, a2, af, c, th in rows:
        print(f'  {t:6s}' + '  '.join(f'{n}={v:.4g}' for n, v in zip(NAMES, th)), flush=True)
    print('DONE', flush=True)
