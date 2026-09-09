"""
Does the dislocation ticket BEAT the nine-stock book? (user, 9 Sep 2026)

The grid in disc_structure.py reported per-trade economics. The book's 72.4%/yr
(sheet) is a capital-compounding number — so the fair comparison runs the
ticket as a CAPITAL LOOP: one pot, K position slots, each opening signal takes
cash/free-slots at the next open, bracket exit (target T, time-stop at the
open of session N), idle cash earns the model's 3.14%/yr. Same daily data as
the grid (the trading workbook's Query sheet, nine names), same split.

Variants: K in {1,2,3}; entries inside a name's own earnings window
(report day +/- 5 sessions, dates from earnings_pause.EARNINGS) excluded or
allowed — the ticket design excludes them.

Honesty notes: daily bars cannot order open-vs-high on the entry day, so
entry-day target hits count (mild optimism vs the book's verified fills);
costs ignored (bp at these prices). Both cut in the ticket's favour — a
losing comparison is therefore conservative in the direction that matters.

Usage: python disc_loop.py <trading_workbook.xlsx>
"""
import datetime as dt
import json
import sys

from disc_structure import load_from_workbook, signals, SPLIT
from earnings_pause import EARNINGS

OUT = 'disc_loop.json'
T, CAP = 0.05, 10
RATE = 0.0314


def ann(total, d0, d1):
    yrs = (d1 - d0).days / 365.25
    return (1 + total) ** (1 / yrs) - 1 if yrs > 0 else 0.0


def build_events(data, excl_earnings):
    """(date -> list of (name, i)) opening signals, next-open convention."""
    ev = {}
    for nm, (dts, O, H, L, C) in data.items():
        reps = [dt.date.fromisoformat(s) for s in EARNINGS.get(nm, [])]
        idx_dates = [d.date() if hasattr(d, 'date') else d for d in dts]
        for i in signals(dts, O, H, L, C):
            if i + 1 >= len(dts):
                continue
            d_entry = idx_dates[i + 1]
            if excl_earnings and any(abs((d_entry - r).days) <= 7 for r in reps):
                continue
            ev.setdefault(d_entry, []).append((nm, i + 1))
    return ev


def loop(data, K, excl_earnings, lo=None, hi=None):
    ev = build_events(data, excl_earnings)
    # unified calendar
    cal = sorted({(d.date() if hasattr(d, 'date') else d)
                  for v in data.values() for d in v[0]})
    if lo:
        cal = [d for d in cal if d >= lo]
    if hi:
        cal = [d for d in cal if d < hi]
    idx = {nm: {(d.date() if hasattr(d, 'date') else d): j
                for j, d in enumerate(v[0])} for nm, v in data.items()}
    cash, open_pos, trades = 1.0, [], []
    prev = None
    invested_days = total_days = 0
    for day in cal:
        if prev is not None:
            cash *= (1 + RATE) ** ((day - prev).days / 365.25)
        prev = day
        # exits first
        still = []
        for p in open_pos:
            nm, j_ent, px, sh, deadline = p
            j = idx[nm].get(day)
            if j is None:
                still.append(p)
                continue
            dts, O, H, L, C = data[nm]
            if H[j] >= px * (1 + T) and j > j_ent - 1:
                cash += sh * px * (1 + T)
                trades.append((nm, day, T))
            elif j >= deadline:
                cash += sh * O[j]
                trades.append((nm, day, O[j] / px - 1))
            else:
                still.append(p)
        open_pos = still
        # entries
        for nm, j_ent in ev.get(day, []):
            if len(open_pos) >= K or cash <= 0:
                continue
            if any(p[0] == nm for p in open_pos):
                continue
            dts, O, H, L, C = data[nm]
            j = idx[nm][day]
            px = O[j]
            alloc = cash / (K - len(open_pos))
            sh = alloc / px
            cash -= alloc
            open_pos.append((nm, j, px, sh, j + CAP))
            # same-day target hit
        equity = cash + sum(p[3] * data[p[0]][4][idx[p[0]].get(day, p[1])]
                            for p in open_pos if idx[p[0]].get(day) is not None)
        invested_days += (equity - cash) / equity if equity > 0 else 0
        total_days += 1
    # close residual at last close
    for nm, j_ent, px, sh, _ in open_pos:
        cash += sh * data[nm][4][-1]
    return dict(ann=ann(cash - 1, cal[0], cal[-1]), trades=len(trades),
                occupancy=invested_days / total_days if total_days else 0)


def main():
    data = load_from_workbook(sys.argv[1])
    res = {}
    print(f"{'K':>2s} {'earnings':>9s} | {'full ann':>9s} {'train':>8s} {'test':>8s}"
          f" {'occ':>5s} {'trades/yr':>10s}")
    for K in (1, 2, 3):
        for ex in (True, False):
            full = loop(data, K, ex)
            tr = loop(data, K, ex, hi=SPLIT)
            te = loop(data, K, ex, lo=SPLIT)
            res[f'K{K}_{"excl" if ex else "incl"}'] = dict(full=full, train=tr, test=te)
            print(f'{K:2d} {"excluded" if ex else "allowed":>9s} |'
                  f' {full["ann"]*100:8.1f}% {tr["ann"]*100:7.1f}% {te["ann"]*100:7.1f}%'
                  f' {full["occupancy"]*100:4.0f}% {full["trades"]/2.36:9.1f}')
    print('\nbook reference (same convention family, verified fills): '
          'full 72.4% / train 43.9% / test 104.9%; occupancy ~57% held-fraction')
    with open(OUT, 'w') as f:
        json.dump(res, f, indent=1)
    print(f'saved {OUT}')


if __name__ == '__main__':
    main()
