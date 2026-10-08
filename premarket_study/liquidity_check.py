"""
liquidity_check.py — can the book's order size be absorbed without moving the
price? (user, 8 Oct 2026)

User: "For STNG, if average volume is below 1m shares at $80, that is under
$80m traded a day. I want to buy $0.5-1m on a given day. Will my activity move
the price?"

Participation against ADV is the usual answer and it is the wrong denominator
here. The model does not work an order across the day: it rests a LIMIT BUY
below the market from the open and is filled, if at all, by someone else's
selling. So the question is not what fraction of the day's volume the order is,
but whether the volume that trades AT OR BELOW the bid can absorb it. That is a
much smaller number than ADV and it is the one that binds.

Measured per name from the 5-minute archive (regular hours only):
  - daily dollar volume: median, and the 10th percentile (thin days bind first)
  - the order as a share of ADV, at $0.5m and $1m
  - dollar volume trading in bars that touch a bid 2% below the previous close
    -- the depth actually available to a resting order at the model's depth
  - the share of that which trades in the first hour, where §3.20 showed
    56-80% of fills happen

The exit side is noted but not modelled: the take-profit is also a resting
limit (passive), but the 50-day time stop sells AT THE OPEN, which is
marketable and is where impact actually lives.

Usage: python liquidity_check.py [TICKER ...]
"""
import collections
import datetime as dt
import json
import os
import statistics
import sys

import openpyxl

OUT = 'liquidity_check.json'
DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_5min')
RTH0, RTH1 = dt.time(9, 30), dt.time(16, 0)
HOUR1 = dt.time(10, 30)
DEPTH = 0.02                      # a bid 2% below the previous close
ORDERS = (500_000, 1_000_000)


def load_bars(nm):
    """{date: [(time, close, dollar_volume, low)]} for regular hours."""
    wb = openpyxl.load_workbook(os.path.join(DIR, f'{nm}_5min.xlsx'),
                                read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    next(it)
    by = collections.defaultdict(list)
    for r in it:
        d = r[0]
        if not isinstance(d, dt.datetime) or r[1] is None:
            continue
        t = d.time()
        if not (RTH0 <= t < RTH1):
            continue
        o, h, l, c = float(r[1]), float(r[2]), float(r[3]), float(r[4])
        v = float(r[5]) if len(r) > 5 and r[5] is not None else 0.0
        by[d.date()].append((t, c, c * v, l))
    wb.close()
    return {d: sorted(v) for d, v in by.items()}


def analyse(nm):
    bars = load_bars(nm)
    days = sorted(bars)
    dv = [sum(b[2] for b in bars[d]) for d in days]
    closes = {d: bars[d][-1][1] for d in days}

    at_depth, at_depth_h1, hit_days = [], [], 0
    for i in range(1, len(days)):
        d, prev = days[i], days[i - 1]
        bid = closes[prev] * (1 - DEPTH)
        touched = [b for b in bars[d] if b[3] <= bid]
        if not touched:
            continue
        hit_days += 1
        at_depth.append(sum(b[2] for b in touched))
        at_depth_h1.append(sum(b[2] for b in touched if b[0] < HOUR1))
    return dict(
        n_days=len(days), adv=statistics.median(dv),
        adv_p10=statistics.quantiles(dv, n=10)[0], px=statistics.median(closes.values()),
        depth_days=hit_days, depth_frac=hit_days / max(len(days) - 1, 1),
        depth_dv=statistics.median(at_depth) if at_depth else 0.0,
        depth_dv_p10=statistics.quantiles(at_depth, n=10)[0] if len(at_depth) > 10 else 0.0,
        depth_dv_h1=statistics.median(at_depth_h1) if at_depth_h1 else 0.0)


def main():
    names = sys.argv[1:] or sorted(f[:-len('_5min.xlsx')] for f in os.listdir(DIR)
                                   if f.endswith('_5min.xlsx'))
    res = {}
    print(f'regular hours only; bid depth {DEPTH*100:.0f}% below the previous close\n')
    print(f'  {"name":6s}{"px":>8s}{"ADV $m":>9s}{"p10 $m":>9s}'
          f'{"$1m/ADV":>9s}{"days@bid":>10s}{"$ at bid":>10s}{"first hr":>10s}'
          f'{"$1m/bid$":>10s}')
    for nm in names:
        try:
            a = analyse(nm)
        except FileNotFoundError:
            continue
        res[nm] = a
        print(f'  {nm:6s}{a["px"]:>8.0f}{a["adv"]/1e6:>9.1f}{a["adv_p10"]/1e6:>9.1f}'
              f'{1e6/a["adv"]*100:>8.2f}%{a["depth_frac"]*100:>9.0f}%'
              f'{a["depth_dv"]/1e6:>9.1f}m{a["depth_dv_h1"]/1e6:>9.1f}m'
              f'{(1e6/a["depth_dv"]*100 if a["depth_dv"] else 0):>9.1f}%')

    print(f'\n  order as a share of the dollar volume trading AT OR BELOW the bid '
          f'(median fill day):')
    print(f'  {"name":6s}' + ''.join(f'{f"${o/1e6:.1f}m":>10s}' for o in ORDERS)
          + '      ... and on a thin (10th pct) fill day')
    for nm in names:
        if nm not in res:
            continue
        a = res[nm]
        cells = ''.join(f'{(o/a["depth_dv"]*100 if a["depth_dv"] else 0):>9.1f}%'
                        for o in ORDERS)
        thin = ''.join(f'{(o/a["depth_dv_p10"]*100 if a["depth_dv_p10"] else 0):>9.1f}%'
                       for o in ORDERS)
        print(f'  {nm:6s}{cells}      {thin}')

    with open(OUT, 'w') as f:
        json.dump(res, f, indent=1, default=str)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
