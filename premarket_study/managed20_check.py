"""
managed20_check.py — robustness of the managed20 D+A result (§3.88):
  1. the intraday-ordering assumption: bench fills processed LAST (default) vs
     FIRST (pessimistic for the core), and how many fills were squeezed;
  2. leave-one-out over the eight bench names (does it hang on APLD/AAOI?);
  3. bench P&L by name.
Central configs: D+A all bench X40 N60, and D+A rebound-only X40 N60
(diversifiers always on as tier 2).
"""
import collections
import json

from fresh_opt import SPLIT
from lowdd_book import TWELVE, params
from book12 import pm_rule_for
from book_sim import load_all, simulate
from bear_stop import CAP
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

    def go(tag, bench, gated, first=False):
        names = TWELVE + bench
        sl = [x for x in s_all if x['name'] in names]
        nb = {n: set(cal) - admitted(d[n], 0.40, 60, None) for n in gated if n in bench}
        r = simulate(d, sl, cal, capital=CAP, mode='pooled', collect_trades=True, excl_fn=excl,
                     no_buy=nb, tier2=set(bench), tier2_first=first)
        pn = collections.defaultdict(float)
        for t in r['trades']:
            pn[t['name']] += t['pnl']
        row = dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'],
                   test_dd=mdd(r['equity'][k:]), fills_yr=r['fills'] / yrs,
                   t2_cut=r['t2_cut'], t2_skip=r['t2_skip'],
                   bench_pnl={n: pn[n] for n in bench}, total_pnl=sum(pn.values()))
        out[tag] = row
        print(f'  {tag:40s}{row["full"]*100:>6.1f}{row["train"]*100:>7.1f}{row["test"]*100:>7.1f}'
              f'{row["maxdd"]*100:>7.1f}{row["test_dd"]*100:>7.1f}{row["fills_yr"]:>6.0f}'
              f'   squeezed {r["t2_cut"]:>3d} skipped {r["t2_skip"]:>3d}', flush=True)
        return row

    print(f'  {"arm":40s}{"full":>6s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"tstDD":>7s}{"fills":>6s}')
    for lab, gated in (('all-gated', BENCH), ('rebound-gated', REBOUND)):
        base = go(f'{lab}: core first (default)', BENCH, gated)
        go(f'{lab}: BENCH FIRST (pessimistic)', BENCH, gated, first=True)
        for n in BENCH:
            go(f'{lab}: without {n}', [b for b in BENCH if b != n], gated)
        print('    bench P&L ($k, 2024-26): ' + ', '.join(
            f'{n} {v/1e3:+.0f}' for n, v in sorted(base['bench_pnl'].items(), key=lambda kv: -kv[1]))
            + f'  | book total {base["total_pnl"]/1e3:+.0f}\n')
    json.dump(out, open('managed20_check.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
