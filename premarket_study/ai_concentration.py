"""
How much of the book is one trade, and do GM, VLO, CF and ALNY actually reduce that?

The marginal test scored these four on return and drawdown and rejected them. That answered the
wrong question. The book is TSM (semis), VRT (data-centre cooling), VST (power for data centres)
and MU (HBM memory) -- four expressions of one theme -- plus RKLB. If the theme breaks they break
together, and a return cost is a reasonable price for not owning that.

So the measurements here are about exposure, not performance:

  UNDERLYING CO-MOVEMENT, not strategy co-movement. The strategy sits in cash much of the time,
  which mutes every correlation and makes the book look more diversified than the assets are. The
  thematic exposure lives in the shares; correlations of both are reported so the gap is visible.

  BETA TO THE THEME. An AI factor is built as the equal-weight daily return of TSM, VRT, VST and
  MU -- the book's own AI-adjacent names, since no index is available here -- and every name is
  regressed on it. TSM alone is reported as a check that the composite is not an artefact of how
  it was assembled. RKLB is measured, not assumed: it is not an AI name but it is the same
  high-beta growth risk appetite, and the question is whether it behaves like one.

  VARIANCE SHARE. The headline. Regress the book's daily STRATEGY returns on the factor: R-squared
  is the fraction of book variance that is the AI trade. Five-name against nine-name is the number
  that says whether the reliance has actually fallen.

  THE STRESS WINDOWS. Concentration is a claim about bad days, so it is tested on bad days. The
  worst drawdown windows of the AI factor within the sample are located automatically rather than
  chosen, and both books are run through each one.
"""
import copy
import datetime
import math
import statistics

from engine import run_model
from optimise_candidates import mp
from newdiv import (BOOK, BUF_RESID, CAND, CUT, SEED, book_curves, daily_from_5min,
                    daily_returns, stats)
import five_min

AI = ['TSM', 'VRT', 'VST', 'MU']
FROZEN = {
    'GM':   [0.2011, 0.2907, 0.04228, 0.3827, 0.005803, 0.03368, 0.6041, 0.009885, 0.09131, 41.42],
    'VLO':  [1.441, 0.7016, 0.02011, 0.945, 0.02321, 0.05922, 1.799, 0.02552, 0.08021, 116.7],
    'CF':   [0.8737, 0.4777, 0.004598, 1.838, 0.02545, 0.06327, 0.8036, 0.05159, 0.09228, 65.56],
    'ALNY': [0.7795, 0.1431, 0.02285, 1.266, 0.03147, 0.006668, 2.009, 0.04964, 0.03783, 130.9],
}


def underlying():
    """date -> return, per name, from closes."""
    from daily_window_split import data as bdata
    from mu_rerun import from_workbook
    bdata = dict(bdata)
    bdata['MU'] = from_workbook()
    out = {}
    for s in BOOK:
        dts, O, H, L, C = bdata[s]
        out[s] = {dts[i]: C[i]/C[i-1]-1 for i in range(1, len(C)) if C[i-1] > 0}
    for t in CAND:
        dts, O, H, L, C = daily_from_5min(t)
        out[t] = {dts[i]: C[i]/C[i-1]-1 for i in range(1, len(C)) if C[i-1] > 0}
    return out


def cand_curve(t):
    dts, O, H, L, C = daily_from_5min(t)
    tmpl = copy.copy(SEED)
    tmpl.years = (dts[-1]-dts[0]).days/365.25
    chk = five_min.make_checker(t, dts, O)[0]
    eq = run_model(dts, O, H, L, C, mp(FROZEN[t], tmpl), collect=True,
                   same_day_exit=chk, ou_sigma='resid').frames['equity']
    return dts, eq


def pair(a, b):
    ds = sorted(set(a) & set(b))
    return [a[d] for d in ds], [b[d] for d in ds], ds


def corr(x, y):
    n = len(x)
    if n < 3:
        return float('nan')
    mx, my = statistics.mean(x), statistics.mean(y)
    cov = sum((x[i]-mx)*(y[i]-my) for i in range(n))
    vx = sum((v-mx)**2 for v in x)
    vy = sum((v-my)**2 for v in y)
    return cov/math.sqrt(vx*vy) if vx > 0 and vy > 0 else float('nan')


def regress(y, x):
    """beta and R-squared of y on x."""
    n = len(x)
    mx, my = statistics.mean(x), statistics.mean(y)
    sxx = sum((v-mx)**2 for v in x)
    sxy = sum((x[i]-mx)*(y[i]-my) for i in range(n))
    if sxx <= 0:
        return float('nan'), float('nan')
    b = sxy/sxx
    a = my - b*mx
    ssr = sum((y[i] - (a + b*x[i]))**2 for i in range(n))
    sst = sum((v-my)**2 for v in y)
    return b, (1 - ssr/sst if sst > 0 else float('nan'))


def held(curves, start=None):
    """Equal capital per name at `start`, each compounding independently. No rebalancing."""
    rets = [daily_returns(d, e) for d, e in curves]
    dates = sorted(set().union(*[set(r) for r in rets]))
    if start:
        dates = [d for d in dates if d >= start]
    n = len(curves)
    pots = [1.0/n]*n
    eq = [1.0]
    for d in dates:
        for j, r in enumerate(rets):
            if d in r:
                pots[j] *= (1 + r[d])
        eq.append(sum(pots))
    return dates, eq


def worst_windows(fac_dates, fac, k=3, min_len=5):
    """The k deepest non-overlapping peak-to-trough windows of the factor's cumulative index."""
    idx, v = [1.0], 1.0
    for r in fac:
        v *= (1+r)
        idx.append(v)
    used = set()
    out = []
    for _ in range(k):
        best = None
        for i in range(len(idx)):
            if i in used:
                continue
            peak = idx[i]
            for j in range(i+min_len, len(idx)):
                if j in used:
                    break
                dd = 1 - idx[j]/peak
                if best is None or dd > best[0]:
                    best = (dd, i, j)
        if not best or best[0] <= 0:
            break
        dd, i, j = best
        used |= set(range(i, j+1))
        out.append((dd, fac_dates[max(i-1, 0)], fac_dates[min(j-1, len(fac_dates)-1)]))
    return out


if __name__ == '__main__':
    U = underlying()
    names = BOOK + list(CAND)

    # ---- the AI factor, from the book's own AI-adjacent names
    dates = sorted(set.intersection(*[set(U[s]) for s in AI]))
    fac = [statistics.mean(U[s][d] for s in AI) for d in dates]
    facd = dict(zip(dates, fac))

    print('=== underlying daily-return correlation (the shares, not the strategy) ===',
          flush=True)
    print(f'{"":6s}' + ''.join(f'{n:>7s}' for n in names), flush=True)
    for a in names:
        row = ''
        for b in names:
            x, y, _ = pair(U[a], U[b])
            row += f'{corr(x, y):>7.2f}'
        print(f'{a:6s}{row}', flush=True)

    def avg_pair(group):
        vs = []
        for i, a in enumerate(group):
            for b in group[i+1:]:
                x, y, _ = pair(U[a], U[b])
                vs.append(corr(x, y))
        return statistics.mean(vs)

    print(f'\n  average pairwise correlation, current five names   {avg_pair(BOOK):.2f}', flush=True)
    print(f'  average pairwise correlation, the four AI names    {avg_pair(AI):.2f}', flush=True)
    print(f'  average pairwise correlation, proposed nine        {avg_pair(names):.2f}', flush=True)
    print(f'  average pairwise, the four candidates alone        {avg_pair(list(CAND)):.2f}',
          flush=True)

    print('\n=== beta to the AI factor (equal-weight TSM/VRT/VST/MU) ===', flush=True)
    print(f'{"name":6s}{"beta":>8s}{"R2":>8s}{"beta to TSM":>14s}{"in the book?":>15s}',
          flush=True)
    print('-'*51, flush=True)
    for s in names:
        x, y, ds = pair(facd, U[s])
        b, r2 = regress(y, x)
        xt, yt, _ = pair(U['TSM'], U[s])
        bt, _ = regress(yt, xt)
        tag = 'yes, AI' if s in AI else ('yes' if s in BOOK else 'candidate')
        print(f'{s:6s}{b:>8.2f}{r2:>8.2f}{bt:>14.2f}{tag:>15s}', flush=True)

    # ---- variance share at strategy level
    print('\n=== how much of the BOOK is the AI trade? ===', flush=True)
    bc = book_curves()
    cc = {t: cand_curve(t) for t in CAND}
    books = {
        'five names (current)': [bc[s] for s in BOOK],
        'nine names (proposed)': [bc[s] for s in BOOK] + [cc[t] for t in CAND],
        'five + GM + VLO + CF': [bc[s] for s in BOOK] + [cc[t] for t in ('GM', 'VLO', 'CF')],
    }
    print(f'{"book":24s}{"R2 to AI factor":>18s}{"beta":>8s}{"full-sample ret":>17s}'
          f'{"max DD":>9s}', flush=True)
    print('-'*76, flush=True)
    for label, curves in books.items():
        ds, eq = held(curves)
        rr = daily_returns(ds, eq[1:])
        x, y, _ = pair(facd, rr)
        b, r2 = regress(y, x)
        yrs = max((ds[-1]-ds[0]).days/365.25, 1e-6)
        a = ((eq[-1]/eq[0])**(1/yrs)-1)*100
        dd, sh = stats(eq, 0, len(eq)-1)
        print(f'{label:24s}{r2:>18.2f}{b:>8.2f}{a:>16.1f}%{dd:>8.1f}%', flush=True)

    # ---- the stress windows
    print('\n=== the worst AI drawdowns in the sample, and what each book did through them ===',
          flush=True)
    wins = worst_windows(dates, fac, k=3)
    for dd, d0, d1 in wins:
        print(f'\n  AI factor {-dd*100:.1f}%   {d0} to {d1}   ({(d1-d0).days} days)', flush=True)
        for label, curves in books.items():
            ds, eq = held(curves, start=d0)
            sel = [i for i, d in enumerate(ds) if d <= d1]
            if not sel:
                continue
            j = sel[-1]+1
            trough = min(eq[:j+1])
            print(f'    {label:24s} {(eq[j]/eq[0]-1)*100:>7.1f}%   worst point '
                  f'{(trough/eq[0]-1)*100:>7.1f}%', flush=True)
        for s in names:
            x = [U[s][d] for d in sorted(U[s]) if d0 <= d <= d1]
            v = 1.0
            for r in x:
                v *= (1+r)
            print(f'      {s:5s} share {"":10s}{(v-1)*100:>7.1f}%', flush=True)
    print('\nDONE', flush=True)
