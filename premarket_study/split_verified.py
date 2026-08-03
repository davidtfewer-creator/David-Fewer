"""
Re-run the Bayes/OU capital-split analysis on VERIFIED fills (all ten names).

The original split study used the optimistic basis and concluded the efficient split was
OU-heavy. But OU leaned far more on same-day round trips (90% of its trades vs 74% for Bayes),
so verification should penalise OU disproportionately -- the conclusion may invert.

Reports, per name and book-wide: verified return / Sharpe / maxDD / trades as the Bayes share
runs 0 -> 100%, and the split that maximises each objective.
"""
import copy, statistics
from stop_sweep import load_book
from engine import run_model
from five_min import make_checker as fm, FILES as FMF
from minute_engine import make_checker as nv

data, params, cached = load_book()
STOCKS = list(data)
CHK = {}
for s in STOCKS:
    dts, O, H, L, C = data[s]
    CHK[s] = nv(dts, O)[0] if s == 'NVDA' else fm(s, dts, O)[0]

GRID = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def run(s, bp):
    dts, O, H, L, C = data[s]
    p = copy.copy(params[s]); p.bayes_pct = bp
    return run_model(dts, O, H, L, C, p, collect=True, same_day_exit=CHK[s])


if __name__ == '__main__':
    print('=== PER-NAME: verified annual return by Bayes share ===')
    hdr = f'{"stock":6s}' + ''.join(f'{int(g*100):>6d}%' for g in GRID)
    print(hdr); print('-' * len(hdr))
    curves = {}
    for s in STOCKS:
        row = []
        for g in GRID:
            r = run(s, g)
            row.append(r)
        curves[s] = row
        print(f'{s:6s}' + ''.join(f'{r.annual_return*100:>6.0f} ' for r in row))

    print('\n=== best Bayes share per name (verified) ===')
    print(f'{"stock":6s}{"max-return":>12s}{"ret":>7s}{"max-Sharpe":>12s}{"Sh":>6s}'
          f'{"current 50%":>13s}{"ret@50":>8s}')
    print('-' * 64)
    for s in STOCKS:
        row = curves[s]
        bi = max(range(len(GRID)), key=lambda i: row[i].annual_return)
        si = max(range(len(GRID)), key=lambda i: row[i].sharpe)
        i50 = GRID.index(0.5)
        print(f'{s:6s}{GRID[bi]*100:>11.0f}%{row[bi].annual_return*100:>6.0f}%'
              f'{GRID[si]*100:>11.0f}%{row[si].sharpe:>6.2f}'
              f'{"":>13s}{row[i50].annual_return*100:>7.0f}%')

    print('\n=== BOOK-LEVEL (equal weight across the ten names) ===')
    print(f'{"bayes%":>7s}{"mean ann":>10s}{"mean Sharpe":>13s}{"mean maxDD":>12s}{"trades/yr":>11s}')
    print('-' * 53)
    yrs = (data['NVDA'][0][-1] - data['NVDA'][0][0]).days / 365.25
    best = None
    for gi, g in enumerate(GRID):
        anns = [curves[s][gi].annual_return for s in STOCKS]
        shs = [curves[s][gi].sharpe for s in STOCKS]
        dds = [curves[s][gi].max_drawdown for s in STOCKS]
        tr = [curves[s][gi].total_buys for s in STOCKS]
        ma = statistics.mean(anns)
        tag = '  <-- current' if abs(g-0.5) < 1e-9 else ''
        if best is None or ma > best[1]:
            best = (g, ma)
        print(f'{g*100:>6.0f}%{ma*100:>9.0f}%{statistics.mean(shs):>13.2f}'
              f'{statistics.mean(dds)*100:>11.0f}%{sum(tr)/yrs:>11.0f}{tag}')
    print(f'\nbook-best Bayes share on verified fills: {best[0]*100:.0f}% -> {best[1]*100:.0f}% mean annual')
