"""
dislocation_scan.py — the pre-open dislocation screen (user, 10 Sep 2026).

Reads the trading workbook's Query sheet (daily OHLC, the nine names — current
through Script 1's last pull) and flags DISLOCATION CANDIDATES for the
discretionary ticket, printing everything mechanical about each flag so the
only human input left is the news test and the one-sentence cause.

Per name, on the latest completed session:
  - dip vs the 3-session high and vs the 10-day average
  - volatility state (5-day mean true range vs its 60-day median)
  - depth band, and THAT NAME's own historical base rates for dips in the
    band: how often price recovered to the pre-dip level, and to pre-dip
    +2.5% (the ticket-target proxy), within 48 sessions (complete windows
    only; the sample is the workbook's own history, ~Apr 2024 onward)
  - book breadth (names below their 200dma) — the regime tell: the failures
    historically came when the dip was the market, not the name
  - earnings proximity, from the next-earnings dates typed in Active Trading
    G7:G15 (keep them filled; blank means UNKNOWN, which is a warning, not a
    pass)
  - the ready-made ticket: reference entry (last close), +5% target, and the
    10-session time-stop date

FLAG RULE (matches the tested disc-ticket proxy): close >= 5% below its
3-session high OR >= 3% below its 10-day average, AND 5-day true range >=
1.3x its 60-day median.

What this deliberately does NOT do: the news test. A flag here is a shape,
not a trade. Company-specific bad news (guidance cut, accounting, a lost
customer) is not a dislocation — it is a repricing; the ticket wants the
OTHER kind (sector sympathy, index flows, overreaction to someone else's
news). Classify before acting: ask Claude with the flag list, or read the
tape yourself. Then the standing ticket rules apply — one-sentence cause,
size cap, bracket placed with the buy, no watching.

Usage (any time after Script 1 has refreshed Query; the signal is
close-based, so the evening before works too):

    python dislocation_scan.py "C:\\path\\to\\TradingExcel_9stock_avgo.xlsx"

Requires: pip install openpyxl. Read-only; never writes the workbook.
"""
import datetime as dt
import statistics
import sys

import openpyxl

DIP3, DIPMA, VOLX = 0.95, 0.97, 1.3      # flag thresholds (tested proxy)
TARGET, CAP = 0.05, 10                   # the ticket bracket
EPOCH = dt.date(1899, 12, 30)


def load(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    q = wb['Query']
    heads = {q.cell(row=1, column=c).value: c for c in range(1, q.max_column + 1)}
    names = sorted({h.split('_')[0] for h in heads if h and '_' in h})
    data = {}
    for nm in names:
        dts, O, H, L, C = [], [], [], [], []
        for r in range(2, q.max_row + 1):
            d, o = q.cell(row=r, column=1).value, q.cell(row=r, column=heads[f'{nm}_O']).value
            if d is None or not isinstance(o, (int, float)):
                continue
            if isinstance(d, (int, float)):
                d = EPOCH + dt.timedelta(days=int(d))
            elif hasattr(d, 'date'):
                d = d.date()
            dts.append(d)
            O.append(o)
            H.append(q.cell(row=r, column=heads[f'{nm}_H']).value)
            L.append(q.cell(row=r, column=heads[f'{nm}_L']).value)
            C.append(q.cell(row=r, column=heads[f'{nm}_C']).value)
        data[nm] = (dts, O, H, L, C)
    at = wb['Active Trading']
    earn = {}
    for r in range(7, 16):
        nm, d = at.cell(row=r, column=1).value, at.cell(row=r, column=7).value
        if nm and d is not None:
            earn[str(nm).strip()] = d.date() if hasattr(d, 'date') else d
    return data, earn


def base_rates(dts, H, C, band_lo, band_hi):
    """This name's historical dips in [band_lo, band_hi]: recovery within 48
    sessions to the pre-dip reference and to reference +2.5%. Complete windows
    only."""
    n, hits_e, hits_t, tot = len(C), 0, 0, 0
    i = 4
    while i < n:
        ref = max(C[i - 3:i])
        dip = C[i] / ref - 1
        if band_lo <= dip <= band_hi:
            if i + 49 <= n:                                  # complete window
                mh = max(H[j] for j in range(i + 1, i + 49))
                tot += 1
                hits_e += mh >= ref
                hits_t += mh >= ref * 1.025
            i += 10
        else:
            i += 1
    return tot, hits_e, hits_t


def main():
    data, earn = load(sys.argv[1])
    names = sorted(data)
    asof = max(v[0][-1] for v in data.values())
    today = dt.date.today()

    breadth = sum(1 for nm in names
                  if data[nm][4][-1] < statistics.fmean(data[nm][4][-200:]))
    print(f'DISLOCATION SCAN — data through {asof} (run {today})')
    caution = ('— CAUTION: broad weakness, dips may be the market, not the name'
               if breadth >= 4 else
               '(gate unarmed; single-name dips are the good kind)')
    print(f'book breadth: {breadth} of {len(names)} below their 200dma {caution}\n')

    flags = 0
    for nm in names:
        dts, O, H, L, C = data[nm]
        tr = [(H[i] - L[i]) / C[i] for i in range(len(C))]
        ref3 = max(C[-4:-1])
        dip3 = C[-1] / ref3 - 1
        dma10 = statistics.fmean(C[-10:])
        vs10 = C[-1] / dma10 - 1
        volr = statistics.fmean(tr[-5:]) / statistics.median(tr[-60:])
        flagged = (dip3 <= DIP3 - 1 or vs10 <= DIPMA - 1) and volr >= VOLX
        if not flagged:
            continue
        flags += 1
        band_lo, band_hi = (-0.10, -0.05) if dip3 > -0.10 else (-0.25, -0.10)
        tot, he, ht = base_rates(dts, H, C, band_lo, band_hi)
        ed = earn.get(nm)
        if ed is None:
            ewarn = 'next report UNKNOWN — check before any ticket'
        else:
            dd = (ed - today).days
            ewarn = (f'REPORT IN {dd}d — inside the no-ticket window' if 0 <= dd <= 7
                     else f'next report {ed} ({dd:+d}d) — clear')
        tstop = today + dt.timedelta(days=int(CAP * 1.5))    # ~10 sessions
        print(f'FLAG  {nm}')
        print(f'  close {C[-1]:.2f} on {dts[-1]}: {dip3*100:+.1f}% vs 3-session high '
              f'({ref3:.2f}), {vs10*100:+.1f}% vs 10dma; vol {volr:.2f}x its 60d norm')
        print(f'  own base rate, dips {band_lo*100:.0f}%..{band_hi*100:.0f}% '
              f'({tot} episodes): to pre-dip level {he}/{tot}, to +2.5% target '
              f'{ht}/{tot}, within 48 sessions')
        print(f'  earnings: {ewarn}')
        print(f'  ticket if the news test passes: entry ~{C[-1]:.2f}, GTC sell '
              f'{C[-1]*(1+TARGET):.2f} (+5%), time-stop ~{tstop} ({CAP} sessions)')
        print(f'  NEWS TEST (the human step): company-specific news = repricing, '
              f'not a ticket. Sector/general = candidate. One-sentence cause or no trade.\n')
    if not flags:
        print('no flags today.')


if __name__ == '__main__':
    main()
