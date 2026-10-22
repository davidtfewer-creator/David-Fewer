"""
gate_cash_test.py — does the gate work better if blocked names' capital is held
in CASH instead of being handed to the names still bidding?

bear12_breadth.py found the breadth gate's 2022 benefit is eroded by
concentration: with most of the book gated, the morning pot splits over the few
names still above trend, so those orders grow -- and in 2022 they were often
brief rallies that failed (GM, VRT, AVGO all lost MORE with the gate on).
gate_cash=True keeps a gated sleeve in the allocation denominator so its share
stays in cash. Tested in BOTH regimes, because a fix that only helps the bear is
not a fix.
"""
import collections
import datetime as dt
import json

from bear12_breadth import build, Y0, Y1, END
from bear_replay import dma_gate_dates
from bear_stop import NAMES as N11, CAP
from fresh_opt import SPLIT
from lowdd_book import TWELVE, params
from book12 import pm_rule_for
from book_sim import load_all, simulate
from parallel_book import gate_sets
import book_sim


def mdd(eq):
    pk, m = eq[0], 0.0
    for v in eq:
        pk = max(pk, v); m = max(m, (pk - v) / pk)
    return m


def main():
    out = {}
    # ---------------- regression: defaults unchanged
    po, _ = params(TWELVE)
    d, s, cal = load_all(names=TWELVE, params_override=po)
    excl = pm_rule_for(d, set(TWELVE))
    r0 = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True, excl_fn=excl)
    assert abs(r0['full'] - 0.720) < 0.002 and abs(r0['maxdd'] - 0.209) < 0.002, r0['full']
    print(f'regression: twelve 2024-26 default {r0["full"]*100:.1f}% / {r0["maxdd"]*100:.1f}% DD '
          f'(matches §3.70)\n')

    # ---------------- 2024-26, twelve with NVDA
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    g6, _ = gate_sets(TWELVE, 6)
    g1, _ = gate_sets(TWELVE, 1)
    print('===== 2024-26, the twelve (with NVDA) =====')
    print(f'  {"arm":40s}{"full":>7s}{"test":>7s}{"maxDD":>7s}{"testDD":>8s}{"fills":>7s}')
    for tag, kw in (('no gate (current)', {}),
                    ('breadth K>=6, redistribute', {'no_buy': g6}),
                    ('breadth K>=6, HOLD CASH', {'no_buy': g6, 'gate_cash': True}),
                    ('per-name gate, redistribute', {'no_buy': g1}),
                    ('per-name gate, HOLD CASH', {'no_buy': g1, 'gate_cash': True})):
        r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True, excl_fn=excl, **kw)
        te = mdd(r['equity'][k:])
        print(f'  {tag:40s}{r["full"]*100:>7.1f}{r["test"]*100:>7.1f}{r["maxdd"]*100:>7.1f}'
              f'{te*100:>8.1f}{r["fills"]/(len(cal)/252):>7.0f}', flush=True)
        out[f'2024-26 | {tag}'] = dict(full=r['full'], test=r['test'], maxdd=r['maxdd'], test_dd=te)

    # ---------------- 2022 bear, the eleven
    data, sleeves, bcal = build()
    breach = {x: dma_gate_dates(data[x]['dts'], data[x]['C']) for x in N11}
    cnt = collections.Counter(dd for x in N11 for dd in breach[x])
    gk = {K: {x: {dd for dd in breach[x] if cnt[dd] >= K} for x in N11} for K in (5, 6)}
    print('\n===== 2022 bear, the twelve minus NVDA =====')
    print(f'  {"arm":40s}{"2022":>8s}{"to Jun23":>10s}{"maxDD":>8s}{"fills":>7s}')
    for tag, kw in (('no gate', {}),
                    ('breadth K>=5, redistribute', {'no_buy': gk[5]}),
                    ('breadth K>=5, HOLD CASH', {'no_buy': gk[5], 'gate_cash': True}),
                    ('breadth K>=6, redistribute', {'no_buy': gk[6]}),
                    ('breadth K>=6, HOLD CASH', {'no_buy': gk[6], 'gate_cash': True}),
                    ('per-name gate, redistribute', {'no_buy': breach}),
                    ('per-name gate, HOLD CASH', {'no_buy': breach, 'gate_cash': True})):
        r = book_sim.simulate(data, sleeves, bcal, capital=CAP, collect_trades=True,
                              date_lo=Y0, date_hi=END, **kw)
        c, eq = r['cal'], r['equity']
        i22 = max(i for i, x in enumerate(c) if x <= Y1)
        print(f'  {tag:40s}{(eq[i22]/eq[0]-1)*100:>7.1f}%{(eq[-1]/eq[0]-1)*100:>9.1f}%'
              f'{r["maxdd"]*100:>7.1f}%{r["fills"]:>7d}', flush=True)
        out[f'2022 | {tag}'] = dict(y2022=eq[i22]/eq[0]-1, to_jun23=eq[-1]/eq[0]-1,
                                    maxdd=r['maxdd'], fills=r['fills'])
    json.dump(out, open('gate_cash_test.json', 'w'), indent=1)
    print('\nwrote gate_cash_test.json')


if __name__ == '__main__':
    main()
