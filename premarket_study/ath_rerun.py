"""
ath_rerun.py — the §3.84/§3.85 tables re-run with the ATH gate ON, as the live
workbook has it (Active Trading M7 = 0: every buy also capped at
ATH*(1-0) - prevclose*premium, so no order creates a trade whose exit needs a
print above the all-time high). §3.83-3.85 ran with the gate OFF: load_all and
bear12_breadth.build only apply it when engine kwargs pass ath_target_guard.

2024-26: nine, twelve, +BRKB, each with the PM rule. Bear: nine and eleven.
"""
import collections
import functools
import json

import bear12_breadth as bb
from bear_replay import dma_gate_dates
from bear_stop import CAP
from fresh_opt import SPLIT
from lowdd_book import TWELVE, ROSTER, params
from book12 import pm_rule_for
from book_sim import load_all, simulate
from parallel_book import gate_sets
from recap_9v12 import mdd, arms, show

NINE = list(ROSTER)
ELEVEN = [n for n in TWELVE if n != 'NVDA']
EPS = 0.0


def main():
    out = {}
    for ath in (False, True):
        a = 'ATH on ' if ath else 'ATH off'
        for book, names, Ks in (('nine', NINE, (5,)), ('twelve', TWELVE, (6,)),
                                ('+BRKB', TWELVE + ['BRKB'], (6,))):
            po, _ = params(names)
            ek = {n: dict(ath_target_guard=EPS) for n in names} if ath else None
            d, s, cal = load_all(engine_kwargs_per_name=ek, names=names, params_override=po)
            excl = pm_rule_for(d, set(names))
            k = max(i for i, x in enumerate(cal) if x <= SPLIT)
            yrs = len(cal) / 252
            gk = {K: gate_sets(names, K)[0] for K in Ks}
            for tag, kw in arms(gk, gate_sets(names, 1)[0]):
                r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True,
                             excl_fn=excl, **kw)
                row = dict(full=r['full'], test=r['test'], maxdd=r['maxdd'],
                           test_dd=mdd(r['equity'][k:]), fills_yr=r['fills'] / yrs)
                out[f'2024-26 | {a} | {book} | {tag}'] = row
                show(f'2024-26 {a} {book:7s}{tag:20s}', row)

    orig = bb.run_model
    for ath in (False, True):
        a = 'ATH on ' if ath else 'ATH off'
        bb.run_model = functools.partial(orig, ath_target_guard=EPS) if ath else orig
        for book, names, Ks in (('nine', NINE, (5,)), ('eleven', ELEVEN, (6,))):
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
                out[f'bear | {a} | {book} | {tag}'] = row
                show(f'bear    {a} {book:7s}{tag:20s}', row)
    bb.run_model = orig
    json.dump(out, open('ath_rerun.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
