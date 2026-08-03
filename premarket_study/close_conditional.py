"""
Test the CLOSE-CONDITIONAL premium.

Rule: the fill-day target is unchanged. At that day's close we observe where the stock finished
relative to the fill and amend the resting sell for subsequent sessions:
    closed ABOVE the fill  -> premium x cc_up    (the dip bounced; ~16% of room historically)
    closed AT/BELOW        -> premium x cc_down  (still falling; ~8% of room)
No lookahead: the close is known before the amendment applies.

Two tests:
 (1) cross-sectional -- grid cc_up/cc_down over ALL TEN names on the standard basis. Consistency
     across names is the evidence that this is structural rather than a fit to one series.
 (2) NVDA on minute-VERIFIED fills, the honest basis.
"""
import statistics
from stop_sweep import load_book
from engine import run_model

data, params, cached = load_book()
STOCKS = list(data)
UPS = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
DOWNS = [0.4, 0.6, 0.8, 1.0]


def ann(stock, cu, cd, sde=True):
    dts, O, H, L, C = data[stock]
    r = run_model(dts, O, H, L, C, params[stock], same_day_exit=sde, cc_up=cu, cc_down=cd)
    return r


if __name__ == '__main__':
    print('=== (1) CROSS-SECTIONAL GRID (all ten names, standard basis) ===')
    print('cell = number of names improved vs fixed premium / mean return change (pp)\n')
    base = {s: ann(s, None, None).annual_return for s in STOCKS}
    print(f'{"cc_up":>6s}' + ''.join(f'{f"cd={d}":>14s}' for d in DOWNS))
    best = None
    for cu in UPS:
        cells = []
        for cd in DOWNS:
            diffs = []
            for s in STOCKS:
                a = ann(s, cu, cd).annual_return
                diffs.append((a - base[s]) * 100)
            wins = sum(1 for d in diffs if d > 0)
            md = statistics.mean(diffs)
            cells.append(f'{wins:2d}/10 {md:+6.1f}')
            if best is None or (wins, md) > (best[0], best[1]):
                best = (wins, md, cu, cd)
        print(f'{cu:>6.2f}' + ''.join(f'{c:>14s}' for c in cells))
    print(f'\nbest cell: cc_up={best[2]}, cc_down={best[3]}  -> {best[0]}/10 names improved, '
          f'mean {best[1]:+.1f}pp')

    cu, cd = best[2], best[3]
    print(f'\n=== per-name detail at cc_up={cu}, cc_down={cd} ===')
    print(f'{"stock":6s}{"fixed":>9s}{"cc":>9s}{"delta":>9s}{"buys f/cc":>13s}{"Sharpe f/cc":>15s}')
    for s in STOCKS:
        r0 = ann(s, None, None); r1 = ann(s, cu, cd)
        print(f'{s:6s}{r0.annual_return*100:>8.0f}%{r1.annual_return*100:>8.0f}%'
              f'{(r1.annual_return-r0.annual_return)*100:>+8.1f}'
              f'{f"{r0.total_buys}/{r1.total_buys}":>13s}'
              f'{f"{r0.sharpe:.2f}/{r1.sharpe:.2f}":>15s}')

    print('\n=== (2) NVDA on MINUTE-VERIFIED fills (honest basis) ===')
    from minute_engine import make_checker
    dts, O, H, L, C = data['NVDA']
    CHK, _ = make_checker(dts, O)
    b = run_model(dts, O, H, L, C, params['NVDA'], same_day_exit=CHK)
    print(f'{"setting":22s}{"ann":>8s}{"buys":>7s}{"Sharpe":>9s}{"maxDD":>8s}')
    print(f'{"fixed premium":22s}{b.annual_return*100:>7.0f}%{b.total_buys:>7d}{b.sharpe:>9.2f}'
          f'{b.max_drawdown*100:>7.0f}%')
    for cu2, cd2 in ((1.5, 0.8), (2.0, 0.6), (2.0, 1.0), (2.5, 0.6), (cu, cd)):
        r = run_model(dts, O, H, L, C, params['NVDA'], same_day_exit=CHK, cc_up=cu2, cc_down=cd2)
        print(f'{f"cc_up={cu2}, cc_dn={cd2}":22s}{r.annual_return*100:>7.0f}%{r.total_buys:>7d}'
              f'{r.sharpe:>9.2f}{r.max_drawdown*100:>7.0f}%')
