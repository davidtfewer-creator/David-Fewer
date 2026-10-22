"""
brkb_add.py — BRK.B as name 13 (user, 22 Oct 2026: "reported to be a good hedge
against AI chip stocks"). Ticker stored as BRKB. Fittability rho +0.06 (§fit_brkb.log),
so it runs on the neutral x0_vector(1) like any name under the 0.20 bar.
2024-26 only: there is no 2021-23 BRK.B file yet.
"""
import json

from fresh_opt import SPLIT
from lowdd_book import TWELVE, AI, params, WINDOWS
from book12 import pm_rule_for
from book_sim import load_all, simulate
from bear_stop import CAP
from parallel_book import gate_sets
from recap_9v12 import mdd

THIRTEEN = TWELVE + ['BRKB']


def main():
    out = {}
    for book, names, Ks in (('twelve', TWELVE, (6,)), ('+BRKB', THIRTEEN, (6, 7))):
        po, basis = params(names)
        if 'BRKB' in basis:
            print('BRKB basis:', basis['BRKB'])
        d, s, cal = load_all(names=names, params_override=po)
        excl = pm_rule_for(d, set(names))
        k = max(i for i, x in enumerate(cal) if x <= SPLIT)
        yrs = len(cal) / 252
        arms = [('no gate', {})] + [(f'K>={K} cash', {'no_buy': gate_sets(names, K)[0],
                                                     'gate_cash': True}) for K in Ks]
        for tag, kw in arms:
            r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True,
                         excl_fn=excl, **kw)
            tr = r['trades']
            eq = r['equity']
            st = []
            for _, lo, hi in WINDOWS:
                ix = [i for i, dd in enumerate(cal) if lo <= dd <= hi]
                st.append(eq[ix[-1]] / eq[ix[0]] - 1 if len(ix) > 1 else float('nan'))
            ai = sum(t['cost'] for t in tr if t['name'] in AI) / sum(t['cost'] for t in tr)
            b = [t for t in tr if t['name'] == 'BRKB']
            row = dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'],
                       test_dd=mdd(eq[k:]), fills_yr=r['fills'] / yrs, ai_share=ai,
                       stress=st, brkb_fills_yr=len(b) / yrs,
                       brkb_pnl=sum(t.get('pnl', 0) for t in b),
                       brkb_cost_share=sum(t['cost'] for t in b) / sum(t['cost'] for t in tr))
            out[f'{book} | {tag}'] = row
            print(f'{book:7s}{tag:12s} full {row["full"]*100:5.1f} train {row["train"]*100:5.1f} '
                  f'test {row["test"]*100:5.1f} maxDD {row["maxdd"]*100:4.1f} testDD '
                  f'{row["test_dd"]*100:4.1f} fills {row["fills_yr"]:4.0f} AI$ {ai*100:3.0f}% '
                  f'stress ' + ' / '.join(f'{x*100:+.1f}' for x in st)
                  + (f' | BRKB {row["brkb_fills_yr"]:.0f}/yr, ${row["brkb_pnl"]/1e3:+.0f}k, '
                     f'{row["brkb_cost_share"]*100:.1f}% of $' if b else ''), flush=True)
    json.dump(out, open('brkb_add.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
