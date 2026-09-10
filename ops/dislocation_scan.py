"""
dislocation_scan.py — the pre-open dislocation screen (user, 10 Sep 2026).

Reads the trading workbook's Query sheet (daily OHLC, the nine names — current
through Script 1's last pull) and grades every name for the discretionary
ticket, printing everything mechanical so the only human input left is the
news test and the one-sentence cause.

Convention: the signal is the LAST COMPLETED session's close and the ticket is
entered at the NEXT open — the same convention the base rates below were
measured on. So run it after Script 1's pull, evening or pre-open.

GRADES (measured in premarket_study/disc_vol_gate.py, nine names, daily
workbook data to 2026-09-09, +5%/10-session bracket, halves split 2025-05-23;
each signal scored standalone, so the populations nest):

                                          n   hit    avg   train    test
  STRONG  both dip tests, hot week      250   72%  +1.99%  +1.47%  +3.06%
  FLAG    3sh dip only, hot week         72   68%  +1.38%  +0.78%  +1.95%
     (STRONG and FLAG together = the adopted
      screen: 322, 71%, +1.85%, +1.35/+2.72)
  SLIDE   10dma dip only, hot week      123   53%  +0.52%  +0.05%  +1.32%
  DAYVOL  3sh dip, violent day, calm week 154 70%  +1.86%  -0.22%  +3.18%
  (no screen at all: every session)    4923   61%  +1.07%  +0.19%  +1.68%

Two things that table settles, both of which changed this script:

  1. The dip test that pays is distance below the 3-SESSION HIGH, not below
     the 10-day mean. It beats the 10dma test on both halves, and the
     signals only the 10dma test finds — the grinding slide — earn +0.05%
     on the train half against +0.19% for doing nothing at all. Those are
     graded SLIDE, and carry no ticket.
  2. The volatility test must stay a WEEK of range (5-day mean true range vs
     the 60-day median). Scoring the signal day's own range instead is what
     would flag a name that fell violently in one session out of a calm
     week — and that population averages -0.22% on the train half against
     +3.18% on the test half. Inverted halves, the pattern that has burned
     every overlay this book has rejected. Such names are graded DAYVOL
     with that number attached and carry no ticket, whatever the tape looks
     like.

What this deliberately does NOT do: the news test. A grade here is a shape,
not a trade. Company-specific bad news (guidance cut, accounting, a lost
customer) is not a dislocation — it is a repricing; the ticket wants the
OTHER kind (sector sympathy, index flows, overreaction to someone else's
news). Classify before acting: ask Claude with the flag list, or read the
tape yourself. Then the standing ticket rules apply — one-sentence cause,
size cap, bracket placed with the buy, no watching.

Usage:  python dislocation_scan.py "C:\\path\\to\\TradingExcel_9stock_avgo.xlsx"
        python dislocation_scan.py <workbook.xlsx> 2026-03-31   # replay a session

Requires: pip install openpyxl. Read-only; never writes the workbook.
"""
import datetime as dt
import statistics
import sys

import openpyxl

DIP3, DIPMA, VOLX = 0.95, 0.97, 1.3      # dip vs 3-session high, vs 10dma, vol
TARGET, CAP = 0.05, 10                   # the ticket bracket
EPOCH = dt.date(1899, 12, 30)

# class base rates from disc_vol_gate.py — full / train / test average return
RATES = {
    'STRONG': ('250 episodes, 72% hit, +1.99% avg (train +1.47%, test +3.06%)',
               'the strongest cell measured: both dip tests agree and the week is hot'),
    'FLAG': ('72 episodes, 68% hit, +1.38% avg (train +0.78%, test +1.95%)',
             'dip off a running high — positive on both halves, thinner than STRONG'),
    'SLIDE': ('123 episodes, 53% hit, +0.52% avg (train +0.05%, test +1.32%)',
              'no better than no screen at all on the train half — shape only'),
    'DAYVOL': ('154 episodes, 70% hit, +1.86% avg (train -0.22%, test +3.18%)',
               'INVERTED HALVES — the base rate does not support a ticket'),
}


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


def metrics(dts, O, H, L, C):
    """The last completed session's dislocation state, and its grade."""
    n = len(C)
    tr = [(H[i] - L[i]) / C[i] for i in range(n)]
    ref3 = max(C[-4:-1])
    dip3 = C[-1] / ref3 - 1
    dma10 = statistics.fmean(C[-10:])
    vs10 = C[-1] / dma10 - 1
    med60 = statistics.median(tr[-60:])
    vol5 = statistics.fmean(tr[-5:]) / med60 if med60 else 0.0
    volday = tr[-1] / med60 if med60 else 0.0
    deep3, deepma, week = dip3 <= DIP3 - 1, vs10 <= DIPMA - 1, vol5 >= VOLX
    if deep3 and deepma and week:
        grade = 'STRONG'
    elif deep3 and week:
        grade = 'FLAG'
    elif deepma and week:
        grade = 'SLIDE'
    elif deep3 and volday >= VOLX:
        grade = 'DAYVOL'
    else:
        grade = None
    return dict(close=C[-1], date=dts[-1], ref3=ref3, dip3=dip3, dma10=dma10,
                vs10=vs10, vol5=vol5, volday=volday, grade=grade)


def base_rates(dts, H, C, band_lo, band_hi):
    """This name's own historical dips in [band_lo, band_hi]: recovery within
    48 sessions to the pre-dip reference and to reference +2.5%. Complete
    windows only."""
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


def session_days(dts, k):
    """Calendar days that k sessions have actually taken in this history —
    beats assuming a fixed multiplier for the time-stop date."""
    gaps = [(dts[i + k] - dts[i]).days for i in range(len(dts) - k)]
    return int(statistics.median(gaps)) if gaps else int(k * 1.4)


def report(nm, m, tot, he, ht, ewarn, tstop):
    rate, note = RATES[m['grade']]
    print(f"{m['grade']:6s}  {nm}")
    print(f"  close {m['close']:.2f} on {m['date']}: {m['dip3']*100:+.1f}% vs 3-session "
          f"high ({m['ref3']:.2f}), {m['vs10']*100:+.1f}% vs 10dma; range "
          f"{m['vol5']:.2f}x its 60d norm over the week, {m['volday']:.2f}x on the day")
    print(f'  class base rate: {rate}')
    print(f'                   {note}')
    print(f"  own base rate, dips {m['band'][0]*100:.0f}%..{m['band'][1]*100:.0f}% "
          f'({tot} episodes): to pre-dip level {he}/{tot}, to +2.5% target '
          f'{ht}/{tot} — but within 48 SESSIONS, five times the ticket window;'
          f' context for the name, not a ticket hit rate')
    print(f'  earnings: {ewarn}')
    if m['grade'] in ('STRONG', 'FLAG'):
        print(f"  ticket if the news test passes: entry ~{m['close']:.2f} (next open), "
              f"GTC sell {m['close']*(1+TARGET):.2f} (+{TARGET*100:.0f}%), time-stop "
              f'~{tstop} ({CAP} sessions)')
        print('  NEWS TEST (the human step): company-specific news = repricing, '
              'not a ticket. Sector/general = candidate. One-sentence cause or no trade.')
    else:
        print('  NO TICKET on this grade — note it and move on. Nothing to place.')
    print()


def truncate(data, asof):
    """Drop everything after asof, so a past session can be replayed exactly
    as the scan would have seen it."""
    out = {}
    for nm, (dts, O, H, L, C) in data.items():
        k = sum(1 for d in dts if d <= asof)
        out[nm] = (dts[:k], O[:k], H[:k], L[:k], C[:k])
    return out


def main():
    data, earn = load(sys.argv[1])
    if len(sys.argv) > 2:
        data = truncate(data, dt.date.fromisoformat(sys.argv[2]))
    names = sorted(data)
    asof = max(v[0][-1] for v in data.values())
    today = dt.date.today()

    breadth = sum(1 for nm in names
                  if data[nm][4][-1] < statistics.fmean(data[nm][4][-200:]))
    print(f'DISLOCATION SCAN — data through {asof} (run {today})')
    caution = ('— CAUTION: broad weakness, dips may be the market, not the name'
               if breadth >= 4 else
               '(gate unarmed; single-name dips are the good kind)')
    print(f'book breadth: {breadth} of {len(names)} below their 200dma {caution}')
    if not earn:
        print("earnings dates: 'Active Trading' G7:G15 is EMPTY — every earnings "
              'check below is UNKNOWN. Fill that column.')
    print()

    M = {nm: metrics(*data[nm]) for nm in names}
    graded = [nm for nm in names if M[nm]['grade']]
    # entry is the next open, the stop the open CAP sessions after that
    tstop = asof + dt.timedelta(days=session_days(data[names[0]][0], CAP + 1))
    for grade in ('STRONG', 'FLAG', 'SLIDE', 'DAYVOL'):
        for nm in graded:
            m = M[nm]
            if m['grade'] != grade:
                continue
            dts, O, H, L, C = data[nm]
            m['band'] = (-0.10, -0.05) if m['dip3'] > -0.10 else (-0.25, -0.10)
            tot, he, ht = base_rates(dts, H, C, *m['band'])
            ed = earn.get(nm)
            if ed is None:
                ewarn = 'next report UNKNOWN — check before any ticket'
            else:
                dd = (ed - today).days
                ewarn = (f'REPORT IN {dd}d — inside the no-ticket window'
                         if 0 <= dd <= 7 else f'next report {ed} ({dd:+d}d) — clear')
            report(nm, m, tot, he, ht, ewarn, tstop)
    if not graded:
        print('nothing graded today.\n')

    # the whole book on one line each, so no dislocation is ever invisible
    print(f'the book on {asof} (dip vs 3-session high / vs 10dma, range vs 60d norm):')
    print(f'  {"":6s}{"close":>9s}{"3sh":>8s}{"10dma":>8s}{"wk vol":>8s}{"day vol":>9s}   grade')
    for nm in names:
        m = M[nm]
        print(f"  {nm:6s}{m['close']:>9.2f}{m['dip3']*100:>+8.1f}{m['vs10']*100:>+8.1f}"
              f"{m['vol5']:>8.2f}{m['volday']:>9.2f}   {m['grade'] or '-'}")


if __name__ == '__main__':
    main()
