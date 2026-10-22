"""
box_1min_to_5min.py — turn a Box text extraction of a ONE-minute sheet into a
five-minute file in the layout data_bear/ and data_5min/ already read
(22 Oct 2026; first used for the 2021-23 BRK.B and NVDA files, which the user
exported at 1-minute resolution).

Bars are bucketed on the bar's start minute floored to 5 (09:31..09:34 -> 09:30),
the same start-labelled convention as the existing 5-minute files (their last
regular-session bar is 15:55). O = first open, H = max, L = min, C = last close.
The extraction has no volume column, so Volume is written as None.

Validation before writing: strictly increasing 1-minute stamps, no duplicates,
H >= max(O, C) >= min(O, C) >= L on every input and output bar.

Usage:
    python box_1min_to_5min.py <extracted.txt> <TICKER> <out_dir>
"""
import datetime as dt
import os
import sys

import openpyxl


def parse(path):
    rows = []
    with open(path) as f:
        for ln in f:
            p = ln.strip().split('\t')
            if len(p) < 5:
                continue
            try:
                t = dt.datetime.strptime(p[0].strip(), '%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    t = dt.datetime.strptime(p[0].strip(), '%Y-%m-%d %H:%M')
                except ValueError:
                    continue
            o, h, l, c = map(float, p[1:5])
            rows.append((t, o, h, l, c))
    return rows


def check(bars, what):
    for i, (t, o, h, l, c) in enumerate(bars):
        assert h >= max(o, c) - 1e-9 and min(o, c) >= l - 1e-9, (what, t)
        if i:
            assert t > bars[i - 1][0], (what, 'not increasing', t)


def main():
    src, tick, out_dir = sys.argv[1:4]
    one = parse(src)
    check(one, '1min')
    five = []
    for t, o, h, l, c in one:
        b = t.replace(minute=t.minute - t.minute % 5, second=0)
        if five and five[-1][0] == b:
            _, o0, h0, l0, _ = five[-1]
            five[-1] = (b, o0, max(h0, h), min(l0, l), c)
        else:
            five.append((b, o, h, l, c))
    check(five, '5min')
    days = sorted({t.date() for t, *_ in five})
    rth = sum(1 for t, *_ in five if dt.time(9, 30) <= t.time() < dt.time(16, 0))
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f'{tick} 5min'
    ws.append(['Datetime (ET)', 'Open', 'High', 'Low', 'Close', 'Volume'])
    for t, o, h, l, c in five:
        ws.append([t, o, h, l, c, None])
    path = os.path.join(out_dir, f'{tick}_5min.xlsx')
    wb.save(path)
    print(f'  {tick}: {len(one)} 1-min bars -> {len(five)} 5-min bars ({rth} regular-session) '
          f'over {len(days)} sessions, {days[0]} -> {days[-1]}\n  wrote {path}')


if __name__ == '__main__':
    main()
