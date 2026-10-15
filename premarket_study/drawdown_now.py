"""
Where does today's drawdown sit against the ones this book has recovered from?

A live decision-support question, not a backtest: yields jumped on US inflation
figures, the book is down, and the choice is whether to act. §3.55 measured every
10% drawdown each name has had since April 2024 and how long it took to come
back. This places the CURRENT episode inside that distribution, name by name,
and reports how much of the book is under water at once -- because §3.55 also
found the book largely freezes together (55% of sessions have five or more names
10% down, 11% have all nine), so "a lot of the book is down" is the normal state
of this book, not a signal by itself.

Prices come from the live workbook's Query sheet, which runs past the end of the
5-minute archive. Holdings come from the Active Trading blotter, so the P&L
reported is the actual open position, not a simulated one.

Usage:  python3 drawdown_now.py <workbook.xlsx>
"""
import datetime as dt
import json
import statistics
import sys

import openpyxl

BOOK = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'GM', 'VLO', 'CF', 'MRVL']


def _d(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)):
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(v)))
    return None


def load_query(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    q = wb['Query']
    hdr = [c.value for c in next(q.iter_rows(min_row=1, max_row=1))]
    ix = {h: i for i, h in enumerate(hdr) if h}
    dts, px = [], {n: [] for n in BOOK}
    for r in q.iter_rows(min_row=2, values_only=True):
        if not r or r[0] is None:
            continue
        d = _d(r[0])
        if d is None:
            continue
        vals = {}
        ok = True
        for n in BOOK:
            c = r[ix[f'{n}_C']] if f'{n}_C' in ix else None
            if not isinstance(c, (int, float)):
                ok = False
                break
            vals[n] = float(c)
        if not ok:
            continue
        dts.append(d)
        for n in BOOK:
            px[n].append(vals[n])
    return wb, dts, px


def episodes_past(dts, C, depth=0.10):
    """Same construction as dip_recovery.py, but returning the OPEN episode too."""
    out, peak, peak_i, i, n = [], C[0], 0, 1, len(C)
    while i < n:
        if C[i] >= peak:
            peak, peak_i = C[i], i
            i += 1
            continue
        trough, trough_i, hit_i, j = C[i], i, None, i
        while j < n and C[j] < peak:
            if C[j] < trough:
                trough, trough_i = C[j], j
            if hit_i is None and C[j] <= peak*(1 - depth):
                hit_i = j
            j += 1
        rec = j < n
        if hit_i is not None:
            end = j if rec else n - 1
            out.append(dict(recovered=rec, depth=trough/peak - 1,
                            peak_date=dts[peak_i], hit_date=dts[hit_i],
                            end_date=dts[end], cal_hit=(dts[end] - dts[hit_i]).days,
                            sess_hit=end - hit_i))
        if rec:
            peak, peak_i, i = C[j], j, j + 1
        else:
            break
    return out


def main():
    path = sys.argv[1]
    wb, dts, px = load_query(path)
    today = dts[-1]
    print(f'Query runs {dts[0]} .. {today}  ({len(dts)} sessions)\n')

    print(f'{"name":6s}{"close":>9s}{"peak":>9s}{"peak date":>13s}{"below pk":>10s}'
          f'{"since pk":>10s}{"1d":>7s}{"5d":>8s}{"20d":>8s}')
    state = {}
    for n in BOOK:
        C = px[n]
        pk, pk_i = C[0], 0
        for i, c in enumerate(C):
            if c >= pk:
                pk, pk_i = c, i
        below = C[-1]/pk - 1
        r1 = C[-1]/C[-2] - 1
        r5 = C[-1]/C[-6] - 1 if len(C) > 5 else None
        r20 = C[-1]/C[-21] - 1 if len(C) > 20 else None
        state[n] = dict(close=C[-1], peak=pk, peak_date=str(dts[pk_i]), below=below,
                        sess_since_peak=len(C)-1-pk_i,
                        cal_since_peak=(today - dts[pk_i]).days,
                        r1=r1, r5=r5, r20=r20)
        print(f'{n:6s}{C[-1]:>9.2f}{pk:>9.2f}{str(dts[pk_i]):>13s}{below*100:>9.1f}%'
              f'{state[n]["cal_since_peak"]:>9d}d{r1*100:>6.1f}%{r5*100:>7.1f}%'
              f'{r20*100:>7.1f}%', flush=True)

    nuw = sum(1 for n in BOOK if state[n]['below'] <= -0.10)
    print(f'\n  {nuw} of 9 are 10% or more below their own running peak.')
    print(f'  §3.55 base rates on this book: 55% of sessions have >=5 under water, '
          f'11% have all nine.')

    print(f'\n{"="*86}\nTHIS EPISODE vs THE ONES THIS BOOK RECOVERED FROM\n')
    print(f'{"name":6s}{"now below":>11s}{"age":>7s}{"| past 10% episodes: n":>24s}'
          f'{"med depth":>11s}{"med recovery":>14s}{"P(rec<=50cal)":>15s}  deeper than')
    out = {}
    for n in BOOK:
        C = px[n]
        eps = episodes_past(dts, C)
        closed = [e for e in eps if e['recovered']]
        cur = state[n]['below']
        age = state[n]['cal_since_peak']
        if closed:
            med_depth = statistics.median([e['depth'] for e in closed])
            med_rec = statistics.median([e['cal_hit'] for e in closed])
            p50 = sum(1 for e in eps if e['recovered'] and e['cal_hit'] <= 50)/len(eps)*100
            deeper = sum(1 for e in closed if e['depth'] > cur)   # past dips shallower than now
            frac = f'{deeper}/{len(closed)}'
        else:
            med_depth = med_rec = p50 = None
            frac = '-'
        out[n] = dict(now=cur, age_cal=age, n_past=len(eps), n_closed=len(closed),
                      med_depth=med_depth, med_rec_cal=med_rec, p_rec_50=p50,
                      shallower_than_now=frac)
        print(f'{n:6s}{cur*100:>10.1f}%{age:>6d}d{len(closed):>24d}'
              f'{(f"{med_depth*100:.1f}%" if med_depth else "-"):>11s}'
              f'{(f"{med_rec:.0f}d" if med_rec else "-"):>14s}'
              f'{(f"{p50:.0f}%" if p50 is not None else "-"):>15s}  {frac} past dips',
              flush=True)
    print('\n  "deeper than" = how many of this name\'s PAST recovered 10% dips were '
          'SHALLOWER\n  than where it sits today.')
    json.dump(dict(today=str(today), state={k: {kk: (str(vv) if isinstance(vv, dt.date) else vv)
                                               for kk, vv in v.items()}
                                           for k, v in state.items()},
                   episodes=out),
              open('drawdown_now.json', 'w'), indent=1, default=str)
    return wb


if __name__ == '__main__':
    main()
    print('\nDONE', flush=True)
