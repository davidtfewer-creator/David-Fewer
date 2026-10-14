"""
Is being deep below the peak a BAD time to be buying, or a good one?

The operational worry is specific: both sleeves fill, the name keeps falling,
and the capital is frozen. The obvious remedy is a veto -- don't let the second
sleeve fill when the name is already well below its running peak. But that only
helps if forward returns are genuinely worse from down there. If the name mean
-reverts, the veto would be refusing the best entries in the sample, and the
right rule would be the opposite one.

dip_stop_sweep.py could not settle this: a name has only 3-10 dip EPISODES, so
anything tuned on them is tuned on noise. This asks the same question with one
observation per SESSION instead -- roughly 600 per name, 5,300 pooled -- by
bucketing every session on how far the close sits below its running peak and
measuring what happened next.

Forward returns are close-to-close over 10, 20 and 50 sessions, which brackets
the 50-calendar-day stop. The last 50 sessions of each name are dropped so every
bucket has a full forward window.

This is model-free: no parameters, no fills, no fitting. It cannot say what the
book would have earned. It can say whether the premise of a drawdown veto holds.

Usage:  python3 dip_conditional.py
"""
import json
import statistics

from dip_recovery import BOOK
from fresh_opt_cands import daily_from_5min

BUCKETS = [(0.00, 0.02, 'at/near peak (0-2%)'),
           (0.02, 0.05, 'down 2-5%'),
           (0.05, 0.10, 'down 5-10%'),
           (0.10, 0.20, 'down 10-20%'),
           (0.20, 9.99, 'down >20%')]
FWD = (10, 20, 50)


def rows_for(nm):
    dts, O, H, L, C = daily_from_5min(nm)
    peak = C[0]
    out = []
    for i in range(len(C)):
        peak = max(peak, C[i])
        d = 1 - C[i]/peak                       # 0 at the peak, 0.10 = 10% below
        if i + max(FWD) >= len(C):
            continue
        out.append((d, [C[i + f]/C[i] - 1 for f in FWD]))
    return out


def main():
    allrows = {nm: rows_for(nm) for nm in BOOK}
    pooled = [r for nm in BOOK for r in allrows[nm]]
    print('forward close-to-close return by how far below the running peak the close sits\n')
    print(f'POOLED, all nine names ({len(pooled)} session-observations)\n')
    print(f'{"bucket":24s}{"n":>7s}{"share":>8s}' +
          ''.join(f'{f"+{f}d med":>12s}' for f in FWD) +
          ''.join(f'{f"+{f}d mean":>12s}' for f in FWD))
    res = {'pooled': {}}
    for lo, hi, lbl in BUCKETS:
        sel = [r for r in pooled if lo <= r[0] < hi]
        if not sel:
            continue
        med = [statistics.median([r[1][k] for r in sel])*100 for k in range(len(FWD))]
        mean = [statistics.fmean([r[1][k] for r in sel])*100 for k in range(len(FWD))]
        res['pooled'][lbl] = dict(n=len(sel), med=med, mean=mean)
        print(f'{lbl:24s}{len(sel):>7d}{len(sel)/len(pooled)*100:>7.0f}%' +
              ''.join(f'{v:>11.2f}%' for v in med) +
              ''.join(f'{v:>11.2f}%' for v in mean), flush=True)

    print(f'\nPER NAME — median forward 20-session return by bucket\n')
    print(f'{"name":6s}' + ''.join(f'{lbl.split("(")[0].strip():>20s}' for _, _, lbl in BUCKETS))
    res['per_name'] = {}
    for nm in BOOK:
        rs = allrows[nm]
        cells, store = [], {}
        for lo, hi, lbl in BUCKETS:
            sel = [r for r in rs if lo <= r[0] < hi]
            if len(sel) < 15:
                cells.append(f'{"-":>20s}')
                store[lbl] = None
                continue
            m = statistics.median([r[1][1] for r in sel])*100
            store[lbl] = dict(n=len(sel), med20=m)
            cells.append(f'{m:>14.1f}% ({len(sel):>3d})'[:20].rjust(20))
        res['per_name'][nm] = store
        print(f'{nm:6s}' + ''.join(cells), flush=True)
    print('\n  (cells with fewer than 15 observations are suppressed)')
    json.dump(res, open('dip_conditional.json', 'w'), indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()


def jointly_stuck():
    """Are the names under water at the SAME times?

    If being 10% down is idiosyncratic, a slow-recovering name is a diversifiable
    nuisance. If the book goes under water together, recovery time is systematic:
    the frozen-sleeve problem arrives for every name at once, exactly when free
    capital is most wanted. That distinction decides whether the metric belongs
    in position sizing or only in capacity planning.
    """
    import numpy as np
    from fresh_opt_cands import daily_from_5min
    series = {}
    for nm in BOOK:
        dts, O, H, L, C = daily_from_5min(nm)
        peak, u = C[0], {}
        for i, d in enumerate(dts):
            peak = max(peak, C[i])
            u[d] = 1 if C[i] <= peak*0.90 else 0
        series[nm] = u
    cal = sorted(set.intersection(*(set(u) for u in series.values())))
    M = np.array([[series[nm][d] for d in cal] for nm in BOOK])
    print(f'\n{"="*78}\nARE THEY STUCK AT THE SAME TIME?  ({len(cal)} common sessions)\n')
    cnt = M.sum(axis=0)
    print(f'  number of the nine at least 10% below their own running peak:')
    for k in range(0, 10):
        s = int((cnt == k).sum())
        if s:
            print(f'    {k} names{"":3s}{s:>5d} sessions{s/len(cal)*100:>7.0f}%'
                  f'  {"#"*int(s/len(cal)*60)}')
    ps = [float(np.corrcoef(M[i], M[j])[0, 1])
          for i in range(len(BOOK)) for j in range(i+1, len(BOOK))
          if M[i].std() > 0 and M[j].std() > 0]
    print(f'\n  mean pairwise correlation of the "10% under water" state: '
          f'{sum(ps)/len(ps):+.2f}')
    print(f'  (book RETURN correlation, for comparison, is 0.30 — §3.54)')
    print(f'  share of sessions with 5 or more of the nine under water: '
          f'{float((cnt >= 5).mean())*100:.0f}%')
    return dict(mean_pairwise_underwater=sum(ps)/len(ps),
                dist={int(k): int((cnt == k).sum()) for k in range(10)},
                sessions=len(cal))
