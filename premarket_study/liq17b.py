"""
liq17b.py — follow-up to liq17 (§3.100): name-specific liquidity caps (CF, or
CF + VLO) instead of a uniform one, and participation re-expressed for a book
HELD at $10m (each fill scaled by $10m / book equity on the entry day), since
the simulation compounds a $10m start to several times that.
"""
import json

import participation as P_
from book12 import pm_rule_for
from book20 import TWELVE, DIVERS, EPS
from book_sim import load_all, simulate
from fresh_opt import SPLIT
from lowdd_book import params
from parallel_book import gate_sets
from recap_9v12 import mdd
from liq17 import load_vol, CAPITAL, TIGHT


def main():
    out = {}
    names = TWELVE + DIVERS
    po, _ = params(names)
    ek = {n: dict(ath_target_guard=EPS) for n in names}
    d, s_all, cal = load_all(engine_kwargs_per_name=ek, names=names, params_override=po)
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    excl = pm_rule_for(d, set(names))
    bars, med = load_vol(names, 'data_5min')
    g = gate_sets(TWELVE, 6)[0]
    arms = [('none', {}), ('CF 3%', {'CF': 0.03}), ('CF 2%', {'CF': 0.02}), ('CF 1%', {'CF': 0.01}),
            ('CF 2%, VLO 3%', {'CF': 0.02, 'VLO': 0.03}), ('CF 1%, VLO 2%', {'CF': 0.01, 'VLO': 0.02})]
    print(f'  {"cap":14s}| full  test maxDD tstDD | held at $10m: p95 / %>5%  ' + ''.join(f'{n:>11s}' for n in TIGHT[:5]))
    for tag, L in arms:
        oc = {n: {dd: L[n] * v for dd, v in med[n].items()} for n in L} or None
        r = simulate(d, s_all, cal, capital=CAPITAL, mode='pooled', collect_trades=True, excl_fn=excl,
                     no_buy={n: set(g[n]) for n in TWELVE}, gate_cash=True, tier2=set(DIVERS),
                     exp_cap=0.25, exp_to='cash', order_cap=oc)
        pos = {x: i for i, x in enumerate(cal)}
        eq = r['equity']
        rows, _ = P_.measure(r['trades'], bars)
        part = {}
        for n in TIGHT[:5]:
            xs = sorted(x['p_blend'] * CAPITAL / eq[max(0, pos[x['entry']] - 1)]
                        for x in rows if x['name'] == n and x['p_blend'] is not None)
            part[n] = (xs[int(0.95 * (len(xs) - 1))], sum(1 for x in xs if x > 0.05) / len(xs))
        row = dict(full=r['full'], test=r['test'], maxdd=r['maxdd'], test_dd=mdd(eq[k:]), held10=part)
        out[tag] = row
        print(f'  {tag:14s}| {row["full"]*100:4.1f} {row["test"]*100:5.1f} {row["maxdd"]*100:5.1f} {row["test_dd"]*100:5.1f} |'
              + ' ' * 27 + ''.join(f'{p[0]*100:>6.1f}/{p[1]*100:>3.0f}%' for p in part.values()), flush=True)
    json.dump(out, open('liq17b.json', 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
