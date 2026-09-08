"""
Structuring the discretionary book (user, 8 Sep 2026): can dislocation entries
of the kind the user already makes (AVGO on the MRVL/Google pop-and-drop, MU
at 912 "well below where it trades") be given PRE-DEFINED exits that clear
~3%/hold-week, killing the stock-watching without killing the judgement?

Mechanical PROXY of the setup (the human stays in charge of the real trigger;
this only asks whether the *shape* pays):
  signal day i: close >= 3% below its 10-day mean AND 5-day mean true-range%
  >= 1.3x its trailing 60-day median (violent vol). Buy next OPEN.
Exit bracket fixed at entry: GTC limit at entry x (1+T); time-stop at the open
after N sessions. Non-overlapping per name (no new signal while a position is
open). Universe: every ticker with a 5-minute file (book + judged candidates)
— the disc book is not confined to the nine.

Caveats stated where they bite: daily bars cannot order open vs high on the
entry day, so entry-day target hits are counted (mild optimism, same
convention as the book's same-day fills which run ~41% of trades); costs
0.005+0.0095/sh ignored (basis points at these prices).

Output: grid of T x N with hit rate, avg return, avg hold, return per
hold-week — full sample and both halves (SPLIT 2025-05-23).
"""
import datetime as dt
import json
import statistics

SPLIT = dt.date(2025, 5, 23)          # the standard half-sample split


def load_from_workbook(path):
    """Fallback data source: the trading workbook's Query sheet (daily OHLC,
    nine current names) — used when the 5-minute archive is not on disk."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    q = wb['Query']
    heads = {q.cell(row=1, column=c).value: c for c in range(1, q.max_column + 1)}
    names = sorted({h.split('_')[0] for h in heads if h and '_' in h})
    out = {}
    for nm in names:
        dts, O, H, L, C = [], [], [], [], []
        for r in range(2, q.max_row + 1):
            d = q.cell(row=r, column=1).value
            o = q.cell(row=r, column=heads[f'{nm}_O']).value
            if d is None or not isinstance(o, (int, float)):
                continue
            if isinstance(d, (int, float)):
                d = dt.date(1899, 12, 30) + dt.timedelta(days=int(d))
            dts.append(d)
            O.append(o)
            H.append(q.cell(row=r, column=heads[f'{nm}_H']).value)
            L.append(q.cell(row=r, column=heads[f'{nm}_L']).value)
            C.append(q.cell(row=r, column=heads[f'{nm}_C']).value)
        out[nm] = (dts, O, H, L, C)
    return out

OUT = 'disc_structure.json'
NAMES = ['TSM', 'VRT', 'VST', 'RKLB', 'MU', 'GM', 'VLO', 'CF', 'MRVL',
         'AVGO', 'NVDA', 'AMD', 'SMCI', 'CEG', 'FCX', 'NEM', 'UAL', 'LEN']
TGTS = [0.03, 0.05, 0.07, 0.10]
CAPS = [5, 10, 15, 20]
DIP, VOLX = 0.97, 1.3


def d_of(x):
    return x.date() if hasattr(x, 'date') else x


def signals(dts, O, H, L, C):
    n = len(C)
    tr = [(H[i] - L[i]) / C[i] for i in range(n)]
    out = []
    for i in range(65, n - 1):
        dma10 = statistics.fmean(C[i - 9:i + 1])
        if C[i] >= DIP * dma10:
            continue
        v5 = statistics.fmean(tr[i - 4:i + 1])
        med60 = statistics.median(tr[i - 59:i + 1])
        if med60 <= 0 or v5 < VOLX * med60:
            continue
        out.append(i)
    return out


def run(data, tgt, cap):
    trades = []
    for nm, (dts, O, H, L, C) in data.items():
        n = len(C)
        busy_until = -1
        for i in signals(dts, O, H, L, C):
            if i < busy_until or i + 1 >= n:
                continue
            px = O[i + 1]
            target = px * (1 + tgt)
            exit_j, exit_px = None, None
            for j in range(i + 1, min(i + 1 + cap, n)):
                if H[j] >= target:
                    exit_j, exit_px = j, target
                    break
            if exit_j is None:
                j = min(i + 1 + cap, n - 1)
                exit_j, exit_px = j, O[j]
            mae = min(L[k] for k in range(i + 1, exit_j + 1)) / px - 1
            trades.append(dict(name=nm, entry=d_of(dts[i + 1]), px=px,
                               ret=exit_px / px - 1,
                               hold=(d_of(dts[exit_j]) - d_of(dts[i + 1])).days,
                               hit=exit_px == target, mae=mae))
            busy_until = exit_j + 1
    return trades


def stats(tr):
    if not tr:
        return None
    rets = [t['ret'] for t in tr]
    holds = [max(t['hold'], 1) for t in tr]
    per_wk = statistics.fmean(r / h * 7 for r, h in zip(rets, holds))
    return dict(n=len(tr), hit=sum(t['hit'] for t in tr) / len(tr),
                avg_ret=statistics.fmean(rets), med_hold=statistics.median(holds),
                per_week=per_wk, worst=min(rets),
                mae_med=statistics.median(t['mae'] for t in tr))


def main():
    import os, sys
    if len(sys.argv) > 1:
        data = load_from_workbook(sys.argv[1])
    else:
        from fresh_opt_cands import daily_from_5min
        data = {}
        for nm in NAMES:
            try:
                data[nm] = daily_from_5min(nm)
            except FileNotFoundError:
                pass
    print(f'universe: {len(data)} names: {sorted(data)}')
    res = {}
    print(f"{'T':>4s} {'cap':>4s} | {'n':>5s} {'hit':>5s} {'avg':>7s} {'hold':>5s}"
          f" {'%/wk':>7s} {'worst':>7s} | halves %/wk (train/test)")
    for tgt in TGTS:
        for cap in CAPS:
            tr = run(data, tgt, cap)
            s = stats(tr)
            a = stats([t for t in tr if t['entry'] < SPLIT])
            b = stats([t for t in tr if t['entry'] >= SPLIT])
            res[f'{tgt}_{cap}'] = dict(full=s, train=a, test=b)
            print(f'{tgt*100:3.0f}% {cap:4d} | {s["n"]:5d} {s["hit"]*100:4.0f}%'
                  f' {s["avg_ret"]*100:+6.2f}% {s["med_hold"]:5.0f}'
                  f' {s["per_week"]*100:+6.2f}% {s["worst"]*100:+6.1f}%'
                  f' | {a["per_week"]*100:+.2f}% / {b["per_week"]*100:+.2f}%')
    with open(OUT, 'w') as f:
        json.dump(res, f, indent=1, default=str)
    print(f'saved {OUT}')


if __name__ == '__main__':
    main()
