"""
Per-stock efficiency-optimal Bayes split for Allocation mode 2.

Because the Bayes and OU sleeves are only ~0.24 correlated, a blend can beat either pure
sleeve on risk-adjusted terms (two-asset diversification). For each name we grid the split
0..100% Bayes and locate:
  * Sharpe-max  bayes% - the efficiency optimum (best risk-adjusted return)
  * Calmar-max  bayes% - best return-per-max-drawdown (return-tilted efficiency)
Then a recommended rounded split, and the book-level effect vs the flat 60%.

In-sample, single low-dimensional knob: report round numbers, not razor-edge argmaxima.
"""
import copy, statistics
from split_analysis import load_book, stats
from engine import run_model

GRID = [i / 100 for i in range(0, 101, 5)]   # 0%,5%,...,100% Bayes


def curve(s, data, params):
    dts, O, H, L, C = data[s]
    out = []
    for bp in GRID:
        p = copy.copy(params[s]); p.bayes_pct = bp
        r = run_model(dts, O, H, L, C, p, collect=True)
        ann, sh, mdd = stats(r.frames['equity'])
        calmar = ann / mdd if mdd > 1e-6 else 0
        out.append((bp, ann, sh, mdd, calmar))
    return out


def pick(out, key):
    return max(out, key=key)


if __name__ == '__main__':
    data, params, wts = load_book()
    STOCKS = list(data)

    print('=== PER-STOCK EFFICIENCY-OPTIMAL BAYES SPLIT ===')
    print('(sleeves ~0.24 corr, so an interior blend can beat either pure sleeve)\n')
    hdr = (f'{"stock":6s}{"Sh-max bp":>10s}{"ann":>7s}{"Sh":>6s}{"DD":>6s}   '
           f'{"Calmar-max bp":>14s}{"ann":>7s}{"Sh":>6s}{"DD":>6s}   {"@50%: Sh":>9s}{"@100%: Sh":>10s}')
    print(hdr); print('-' * len(hdr))
    rec = {}
    for s in STOCKS:
        out = curve(s, data, params)
        shp = pick(out, lambda x: x[2])       # max Sharpe
        cal = pick(out, lambda x: x[4])       # max Calmar
        at50 = next(x for x in out if abs(x[0] - 0.5) < 1e-9)
        at100 = out[-1]
        # recommendation: Sharpe-optimal, but nudge toward return if Calmar agrees on more Bayes;
        # round to nearest 5% (grid already), clamp to [0.2,0.9] for sanity/diversification
        rbp = shp[0]
        rec[s] = min(max(rbp, 0.20), 0.90)
        print(f'{s:6s}{shp[0]*100:>9.0f}%{shp[1]*100:>6.0f}%{shp[2]:>6.2f}{shp[3]*100:>5.0f}%   '
              f'{cal[0]*100:>13.0f}%{cal[1]*100:>6.0f}%{cal[2]:>6.2f}{cal[3]*100:>5.0f}%   '
              f'{at50[2]:>9.2f}{at100[2]:>10.2f}')

    print('\n=== RECOMMENDED per-stock Bayes% (Sharpe-optimal, clamped 20-90%) ===')
    print(f'{"stock":6s}{"Bayes%":>8s}{"OU%":>6s}')
    for s in STOCKS:
        print(f'{s:6s}{rec[s]*100:>7.0f}%{(1-rec[s])*100:>5.0f}%')

    # book-level effect: flat-60 vs per-stock recommended vs flat-50, using allocation weights
    print('\n=== BOOK-LEVEL EFFECT (included names, allocation-weighted) ===')
    tot = sum(wts.values())

    def book(splits):
        booked = None; ln = None
        for s, w in wts.items():
            dts, O, H, L, C = data[s]; p = copy.copy(params[s]); p.bayes_pct = splits[s]
            eq = run_model(dts, O, H, L, C, p, collect=True).frames['equity']
            norm = [e / eq[0] * (w / tot) for e in eq]
            if booked is None: booked, ln = norm, len(norm)
            else:
                m = min(ln, len(norm)); booked = [booked[i] + norm[i] for i in range(m)]; ln = m
        return stats(booked)

    for label, sp in [('flat 50%', {s: 0.5 for s in wts}),
                      ('flat 60% (current)', {s: 0.6 for s in wts}),
                      ('per-stock efficiency', {s: rec[s] for s in wts})]:
        a, sh, dd = book(sp)
        print(f'  {label:22s}: ann {a*100:5.0f}%   Sharpe {sh:4.2f}   maxDD {dd*100:4.1f}%')
