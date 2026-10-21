"""Split max drawdown by half for the leading low-DD arms: is the improvement
only the in-sample Feb-Apr 2025 episode (§3.72), or does it hold out of sample?"""
import json
from fresh_opt import SPLIT
from lowdd_book import TWELVE, params, CAP
from book12 import pm_rule_for
from book_sim import load_all, simulate

ARMS = {'TWELVE (current)': TWELVE,
        '+ NEM + LEN': TWELVE + ['NEM', 'LEN'],
        '- VRT - MRVL + NEM + LEN': [n for n in TWELVE if n not in ('VRT', 'MRVL')] + ['NEM', 'LEN'],
        '- VRT - MRVL + NEM + LEN + NOC': [n for n in TWELVE if n not in ('VRT', 'MRVL')] + ['NEM', 'LEN', 'NOC']}


def mdd(eq):
    pk, m = eq[0], 0.0
    for v in eq:
        pk = max(pk, v); m = max(m, (pk - v) / pk)
    return m


po, _ = params(sorted({n for v in ARMS.values() for n in v}))
print(f'split {SPLIT}\n')
print(f'  {"arm":34s}{"maxDD all":>11s}{"train DD":>10s}{"TEST DD":>10s}{"test ret":>10s}')
out = {}
for tag, names in ARMS.items():
    d, s, cal = load_all(names=names, params_override=po)
    r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True,
                 excl_fn=pm_rule_for(d, set(names)))
    eq = r['equity']
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    tr, te = mdd(eq[:k + 1]), mdd(eq[k:])
    print(f'  {tag:34s}{r["maxdd"]*100:>10.1f}%{tr*100:>9.1f}%{te*100:>9.1f}%{r["test"]*100:>9.1f}%',
          flush=True)
    out[tag] = dict(maxdd=r['maxdd'], train_dd=tr, test_dd=te, test=r['test'])
json.dump(out, open('lowdd_halves.json', 'w'), indent=1)
