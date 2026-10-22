"""
recap_9v12.py — one table: the nine vs the twelve, each with no gate, the breadth
gate (two K values, scaled to book size) and the per-name gate, each either
redistributing the gated share or holding it in cash. 2024-26 (with the PM rule)
and the 2022 bear (Jan 2022 - Jun 2023, no PM rule, no NVDA data, so the
'twelve' there is eleven).
"""
import collections
import json

import bear12_breadth as bb
from bear_replay import dma_gate_dates
from bear_stop import CAP
from fresh_opt import SPLIT
from lowdd_book import TWELVE, ROSTER, params
from book12 import pm_rule_for
from book_sim import load_all, simulate
from parallel_book import gate_sets

NINE = list(ROSTER)
ELEVEN = [n for n in TWELVE if n != 'NVDA']


def mdd(eq):
    pk, m = eq[0], 0.0
    for v in eq:
        pk = max(pk, v); m = max(m, (pk - v) / pk)
    return m


def arms(gate_k, gate_1):
    a = [('no gate', {})]
    for K, g in gate_k.items():
        a += [(f'breadth K>={K}', {'no_buy': g}),
              (f'breadth K>={K} cash', {'no_buy': g, 'gate_cash': True})]
    a += [('per-name', {'no_buy': gate_1}), ('per-name cash', {'no_buy': gate_1, 'gate_cash': True})]
    return a


def show(tag, row):
    print(tag + ' '.join(f'{(v if k == "fills_yr" else v * 100):7.1f}' for k, v in row.items()),
          flush=True)


def main():
    out = {}
    for book, names, Ks in (('nine', NINE, (4, 5)), ('twelve', TWELVE, (5, 6))):
        po, _ = params(names)
        d, s, cal = load_all(names=names, params_override=po)
        excl = pm_rule_for(d, set(names))
        k = max(i for i, x in enumerate(cal) if x <= SPLIT)
        yrs = len(cal) / 252
        gk = {K: gate_sets(names, K)[0] for K in Ks}
        for tag, kw in arms(gk, gate_sets(names, 1)[0]):
            r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True,
                         excl_fn=excl, **kw)
            row = dict(full=r['full'], test=r['test'], maxdd=r['maxdd'],
                       test_dd=mdd(r['equity'][k:]), fills_yr=r['fills'] / yrs)
            out[f'2024-26 | {book} | {tag}'] = row
            show(f'2024-26 {book:7s}{tag:22s}', row)

    for book, names, Ks in (('nine', NINE, (4, 5)), ('eleven', ELEVEN, (5, 6))):
        bb.NAMES = names
        data, sleeves, bcal = bb.build()
        breach = {x: dma_gate_dates(data[x]['dts'], data[x]['C']) for x in names}
        cnt = collections.Counter(dd for x in names for dd in breach[x])
        gk = {K: {x: {dd for dd in breach[x] if cnt[dd] >= K} for x in names} for K in Ks}
        for tag, kw in arms(gk, breach):
            r = simulate(data, sleeves, bcal, capital=CAP, collect_trades=True,
                         date_lo=bb.Y0, date_hi=bb.END, **kw)
            c, eq = r['cal'], r['equity']
            i22 = max(i for i, x in enumerate(c) if x <= bb.Y1)
            row = dict(y2022=eq[i22] / eq[0] - 1, to_jun23=eq[-1] / eq[0] - 1,
                       maxdd=r['maxdd'], fills_yr=r['fills'] / (len(c) / 252))
            out[f'bear | {book} | {tag}'] = row
            show(f'bear    {book:7s}{tag:22s}', row)
    json.dump(out, open('recap_9v12.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
