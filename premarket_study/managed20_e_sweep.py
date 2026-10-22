"""
managed20_e_sweep.py — the deep-drop threshold X (and hold N) for the rebound
names in breadth K>=6 + E (§3.90 used X40 N60 untested under E). Diversifiers
always eligible. X=None means the rebound names are always eligible too.
Also run without APLD/AAOI, the two hindsight names.
"""
import json

from fresh_opt import SPLIT
from lowdd_book import TWELVE, params
from book12 import pm_rule_for
from book_sim import load_all, simulate
from bear_stop import CAP
from parallel_book import gate_sets
from recap_9v12 import mdd
from managed20 import BENCH, REBOUND, TWENTY, EPS, admitted


def main():
    out = {}
    po, _ = params(TWENTY)
    ek = {n: dict(ath_target_guard=EPS) for n in TWENTY}
    d, s_all, cal = load_all(engine_kwargs_per_name=ek, names=TWENTY, params_override=po)
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    excl = pm_rule_for(d, set(TWENTY))
    yrs = len(cal) / 252
    g6 = gate_sets(TWELVE, 6)[0]
    print(f'  {"arm":30s}{"full":>6s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"tstDD":>7s}'
          f'{"fills":>6s}{"bench$":>9s}  rebound-name P&L $k')
    for lab, bench in (('', BENCH), ('no APLD/AAOI ', [b for b in BENCH if b not in ('APLD', 'AAOI')])):
        reb = [n for n in REBOUND if n in bench]
        for X in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, None):
            for N in ((40, 60, 120) if X is not None else (0,)):
                nb = {n: set(g6[n]) for n in TWELVE}
                if X is not None:
                    nb.update({n: set(cal) - admitted(d[n], X, N, None) for n in reb})
                sl = [x for x in s_all if x['name'] in TWELVE + bench]
                r = simulate(d, sl, cal, capital=CAP, mode='pooled', collect_trades=True,
                             excl_fn=excl, no_buy=nb, gate_cash=True, tier2=set(bench))
                tr = r['trades']
                bp = {n: sum(t['pnl'] for t in tr if t['name'] == n) for n in bench}
                tag = lab + (f'X{int(X*100)} N{N}' if X is not None else 'rebound always eligible')
                row = dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'],
                           test_dd=mdd(r['equity'][k:]), fills_yr=r['fills'] / yrs, bench_pnl=bp)
                out[tag] = row
                print(f'  {tag:30s}{row["full"]*100:>6.1f}{row["train"]*100:>7.1f}{row["test"]*100:>7.1f}'
                      f'{row["maxdd"]*100:>7.1f}{row["test_dd"]*100:>7.1f}{row["fills_yr"]:>6.0f}'
                      f'{sum(bp.values())/1e3:>+8.0f}k  '
                      + ' '.join(f'{n} {bp[n]/1e3:+.0f}' for n in reb), flush=True)
        print()
    json.dump(out, open('managed20_e_sweep.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
