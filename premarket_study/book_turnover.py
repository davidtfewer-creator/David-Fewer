"""
How fast does the book actually trade, and how fast does a candidate trade?

Every candidate screen in this file has judged names on RETURN and on
CORRELATION. None has judged them on SPEED -- fills per year and how long a
position is held -- even though that is what the trading character of the entity
rests on, and even though it was the stated reason CF was rejected ("relies on a
small number of high margin trades... fast turnover stocks are a better fit").

This measures both: the live book at its deployed parameters, and every
candidate that has a stored reference vector and a 5-minute file. Holding period
is in CALENDAR days from fill to sale, both sleeves pooled.

Caveat on the candidates: reference vectors are FULL-SAMPLE fits and carry
lookahead (HANDOVER sec.5). That matters a great deal for the return they imply
and much less for turnover, which is a structural property of the name and its
premium -- but the figures are a guide to speed, not a return claim.

Usage:  python3 book_turnover.py
"""
import os
import sys

from engine import run_model
from fresh_opt_cands import REF, daily_from_5min, ref_params
from live5_load import load as load_book
from minute_index import make_checker


def holds(dts, O, H, L, C, p, chk):
    fr = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                   collect=True).frames
    hd, stops = [], 0
    for key in ('t1', 't2'):
        t = fr[key]
        e = None
        for i in range(len(dts)):
            if t['Z'][i] == 1:
                e = i
            if t['AD'][i] == 1 and e is not None:
                hd.append((dts[i] - dts[e]).days)
                if t['AC'][i] is not None and t['AC'][i] < t['AB'][i]:
                    stops += 1
                e = None
    hd.sort()
    return hd, stops


def line(lbl, hd, yrs, stops=None):
    n = len(hd)
    print(f'{lbl:8s}{n/yrs:>10.1f}{hd[n//2]:>6d}d{hd[int(n*0.75)]:>7d}d'
          f'{hd[int(n*0.95)]:>7d}d{sum(1 for h in hd if h <= 5)/n*100:>7.0f}%'
          f'{(stops if stops is not None else 0):>7d}', flush=True)


def main():
    print(f'{"name":8s}{"fills/yr":>10s}{"med":>7s}{"75th":>8s}{"95th":>8s}'
          f'{"<=5d":>8s}{"stops":>7s}')
    print('--- the live book, deployed parameters ---', flush=True)
    data, params, _ = load_book()
    allh = []
    for s, (dts, O, H, L, C) in data.items():
        hd, st = holds(dts, O, H, L, C, params[s], make_checker(s, dts, O))
        allh += hd
        line(s, hd, (dts[-1] - dts[0]).days/365.25, st)
    allh.sort()
    yrs = (dts[-1] - dts[0]).days/365.25
    line('BOOK', allh, yrs)
    print('\n--- candidates with a stored reference vector (lookahead: see docstring) ---',
          flush=True)
    for s, v in sorted(REF.items()):
        if not v or not os.path.exists(os.path.join('data_5min', f'{s}_5min.xlsx')):
            continue
        try:
            dts, O, H, L, C = daily_from_5min(s)
            hd, st = holds(dts, O, H, L, C, ref_params(s), make_checker(s, dts, O))
        except Exception as e:                      # noqa: BLE001 - report, do not stop
            print(f'{s:8s}  skipped: {e}', flush=True)
            continue
        if hd:
            line(s, hd, (dts[-1] - dts[0]).days/365.25, st)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
