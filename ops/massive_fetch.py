"""
massive_fetch.py — pull aggregates from the Massive API (api.massive.com) into
the archive formats the book and the studies already read (HANDOVER 3.103).

  5min  -> <out>/<TICKER>_5min.xlsx   sheet "<TICKER> 5min", columns
           Datetime (ET) | Open | High | Low | Close | Volume, 04:00-20:00 ET
           (the data_5min / data_bear layout; Volume included)
  day   -> <out>/<TICKER>_daily.csv   date,open,high,low,close,volume,
           dollar_volume, first_hour_dollar_volume (the last two from 5-minute
           bars when --with-fh is given: 09:30-10:30 ET, close x volume)

The API key is read ONLY from the environment variable MASSIVE_API_KEY. It is
never written to disk, never printed, and scrubbed from any error text.

Usage:
    MASSIVE_API_KEY=... python3 ops/massive_fetch.py 5min 2024-04-01 2026-10-23 out_dir TSM VRT ...
    MASSIVE_API_KEY=... python3 ops/massive_fetch.py day  2024-04-01 2026-10-23 out_dir --with-fh TSM ...
Options: --pause S (seconds between calls; 13 for a 5-calls/min plan), --adjusted false.
"""
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import openpyxl

BASE = 'https://api.massive.com'
ET = ZoneInfo('America/New_York')
KEY = os.environ.get('MASSIVE_API_KEY', '')


def scrub(s):
    return str(s).replace(KEY, '***') if KEY else str(s)


def get(url, pause):
    sep = '&' if '?' in url else '?'
    full = f'{url}{sep}apiKey={urllib.parse.quote(KEY)}'
    for attempt in range(8):
        try:
            with urllib.request.urlopen(full, timeout=60) as r:
                data = json.loads(r.read().decode())
            time.sleep(pause)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                wait = min(120, 15 * 2 ** attempt)
                print(f'    HTTP {e.code}, retry in {wait}s', flush=True)
                time.sleep(wait)
                continue
            raise RuntimeError(scrub(f'HTTP {e.code}: {e.read()[:300]}')) from None
        except (urllib.error.URLError, TimeoutError) as e:
            wait = min(120, 10 * 2 ** attempt)
            print(f'    network error {scrub(e)}, retry in {wait}s', flush=True)
            time.sleep(wait)
    raise RuntimeError('gave up after 8 attempts')


def aggs(tk, mult, span, lo, hi, adjusted, pause):
    """Every bar in [lo, hi], following next_url pagination."""
    url = (f'{BASE}/v2/aggs/ticker/{urllib.parse.quote(tk)}/range/{mult}/{span}/{lo}/{hi}'
           f'?adjusted={adjusted}&sort=asc&limit=50000')
    out = []
    while url:
        js = get(url, pause)
        out += js.get('results') or []
        nxt = js.get('next_url')
        url = nxt.split('&apiKey=')[0].split('?apiKey=')[0] if nxt else None
    seen, bars = set(), []
    for b in out:
        if b['t'] not in seen:
            seen.add(b['t'])
            bars.append(b)
    return sorted(bars, key=lambda b: b['t'])


def et(ms):
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).astimezone(ET).replace(tzinfo=None)


def five_min(tk, lo, hi, out, adjusted, pause):
    bars = aggs(tk, 5, 'minute', lo, hi, adjusted, pause)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f'{tk} 5min'
    ws.append(['Datetime (ET)', 'Open', 'High', 'Low', 'Close', 'Volume'])
    n = 0
    for b in bars:
        t = et(b['t'])
        if dt.time(4, 0) <= t.time() < dt.time(20, 0):
            ws.append([t, b['o'], b['h'], b['l'], b['c'], b.get('v')])
            n += 1
    path = os.path.join(out, f'{tk}_5min.xlsx')
    wb.save(path)
    days = sorted({et(b['t']).date() for b in bars})
    print(f'  {tk}: {n} bars over {len(days)} sessions {days[0] if days else "-"} -> '
          f'{days[-1] if days else "-"}  -> {path}', flush=True)
    return bars


def daily(tk, lo, hi, out, adjusted, pause, with_fh):
    d = aggs(tk, 1, 'day', lo, hi, adjusted, pause)
    fh = {}
    if with_fh:
        for b in aggs(tk, 5, 'minute', lo, hi, adjusted, pause):
            t = et(b['t'])
            if dt.time(9, 30) <= t.time() < dt.time(10, 30) and b.get('v'):
                fh[t.date()] = fh.get(t.date(), 0.0) + b['c'] * b['v']
    path = os.path.join(out, f'{tk}_daily.csv')
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['date', 'open', 'high', 'low', 'close', 'volume', 'dollar_volume',
                    'first_hour_dollar_volume'])
        for b in d:
            day = et(b['t']).date()
            vw = b.get('vw') or b['c']
            w.writerow([day, b['o'], b['h'], b['l'], b['c'], b.get('v'),
                        round((b.get('v') or 0) * vw), round(fh[day]) if day in fh else ''])
    print(f'  {tk}: {len(d)} daily bars -> {path}', flush=True)


def main():
    if not KEY:
        sys.exit('set MASSIVE_API_KEY in the environment')
    a = [x for x in sys.argv[1:]]
    pause = float(a[a.index('--pause') + 1]) if '--pause' in a else 0.25
    adjusted = a[a.index('--adjusted') + 1] if '--adjusted' in a else 'true'
    with_fh = '--with-fh' in a
    for flag in ('--pause', '--adjusted'):
        if flag in a:
            i = a.index(flag)
            del a[i:i + 2]
    a = [x for x in a if x != '--with-fh']
    mode, lo, hi, out, tickers = a[0], a[1], a[2], a[3], a[4:]
    os.makedirs(out, exist_ok=True)
    for tk in tickers:
        try:
            if mode == '5min':
                five_min(tk, lo, hi, out, adjusted, pause)
            else:
                daily(tk, lo, hi, out, adjusted, pause, with_fh)
        except Exception as e:                      # keep going; report without the key
            print(f'  {tk}: FAILED {scrub(e)}', flush=True)


if __name__ == '__main__':
    main()
