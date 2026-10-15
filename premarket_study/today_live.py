"""
Re-price the episode for a live 3-7% down day.

The earlier read assumed -2.5% from the pre-market indication. The user reports
the book actually down 3-7% intraday on 15 Oct, so every figure that depended on
that assumption moves. This re-runs them across the stated range rather than
picking a point, and reports the per-name 200dma breach thresholds so the actual
prints can be read off directly.

What changes and what does not:
  * the 200dma BREADTH GATE (§3.23, K=4) -- GM sat 0.4% above its line, so almost
    any down day makes it the fourth breach and fires the rule
  * where the 3-session move ranks against the 635 in the sample, and whether the
    episode is still April-2024 shaped or has become April-2025 shaped
  * the open-position P&L
It does NOT change the fact that the gate is nearly inert here: $6,035 of cash
and 13 of 18 sleeves holding means an entry veto has almost nothing to veto.

Usage:  python3 today_live.py <workbook.xlsx>
"""
import datetime as dt
import json
import statistics
import sys

from drawdown_now import BOOK, load_query

AI = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'MRVL']
DIV = ['GM', 'VLO', 'CF']
SCEN = (-0.03, -0.05, -0.07)

# The actual prints, 15 Oct, 30 minutes into the session (user-reported). Kept so
# the live reading is reproducible: the scenario table above was built before they
# arrived and the outcome differed from every uniform scenario in it, because the
# diversifiers did NOT follow the AI names down.
ACTUAL = {'TSM': -0.045, 'VRT': -0.070, 'VST': -0.020, 'AVGO': -0.025,
          'MU': -0.040, 'MRVL': -0.040, 'GM': +0.0025, 'VLO': -0.015, 'CF': 0.0}


def main():
    path = sys.argv[1]
    wb, dts, px = load_query(path)
    i = len(dts) - 1
    pk = max(j for j, d in enumerate(dts) if d <= dt.date(2026, 10, 7))

    print('1. WHAT TODAY\'S FALL DOES TO EACH NAME\'S 200dma\n')
    print(f'{"name":6s}{"14 Oct":>10s}{"200dma":>10s}{"headroom":>10s}'
          f'{"breaches at":>13s}   state at -3% / -5% / -7%')
    sma = {}
    for n in BOOK:
        C = px[n]
        m = sum(C[i-199:i+1])/200
        sma[n] = m
        head = C[i]/m - 1
        thr = m/C[i] - 1                      # today's return that puts it exactly on the line
        st = ' / '.join('BELOW' if C[i]*(1+s) < m else 'above' for s in SCEN)
        print(f'{n:6s}{C[i]:>10.2f}{m:>10.2f}{head*100:>9.1f}%{thr*100:>12.1f}%   {st}')

    print(f'\n2. THE BOOK AT EACH LEVEL\n')
    # 3-session windows for ranking
    R = [statistics.fmean([px[n][j]/px[n][j-1] - 1 for n in BOOK]) for j in range(1, len(dts))]
    wins = []
    for s in range(len(R) - 2):
        c = (1+R[s])*(1+R[s+1])*(1+R[s+2]) - 1
        wins.append(c)
    print(f'{"today":>8s}{"vs 7 Oct peak":>15s}{"3-sess move":>13s}{"rank/635":>10s}'
          f'{"below 200dma":>14s}{"gate":>7s}{"AI six":>9s}{"divers":>9s}')
    out = {}
    for s in SCEN:
        lvl_now = statistics.fmean([px[n][i]*(1+s)/px[n][pk] for n in BOOK]) - 1
        r3 = (1+R[-2])*(1+R[-1])*(1+s) - 1
        rank = sum(1 for w in wins if w <= r3) + 1
        nb = sum(1 for n in BOOK if px[n][i]*(1+s) < sma[n])
        ai = statistics.fmean([px[n][i]*(1+s)/px[n][pk] - 1 for n in AI])
        dv = statistics.fmean([px[n][i]*(1+s)/px[n][pk] - 1 for n in DIV])
        out[f'{s*100:.0f}%'] = dict(vs_peak=lvl_now, move3=r3, rank=rank, below200=nb,
                                    gate=nb >= 4, ai=ai, div=dv)
        print(f'{s*100:>7.0f}%{lvl_now*100:>14.1f}%{r3*100:>12.1f}%{rank:>10d}'
              f'{nb:>12d}/9{("ON" if nb >= 4 else "off"):>7s}{ai*100:>8.1f}%{dv*100:>8.1f}%')

    print(f'\n  for reference: April 2024 fell -10.7% over 12 sessions, '
          f'diversifiers -6.6%, 8 of 9 fell')
    print(f'                 April 2025 fell -16.9% over  3 sessions, '
          f'diversifiers -12.1%, 9 of 9 fell  <- the un-protectable one')

    print(f'\n3. OPEN POSITIONS\n')
    at = wb['Active Trading']
    pos = []
    for r in range(42, 400):
        v = [at.cell(row=r, column=c).value for c in range(1, 13)]
        stock, tr, bprice, shares, cost, selld = v[1], v[2], v[4], v[5], v[6], v[7]
        if not isinstance(stock, str) or stock.strip() not in BOOK or selld not in (None, ''):
            continue
        pos.append((stock.strip(), float(bprice), float(shares or 0), float(cost or 0)))
    print(f'{"today":>8s}{"held value":>14s}{"cost":>14s}{"P&L":>14s}{"return":>9s}')
    for s in SCEN:
        val = sum(sh*px[n][i]*(1+s) for n, bp, sh, c in pos)
        cost = sum(c for n, bp, sh, c in pos)
        print(f'{s*100:>7.0f}%{val:>14,.0f}{cost:>14,.0f}{val-cost:>14,.0f}'
              f'{(val/cost-1)*100:>8.1f}%')
        out[f'{s*100:.0f}%']['held_value'] = val
        out[f'{s*100:.0f}%']['held_pnl'] = val - cost
    print(f'\n4. THE ACTUAL PRINTS (15 Oct, 30 min in)\n')
    bk = statistics.fmean([ACTUAL[n] for n in BOOK])
    ai = statistics.fmean([ACTUAL[n] for n in AI])
    dv = statistics.fmean([ACTUAL[n] for n in DIV])
    nb = sum(1 for n in BOOK if px[n][i]*(1+ACTUAL[n]) < sma[n])
    vsdv = statistics.fmean([px[n][i]*(1+ACTUAL[n])/px[n][pk] - 1 for n in DIV])
    vs = statistics.fmean([px[n][i]*(1+ACTUAL[n])/px[n][pk] for n in BOOK]) - 1
    print(f'  book {bk*100:+.2f}%   AI six {ai*100:+.2f}%   diversifiers {dv*100:+.2f}%')
    print(f'  from the 7 Oct peak: book {vs*100:+.1f}%, diversifiers {vsdv*100:+.1f}%')
    print(f'  breadth {nb} of 9 below their 200dma -> gate '
          f'{"ON" if nb >= 4 else "OFF"}; GM rose, so it is not the fourth breach')
    print(f'  shape: April 2025 had diversifiers -12.1% and 9/9 falling. Not this.')
    out['actual'] = dict(moves=ACTUAL, book=bk, ai=ai, div=dv, below200=nb,
                         gate=nb >= 4, vs_peak=vs, div_vs_peak=vsdv)
    json.dump(out, open('today_live.json', 'w'), indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
