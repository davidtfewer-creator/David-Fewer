"""
Flat premium for the first k sessions, then a ramp beyond it -- a rule aimed at the tail.

Motivation. Two thirds of trades clear within three sessions, and they are not the problem:
they were never trapped. Half of all capital-time sits in the longest tenth of trades. So key
the schedule to day k+1 onward, leaving the fast trades at the full premium and touching only
the positions that have actually become expensive.

Both directions are run, because "charge the long holds" admits two readings:

  ESCAPE   after day k the premium DECAYS. Accept less to get the capital back. This is the
           only direction that can release capital: a resting sell can be lowered into the
           market, never raised into it.
  PENALTY  after day k the premium RISES. If the position is going to tie capital up, make it
           pay more when it finally comes back. Coherent, but it can only reduce turnover --
           it is a bet on the size of the eventual profit, not on compounding.

The test that decides it. A 40-cell grid over (k, target, fade length) is run on NVDA and AVGO
independently and the two are RANK-CORRELATED. If a schedule family carries real signal, the
cells that work on one name should tend to work on the other -- they are the same trade in the
same window. If the correlation is around zero, the grid is measuring noise, and picking its
best cell is picking a lottery ticket.

Run:  python3 ramp_stale.py
"""
import sys

import numpy as np
from scipy import stats

import ramp_premium as R
from ramp_oos import window_return

MODE = 'verified'
NAMES = sys.argv[1:] or ['NVDA', 'AVGO']

START = (3, 5, 7, 10)                     # sessions held at full premium
TARGET = (0.50, 0.70, 0.85, 1.15, 1.50)   # <1 escape, >1 penalty
FADE = (5, 10)                            # sessions over which to reach the target
PERTURB = (0.90, 0.95, 1.00, 1.05, 1.10)


def sched(k, target, fade):
    s = [1.0] * k
    for j in range(1, fade + 1):
        s.append(1.0 + (target - 1.0) * j / fade)
    return tuple(s)


def load(stock):
    d, O, H, L, C = R.load_feed(stock)
    yrs = (d[-1] - d[0]).days / 365.25
    p, _ = R.load_params(stock, years=yrs)
    return dict(d=d, data=(d, O, H, L, C), p=p, idx=R.build_index(stock), stock=stock)


def score(ctx, ramp, prem_scale=1.0):
    r = R.run(ctx['stock'], ramp=ramp, mode=MODE, p=ctx['p'], data=ctx['data'],
              idx=ctx['idx'], prem_scale=prem_scale)
    d = ctx['d']
    return (r.annual_return, window_return(r, d, d[0], R.SPLIT), window_return(r, d, R.SPLIT), r)


def nbhd(ctx, ramp):
    """Neighbourhood median over premium scalings -- guards against a lucky point estimate."""
    out = [score(ctx, ramp, sc)[:3] for sc in PERTURB]
    return tuple(float(np.median([o[j] for o in out])) for j in range(3))


def main():
    ctxs = {n: load(n) for n in NAMES}

    # ---- how much of the book does a day-k rule even touch? -------------------------
    print(f'=== reach of a rule that starts at day k+1 ({MODE} fills) ===\n')
    for n, ctx in ctxs.items():
        _, _, _, base = score(ctx, None)
        trips = R.trades_of(base.frames['t1']) + R.trades_of(base.frames['t2'])
        h = np.array([t[2] for t in trips])
        print(f'  {n}: {len(h)} trades')
        for k in START:
            reach = (h > k).mean()
            time_share = h[h > k].sum() / h.sum()
            print(f'     day>{k:2d}: {100*reach:5.1f}% of trades, '
                  f'{100*time_share:5.1f}% of all held-time')
    print()

    # ---- the grid -------------------------------------------------------------------
    base = {n: nbhd(ctxs[n], None) for n in NAMES}
    for n in NAMES:
        print(f'  {n} baseline (neighbourhood median): full {100*base[n][0]:.2f}%  '
              f'fitted {100*base[n][1]:.2f}%  tested {100*base[n][2]:.2f}%')
    print()

    cells, res = [], {n: [] for n in NAMES}
    for k in START:
        for t in TARGET:
            for f in FADE:
                cells.append((k, t, f))
    for n in NAMES:
        for (k, t, f) in cells:
            res[n].append(nbhd(ctxs[n], sched(k, t, f)))

    hdr = ' '.join(f'{n:>25s}' for n in NAMES)
    print(f'=== grid: neighbourhood-median Δ vs fixed premium, in pp ===\n')
    print(f"{'k':>3s} {'target':>7s} {'fade':>5s}  " + hdr)
    print(f"{'':>3s} {'':>7s} {'':>5s}  " + ' '.join(f"{'full  fitted  tested':>25s}" for _ in NAMES))
    for i, (k, t, f) in enumerate(cells):
        kind = 'escape' if t < 1 else 'penalty'
        line = f'{k:3d} {t:7.2f} {f:5d}  '
        for n in NAMES:
            v = res[n][i]
            line += (f'{100*(v[0]-base[n][0]):+7.2f}{100*(v[1]-base[n][1]):+8.2f}'
                     f'{100*(v[2]-base[n][2]):+9.2f}  ')
        print(line + f' [{kind}]')

    # ---- does the grid agree across the two names? ----------------------------------
    if len(NAMES) == 2:
        a, b = NAMES
        print(f'\n=== does the grid transport from {a} to {b}? ===\n')
        for j, nm in ((0, 'full sample'), (1, 'fitted half'), (2, 'tested half')):
            va = np.array([res[a][i][j] - base[a][j] for i in range(len(cells))])
            vb = np.array([res[b][i][j] - base[b][j] for i in range(len(cells))])
            rho, pv = stats.spearmanr(va, vb)
            both = np.mean((va > 0) & (vb > 0))
            print(f'  {nm:12s} Spearman rho = {rho:+.3f} (p={pv:.3f});  '
                  f'{100*both:.0f}% of cells positive on BOTH; '
                  f'{a} median {100*np.median(va):+.2f}pp, {b} median {100*np.median(vb):+.2f}pp')

        print(f'\n  best cell on {a}, and what it does on {b}:')
        for j, nm in ((0, 'full'), (2, 'tested')):
            va = [res[a][i][j] - base[a][j] for i in range(len(cells))]
            i = int(np.argmax(va))
            k, t, f = cells[i]
            print(f'    by {nm:6s}: k={k} target={t} fade={f} -> '
                  f'{a} {100*va[i]:+.2f}pp, {b} {100*(res[b][i][j]-base[b][j]):+.2f}pp')


if __name__ == '__main__':
    main()
