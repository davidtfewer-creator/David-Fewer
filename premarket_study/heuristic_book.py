"""
Could the old heuristic replace the OU sleeve on some names? Sleeve-by-sleeve comparison
and the correlation triangle, then the book test. Held construction throughout (§3.4):
every sleeve gets an equal share of its name's capital at the test boundary and compounds
independently — no rebalancing between sleeves or names.

Tested half (2025-05-23 onward), at-open basis, residual OU sigma. The heuristic runs on
its frozen first-half fit (honest OOS); Bayes and OU run on deployed parameters (full-sample
fits — mildly flattered on this window, see heuristic_symmetric.py for the symmetric refit).

Per name: each sleeve standalone (Bayes, OU, heuristic), the three pairwise correlations of
daily sleeve returns, and the two 50/50 pairings — deployed Bayes+OU vs Bayes+heuristic.
Book level: A = Bayes+OU 50/50 (today's book), C = Bayes+heuristic 50/50, B = thirds,
H = heuristic only. Metrics: annualised return, max drawdown, Jun–Jul 2026 stress episode.
"""
import datetime, math

from engine import run_model
from heuristic_fixed import load, CUT, NAMES, hp
from heuristic_engine import run_heuristic
from heuristic_symmetric import HEUR

STRESS = (datetime.date(2026, 6, 1), datetime.date(2026, 7, 31))


def sleeve_equity(fr, C):
    return [fr['AA'][i] * C[i] if fr['AE'][i] == 1 else fr['Y'][i] for i in range(len(C))]


def corr(x, y):
    n = min(len(x), len(y))
    x, y = x[:n], y[:n]
    mx = sum(x) / n; my = sum(y) / n
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (sx * sy) if sx and sy else float('nan')


def rets(series):
    return [series[i] / series[i - 1] - 1 for i in range(1, len(series))]


def ann_dd(series, dates):
    yrs = max((dates[-1] - dates[0]).days, 1) / 365.25
    ann = (series[-1] / series[0]) ** (1 / yrs) - 1
    peak = -1e30; dd = 0.0
    for v in series:
        peak = max(peak, v)
        dd = max(dd, (peak - v) / peak)
    return ann, dd


def stress(series, dates):
    lo = next(i for i, d in enumerate(dates) if d >= STRESS[0])
    hi = max(i for i, d in enumerate(dates) if d <= STRESS[1])
    return series[hi] / series[lo] - 1


if __name__ == '__main__':
    curves = {}
    print('tested half, held construction, at-open basis, residual OU sigma;')
    print('heuristic on frozen first-half fit, Bayes/OU on deployed (full-sample) params\n')
    print(f'{"stock":6s}{"Bayes":>9s}{"OU":>9s}{"heur":>9s} |'
          f'{"h-B":>6s}{"h-OU":>6s}{"B-OU":>6s} |{"B+OU":>9s}{"B+heur":>9s}{"delta":>8s}')
    deltas = []
    for s in NAMES:
        dts, O, H, L, C, p = load(s)
        r = run_model(dts, O, H, L, C, p, ou_sigma='resid', collect=True, same_day_exit='at_open')
        e1 = sleeve_equity(r.frames['t1'], C)
        e2 = sleeve_equity(r.frames['t2'], C)
        eh = run_heuristic(dts, O, H, L, C, hp(HEUR[s], p),
                           same_day_exit='at_open').frames['equity']
        cut = next(i for i, d in enumerate(dts) if d >= CUT)
        te = dts[cut:]
        n1 = [v / e1[cut] for v in e1[cut:]]
        n2 = [v / e2[cut] for v in e2[cut:]]
        nh = [v / eh[cut] for v in eh[cut:]]
        curves[s] = {dts[cut + i]: (n1[i], n2[i], nh[i]) for i in range(len(te))}
        aB, _ = ann_dd(n1, te); aO, _ = ann_dd(n2, te); aH, _ = ann_dd(nh, te)
        r1, r2, rh = rets(n1), rets(n2), rets(nh)
        chB, chO, cBO = corr(rh, r1), corr(rh, r2), corr(r1, r2)
        bo = [(n1[i] + n2[i]) / 2 for i in range(len(n1))]
        bh = [(n1[i] + nh[i]) / 2 for i in range(len(n1))]
        aBO, _ = ann_dd(bo, te); aBH, _ = ann_dd(bh, te)
        deltas.append(aBH - aBO)
        print(f'{s:6s}{aB * 100:>8.1f}%{aO * 100:>8.1f}%{aH * 100:>8.1f}% |'
              f'{chB:>6.2f}{chO:>6.2f}{cBO:>6.2f} |'
              f'{aBO * 100:>8.1f}%{aBH * 100:>8.1f}%{(aBH - aBO) * 100:>+7.1f}')
    print(f'\nB+heur beats B+OU on {sum(1 for d in deltas if d > 0)}/{len(deltas)} names; '
          f'mean delta {sum(deltas) / len(deltas) * 100:+.1f}pp')

    common = sorted(set.intersection(*(set(c) for c in curves.values())))
    books = {'A': [], 'B': [], 'C': [], 'H': []}
    for d in common:
        a = b = c = h = 0.0
        for s in NAMES:
            n1, n2, nh = curves[s][d]
            a += (n1 + n2) / 2
            b += (n1 + n2 + nh) / 3
            c += (n1 + nh) / 2
            h += nh
        k = len(NAMES)
        books['A'].append(a / k); books['B'].append(b / k)
        books['C'].append(c / k); books['H'].append(h / k)

    print(f'\n{"book":36s}{"ann":>8s}{"maxDD":>8s}{"Jun-Jul 26":>12s}')
    for k, lbl in (('A', 'A  Bayes+OU 50/50 (deployed book)'),
                   ('C', 'C  Bayes+heuristic 50/50'),
                   ('B', 'B  Bayes/OU/heuristic thirds'),
                   ('H', 'H  heuristic only')):
        ann, dd = ann_dd(books[k], common)
        print(f'{lbl:36s}{ann * 100:>7.1f}%{dd * 100:>7.1f}%{stress(books[k], common) * 100:>+11.1f}%')
    print(f'\nbook-level corr of daily returns: (H,A) '
          f'{corr(rets(books["H"]), rets(books["A"])):.2f}')
