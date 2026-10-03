"""
build_pm_cache.py — rebuild the pre-market caches lost to the container recycle
(HANDOVER 3.28d), from the 5-minute files themselves.

The archive re-uploaded on 3 Oct 2026 carries PRE-MARKET bars (from 04:00 ET)
as well as regular hours, so data_pm/ no longer needs separate files: both
caches the overlay studies read can be derived from data_5min/ directly.

  data_pm/pm_last.pkl        {name: {date: last pre-market print}}   (the 09:25
                             screen premarket_excl.py reads)
  data_pm/pm_last_cuts.pkl   {cut: {name: {date: print}}} for 08:30, 09:00,
                             09:15, 09:25 — the cutoff grid of 3.16, read by
                             breadth_gate, stop_autopsy, premia_at_book and the
                             rest via ['09:00']

CONVENTION. Bars are start-stamped, so a bar labelled 09:25 runs to 09:30. A
cut at T takes the close of the last bar that has FINISHED by T, i.e. the last
bar whose stamp is strictly before T — strictly ex ante, which is what a rule
acting at T can see. The 09:25 screen is the last pre-market bar of the
session (stamp before 09:30). This convention is checked, not assumed: the
caller must reproduce a published baseline before trusting the result, and
baseline_check.py does exactly that.

Usage: python build_pm_cache.py
"""
import collections
import datetime as dt
import os
import pickle

import openpyxl

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_5min')
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_pm')
OPEN_T = dt.time(9, 30)
PM_START = dt.time(4, 0)
CUTS = {'08:30': dt.time(8, 30), '09:00': dt.time(9, 0),
        '09:15': dt.time(9, 15), '09:25': dt.time(9, 25)}


def premarket_bars(path):
    """{date: [(time, close)]} for bars between 04:00 and the open."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    by = collections.defaultdict(list)
    first = True
    for row in ws.iter_rows(values_only=True):
        if first:
            first = False
            continue
        d, c = row[0], row[4]
        if not isinstance(d, dt.datetime) or c is None:
            continue
        t = d.time()
        if PM_START <= t < OPEN_T:
            by[d.date()].append((t, float(c)))
    wb.close()
    return {d: sorted(v) for d, v in by.items()}


def last_before(bars, cut):
    """Close of the last bar that finished by `cut` (stamp strictly before it)."""
    prior = [c for t, c in bars if t < cut]
    return prior[-1] if prior else None


def main():
    os.makedirs(DST, exist_ok=True)
    names = sorted(f[:-len('_5min.xlsx')] for f in os.listdir(SRC) if f.endswith('_5min.xlsx'))
    cuts = {k: {} for k in CUTS}
    last = {}
    print(f'{"name":6s}{"sessions":>10s}{"with PM":>9s}' +
          ''.join(f'{k:>9s}' for k in CUTS))
    for nm in names:
        bars = premarket_bars(os.path.join(SRC, f'{nm}_5min.xlsx'))
        last[nm] = {d: last_before(v, OPEN_T) for d, v in bars.items()}
        last[nm] = {d: p for d, p in last[nm].items() if p is not None}
        cov = []
        for k, t in CUTS.items():
            cuts[k][nm] = {d: p for d, p in
                           ((d, last_before(v, t)) for d, v in bars.items())
                           if p is not None}
            cov.append(len(cuts[k][nm]))
        print(f'{nm:6s}{len(bars):>10d}{len(last[nm]):>9d}' +
              ''.join(f'{c:>9d}' for c in cov))

    with open(os.path.join(DST, 'pm_last.pkl'), 'wb') as f:
        pickle.dump(last, f)
    with open(os.path.join(DST, 'pm_last_cuts.pkl'), 'wb') as f:
        pickle.dump(cuts, f)
    print(f'\nwrote {DST}/pm_last.pkl and pm_last_cuts.pkl for {len(names)} names')


if __name__ == '__main__':
    main()
