"""
box_5min_import.py — turn a Box text extraction into a data_5min/ file
(8 Oct 2026).

HANDOVER 3.28d recorded that Box MCP "can search/list but CANNOT download
binaries". That is no longer true: `get_file_content` returns the sheet's
extracted text, the harness writes it to disk when it is large, and the result
is EXACT. Verified on LEN against the locally held xlsx: 53,643 of 53,643 bars
identical, zero mismatches. So the 5-minute archive no longer has to be
re-uploaded by hand after a container recycle.

The workflow (the Box calls are made by the assistant, not by this script):
  1. mcp__Box__search_files_keyword / list_folder_content_by_folder_id
     -> the file id for "<TICKER> 5min Apr2024-Aug2026.xlsx"
  2. mcp__Box__get_file_content(file_id) -> harness saves the text to a path
  3. python box_5min_import.py <that path> <TICKER>
     -> premarket_study/data_5min/<TICKER>_5min.xlsx, the layout
        minute_index and fresh_opt_cands.daily_from_5min already read

Datetime rendering varies between files because the extraction reflects each
sheet's own display format -- LEN comes back as "2024-04-01 7:35:00", SKHY as
"2026-07-13 04:00" -- so several formats are tried rather than one assumed.

Validation before anything is written: bar count, span, strictly increasing
timestamps, no duplicates, and high >= max(open, close) >= min(open, close)
>= low on every bar. A file that fails is not written.

Usage:
    python box_5min_import.py <extracted.txt> <TICKER> [--out-dir DIR]
    python box_5min_import.py <extracted.txt> <TICKER> --check-against <xlsx>
"""
import argparse
import datetime as dt
import os
import sys

import openpyxl

FMTS = ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
        '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M',
        '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M',
        '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M')
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'premarket_study', 'data_5min')


def parse_dt(s):
    s = s.strip()
    for f in FMTS:
        try:
            return dt.datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def read_extract(path):
    """Rows of (datetime, O, H, L, C, V) from the tab-separated extraction."""
    rows = []
    for line in open(path, encoding='utf-8', errors='replace'):
        p = line.rstrip('\n').split('\t')
        if len(p) < 6:
            continue
        d = parse_dt(p[1])
        if d is None:
            continue
        try:
            vals = [float(x) for x in p[2:6]]
            vol = float(p[6]) if len(p) > 6 and p[6].strip() else 0.0
        except ValueError:
            continue
        rows.append((d, *vals, vol))
    return rows


USED0, USED1 = dt.time(4, 0), dt.time(16, 0)


def validate(rows, ticker):
    """Integrity of the windows the pipeline actually reads: pre-market from
    04:00 for the PM cache and regular hours to 16:00 for the daily bars.
    Faults in the after-hours tail are REPORTED but do not refuse the file —
    SMCI's Box export splices two different series over 19:00-19:55 on 6 Nov in
    both 2024 and 2025, which is real, but no part of the pipeline reads it."""
    errs = []
    used = [r for r in rows if USED0 <= r[0].time() < USED1]
    tail = len(rows) - len(used)
    seen_t, dup_t = set(), 0
    for r in rows:
        if not (USED0 <= r[0].time() < USED1):
            if r[0] in seen_t:
                dup_t += 1
            seen_t.add(r[0])
    if dup_t:
        print(f'  NOTE: {dup_t} duplicate timestamps in the after-hours tail '
              f'({tail} bars outside 04:00-16:00) — reported, not fatal; the '
              f'pipeline does not read them')
    rows = used
    if len(rows) < 1000:
        errs.append(f'only {len(rows)} bars — too few for a 2-year 5-minute file')
    seen, prev = set(), None
    dupes = backwards = ohlc = 0
    for d, o, h, l, c, _ in rows:
        if d in seen:
            dupes += 1
        seen.add(d)
        if prev is not None and d < prev:
            backwards += 1
        prev = d
        if not (h >= max(o, c) - 1e-9 and l <= min(o, c) + 1e-9 and h >= l - 1e-9):
            ohlc += 1
    if dupes:
        errs.append(f'{dupes} duplicate timestamps')
    if backwards:
        errs.append(f'{backwards} out-of-order timestamps')
    if ohlc:
        errs.append(f'{ohlc} bars where high/low do not bracket open/close')
    days = {d.date() for d, *_ in rows}
    pre = sum(1 for d, *_ in rows if d.time() < dt.time(9, 30))
    print(f'  {ticker}: {len(rows)} bars in 04:00-16:00 over {len(days)} sessions, '
          f'{rows[0][0]} -> {rows[-1][0]}, {pre} pre-market')
    return errs


def write_xlsx(rows, ticker, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f'{ticker}_5min.xlsx')
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(f'{ticker} 5min')
    ws.append(['Datetime (ET)', 'Open', 'High', 'Low', 'Close', 'Volume'])
    for r in rows:
        ws.append(list(r))
    wb.save(path)
    return path


def check_against(rows, xlsx):
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    next(it)
    ref = [(r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]))
           for r in it if isinstance(r[0], dt.datetime) and r[1] is not None]
    wb.close()
    if len(ref) != len(rows):
        print(f'  CHECK: bar counts differ — extraction {len(rows)}, reference {len(ref)}')
        return False
    bad = sum(1 for a, b in zip(rows, ref)
              if a[0] != b[0] or max(abs(a[i] - b[i]) for i in range(1, 5)) > 1e-9)
    print(f'  CHECK against {os.path.basename(xlsx)}: '
          f'{len(ref)-bad}/{len(ref)} bars identical, {bad} mismatches')
    return bad == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('extract')
    ap.add_argument('ticker')
    ap.add_argument('--out-dir', default=DEFAULT_OUT)
    ap.add_argument('--check-against')
    a = ap.parse_args()

    rows = read_extract(a.extract)
    if not rows:
        sys.exit('no parseable rows — check the file is a 5-minute extraction')
    errs = validate(rows, a.ticker)
    rows = [r for r in rows if USED0 <= r[0].time() < USED1]
    if a.check_against and not check_against(rows, a.check_against):
        errs.append('does not match the reference file')
    if errs:
        print('  REFUSED, nothing written:')
        for e in errs:
            print(f'    - {e}')
        sys.exit(1)
    path = write_xlsx(rows, a.ticker, a.out_dir)
    print(f'  wrote {path}')


if __name__ == '__main__':
    main()
