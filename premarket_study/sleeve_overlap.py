"""
How different are the two sleeves, really?

Bayes and OU are both dip-buyers: estimate fair value, bid a spread below it,
sell a fixed premium. If their fills land on the same days at similar prices,
the book is running one algorithm twice and the second sleeve's seat is open
for something orthogonal. If they fill on different days, they genuinely
diversify entry timing and both earn their keep.

Per name (verified fills, deployed/reference params):
  - fills per sleeve and entry-day overlap (days BOTH sleeves entered)
  - per-sleeve compounded annualised return (each sleeve runs half the capital)
  - correlation of per-trade outcomes when both entered the same day
  - correlation of monthly sleeve P&L (by exit month)
"""
import collections
import datetime
import json

import numpy as np

from engine import Params, run_model
from fresh_opt import SPLIT, annualise
from fresh_opt_cands import daily_from_5min, ref_params, aw_params
from live5_load import load as load_book, STOCKS as BOOK
from minute_index import make_checker
from earnings_pause import trades_from_frames

NAMES = BOOK + ['GM', 'VLO', 'CF', 'MRVL']


def params_for(s, book_params):
    if s in BOOK:
        return book_params[s]
    if s == 'MRVL':
        t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                    bayes_pct=0.5, years=2.2, ou_W=80)
        return aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    return ref_params(s)


def main():
    book_data, book_params, _ = load_book()
    print(f'{"name":6s}{"B fills":>8s}{"O fills":>8s}{"both-day":>9s}{"overlap":>8s}'
          f'{"B ann":>8s}{"O ann":>8s}{"same-day r":>11s}{"monthly r":>10s}')
    tot = dict(b=0, o=0, both=0)
    all_m = []
    for s in NAMES:
        if s in BOOK:
            dts, O, H, L, C = book_data[s]
        else:
            dts, O, H, L, C = daily_from_5min(s)
        p = params_for(s, book_params)
        chk = make_checker(s, dts, O)
        r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                      collect=True)
        fr = r.frames
        t1 = trades_from_frames(dts, fr, 't1', fr['X'])
        t2 = trades_from_frames(dts, fr, 't2', fr['AM'])
        d1 = {dts[i]: (xp / bp - 1) for (i, j, bp, xp, st) in t1 if j is not None}
        d2 = {dts[i]: (xp / bp - 1) for (i, j, bp, xp, st) in t2 if j is not None}
        both = sorted(set(d1) & set(d2))
        ov = len(both) / max(1, min(len(d1), len(d2)))
        # same-day per-trade outcome correlation
        if len(both) >= 5:
            r_same = np.corrcoef([d1[d] for d in both], [d2[d] for d in both])[0, 1]
        else:
            r_same = float('nan')
        # per-sleeve compounded return
        def ann_of(dd):
            g = 1.0
            for v in dd.values():
                g *= 1 + v
            return annualise(g - 1, dts, 0, len(dts) - 1)
        # monthly P&L correlation (by exit month)
        def monthly(trades):
            m = collections.defaultdict(float)
            for (i, j, bp, xp, st) in trades:
                if j is None:
                    continue
                m[(dts[j].year, dts[j].month)] += xp / bp - 1
            return m
        m1, m2 = monthly(t1), monthly(t2)
        months = sorted(set(m1) | set(m2))
        v1 = [m1.get(k, 0.0) for k in months]
        v2 = [m2.get(k, 0.0) for k in months]
        r_m = np.corrcoef(v1, v2)[0, 1] if len(months) >= 6 else float('nan')
        all_m.append((v1, v2))
        tot['b'] += len(d1); tot['o'] += len(d2); tot['both'] += len(both)
        print(f'{s:6s}{len(d1):>8d}{len(d2):>8d}{len(both):>9d}{ov*100:>7.0f}%'
              f'{ann_of(d1)*100:>7.1f}%{ann_of(d2)*100:>7.1f}%'
              f'{r_same:>11.2f}{r_m:>10.2f}')
    print(f'\nTOTAL  B {tot["b"]}  O {tot["o"]}  both-day {tot["both"]} '
          f'(overlap {tot["both"]/min(tot["b"], tot["o"])*100:.0f}% of smaller sleeve)')


if __name__ == '__main__':
    main()
