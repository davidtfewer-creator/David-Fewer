"""
Pre-market breadth diagnostic (user, 26 Aug 2026): is a BOOK-WIDE adverse
pre-market morning (many names' 09:00 prints down vs yesterday's close) a
reason to veto the day's entries beyond the per-name 4% rule?

VERDICT: premise dead at the diagnostic — no intervention warranted. Completed
trades that survive the per-name PM rule get BETTER, monotonically, as the
morning's breadth worsens (>=2%-down breadth 6-9: avg +2.46%, 1% stops, the
best bucket in the table; >=3% breadth 3-9: +2.31%, 1 stop in 186). A
coordinated gap-down that still leaves a bid within 4% of the tape is a
book-wide panic that mean-reverts — the harvest, not the hazard. The weakest
bucket is 1-2 names down >=3% (+1.10%): the idiosyncratic single-name
adverse-information case, which is exactly what the per-name rule already
vetoes. Breadth adds nothing the 4% depth check hasn't priced.

Run: python pm_breadth_diag.py   (prints the distribution + bucket tables;
baseline invariance asserted against the recorded PM-rule references.)
"""
import json
import pickle

import numpy as np

from book_sim import NAMES as N8, load_all, simulate
from engine import Params
from fresh_opt_cands import aw_params


def main():
    t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                bayes_pct=0.5, years=2.2, ou_W=80)
    mrvl = aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    names = N8 + ['MRVL']
    data, sleeves, cal = load_all(names=names, params_override={'MRVL': mrvl})
    pm = pickle.load(open('data_pm/pm_last_cuts.pkl', 'rb'))['09:00']

    def pm_rule(name, i, bid):
        pml = pm[name].get(data[name]['dts'][i])
        return pml is not None and bid < pml * (1 - 0.04)

    moves = {}
    for d in cal:
        row = []
        for s in names:
            nd = data[s]
            i = nd['idx'][d]
            p_ = pm[s].get(d)
            if i > 0 and p_ is not None:
                row.append(p_ / nd['C'][i - 1] - 1)
        moves[d] = row
    cov = {d: len(moves[d]) for d in cal}

    for x in (0.01, 0.02, 0.03):
        br = {d: sum(1 for m in moves[d] if m <= -x) for d in cal}
        dist = {}
        for d in cal:
            if cov[d] >= 6:
                dist[br[d]] = dist.get(br[d], 0) + 1
        print(f'breadth at down >= {x:.0%}: ' +
              ', '.join(f'{k}:{dist[k]}' for k in sorted(dist)))

    r = simulate(data, sleeves, cal, mode='pooled', excl_fn=pm_rule,
                 collect_trades=True)
    assert abs(r['test'] - 1.184) < 0.01

    for x, buckets in ((0.02, [(0, 0), (1, 1), (2, 3), (4, 5), (6, 9)]),
                       (0.03, [(0, 0), (1, 2), (3, 9)])):
        br = {d: sum(1 for m in moves[d] if m <= -x) for d in cal}
        print(f'\ncompleted trades by adverse-morning breadth (down >= {x:.0%}, coverage >= 6):')
        for lo, hi in buckets:
            rs, st = [], 0
            for t in r['trades']:
                d = t['entry']
                if cov.get(d, 0) < 6 or not (lo <= br.get(d, 0) <= hi):
                    continue
                rs.append(t['pnl'] / t['cost'])
                st += t['stopped']
            a = np.array(rs) if rs else np.array([np.nan])
            print(f'  {lo}-{hi}: trades {len(rs):4d}  avg {np.nanmean(a)*100:+.2f}%  '
                  f'med {np.nanmedian(a)*100:+.2f}%  stops {st}')


if __name__ == '__main__':
    main()
