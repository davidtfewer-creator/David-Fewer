"""What does the PER-NAME 200dma gate (the version that worked in the 2022 bear,
bear_stop.py) cost in the 2024-26 sample? gate_sets(names, 1) = suppress a name
while it is below its own 200dma, no breadth condition. Twelve-name book."""
import json
from fresh_opt import SPLIT
from lowdd_book import TWELVE, params, CAP
from book12 import pm_rule_for
from book_sim import load_all, simulate
from parallel_book import gate_sets


def mdd(eq):
    pk, m = eq[0], 0.0
    for v in eq:
        pk = max(pk, v); m = max(m, (pk - v) / pk)
    return m


po, _ = params(TWELVE)
d, s, cal = load_all(names=TWELVE, params_override=po)
excl = pm_rule_for(d, set(TWELVE))
k = max(i for i, x in enumerate(cal) if x <= SPLIT)
g1, _ = gate_sets(TWELVE, 1)
fired = sorted({x for v in g1.values() for x in v})
print(f'per-name 200dma gate: {len(fired)} gated dates, '
      f'{sum(1 for x in fired if x > SPLIT)} of them in the TEST half\n')
print(f'  {"arm":30s}{"full":>7s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"testDD":>8s}{"fills":>7s}')
out = {}
for tag, kw in (('50d, no gate (current)', {}), ('50d + per-name 200dma gate', {'no_buy': g1}),
                ('20d + per-name 200dma gate', {'no_buy': g1, 'stop_days': 20})):
    r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True, excl_fn=excl, **kw)
    te = mdd(r['equity'][k:])
    print(f'  {tag:30s}{r["full"]*100:>7.1f}{r["train"]*100:>7.1f}{r["test"]*100:>7.1f}'
          f'{r["maxdd"]*100:>7.1f}{te*100:>8.1f}{r["fills"]/(len(cal)/252):>7.0f}')
    out[tag] = dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'], test_dd=te)
json.dump(out, open('gate_normal_cost.json', 'w'), indent=1)
