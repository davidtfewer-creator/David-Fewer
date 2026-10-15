"""
What the OPEN POSITIONS are actually worth -- not what the prices did.

Correction to §3.57. That note said "the diversifiers paid out in real time",
citing VLO +6.0% and CF +7.1% on the week. Both price moves are real and both
are irrelevant to this book, because the book is not in them the way the prices
imply: VLO holds ZERO shares (both sleeves sat in CASH through the rally, bids
at 447/442 against a 459.78 close) and CF's open sleeve was bought weeks ago at
a far higher price, so a 7% bounce off the bottom leaves it well under water.

A diversifier earns its place by what the BOOK holds of it, not by what the
ticker does. Measuring the price series and calling it a hedge is the mistake
this corrects.

Entries come from the trade log, the authoritative record of what was actually
paid, matched to the open sleeves on the blotter.

Usage:  python3 position_pnl.py <workbook.xlsx> [--pm -0.025]
"""
import datetime as dt
import json
import sys

import openpyxl

from drawdown_now import BOOK, load_query

AI = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'MRVL']
DIV = ['GM', 'VLO', 'CF']


def main():
    path = sys.argv[1]
    pm = float(sys.argv[sys.argv.index('--pm')+1]) if '--pm' in sys.argv else 0.0
    wb, dts, px = load_query(path)
    last = {n: px[n][-1] for n in BOOK}
    i9 = max(i for i, d in enumerate(dts) if d <= dt.date(2026, 10, 9))
    ref9 = {n: px[n][i9] for n in BOOK}
    at = wb['Active Trading']

    # open sleeves from the blotter
    open_sleeves = []
    for r in range(19, 37):
        nm, tr, st = (at.cell(row=r, column=c).value for c in (1, 2, 3))
        sh = at.cell(row=r, column=8).value
        if isinstance(nm, str) and nm.strip() in BOOK and st == 'HOLDING':
            open_sleeves.append([nm.strip(), str(tr).strip(), float(sh or 0)])

    # un-sold trade-log rows give the entry actually paid
    entries = {}
    for r in range(42, 400):
        v = [at.cell(row=r, column=c).value for c in range(1, 13)]
        stock, tranche, bdate, bprice, shares = v[1], v[2], v[3], v[4], v[5]
        selld = v[7]
        if not isinstance(stock, str) or stock.strip() not in BOOK:
            continue
        if selld not in (None, ''):
            continue                     # closed trade
        key = (stock.strip(), str(tranche).strip())
        entries[key] = dict(buy_date=bdate, buy=float(bprice), shares=float(shares or 0),
                            cost=float(v[6] or 0))

    print(f'OPEN POSITIONS at {dts[-1]} close'
          f'{f", plus {pm*100:+.1f}% pre-market" if pm else ""}\n')
    print(f'{"name":6s}{"sleeve":8s}{"bought":>12s}{"entry":>10s}{"now":>10s}'
          f'{"vs entry":>10s}{"since 9 Oct":>13s}{"value":>12s}{"P&L $":>12s}')
    tot_cost = tot_val = 0.0
    grp = {'AI': [0.0, 0.0], 'diversifier': [0.0, 0.0]}
    rows = []
    for nm, tr, sh in open_sleeves:
        e = entries.get((nm, tr))
        if not e:
            print(f'{nm:6s}{tr:8s}  no open trade-log row found')
            continue
        now = last[nm]*(1 + pm)
        val = e['shares']*now
        cost = e['cost'] or e['shares']*e['buy']
        pnl = val - cost
        w = now/ref9[nm] - 1
        g = 'AI' if nm in AI else 'diversifier'
        grp[g][0] += cost
        grp[g][1] += val
        tot_cost += cost
        tot_val += val
        bd = e['buy_date'].date() if isinstance(e['buy_date'], dt.datetime) else e['buy_date']
        rows.append(dict(name=nm, sleeve=tr, buy_date=str(bd), entry=e['buy'],
                         now=now, shares=e['shares'], cost=cost, value=val, pnl=pnl,
                         vs_entry=now/e['buy'] - 1, since_oct9=w, group=g))
        print(f'{nm:6s}{tr:8s}{str(bd):>12s}{e["buy"]:>10.2f}{now:>10.2f}'
              f'{(now/e["buy"]-1)*100:>9.1f}%{w*100:>12.1f}%{val:>12,.0f}{pnl:>12,.0f}',
              flush=True)

    print(f'\n{"":14s}{"cost":>14s}{"value":>14s}{"P&L":>14s}{"return":>10s}')
    for g in ('AI', 'diversifier'):
        c, v = grp[g]
        if c:
            print(f'{g:14s}{c:>14,.0f}{v:>14,.0f}{v-c:>14,.0f}{(v/c-1)*100:>9.1f}%')
    print(f'{"TOTAL HELD":14s}{tot_cost:>14,.0f}{tot_val:>14,.0f}'
          f'{tot_val-tot_cost:>14,.0f}{(tot_val/tot_cost-1)*100:>9.1f}%')
    cash = wb['Allocation']['B5'].value or 0
    print(f'\n  cash available {cash:,.2f}  '
          f'({cash/(tot_val+cash)*100:.1f}% of book value)')
    print(f'  VLO shares held: {sum(s for n, t, s in open_sleeves if n == "VLO"):.0f}'
          f'   -- the name that rallied is the one the book is not in')

    json.dump(dict(asof=str(dts[-1]), pm=pm, positions=rows,
                   totals=dict(cost=tot_cost, value=tot_val, pnl=tot_val-tot_cost),
                   by_group={g: dict(cost=grp[g][0], value=grp[g][1]) for g in grp},
                   cash=cash), open('position_pnl.json', 'w'), indent=1, default=str)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
