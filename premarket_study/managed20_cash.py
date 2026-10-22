"""
managed20_cash.py — the managed book in a CASH account (user, 22 Oct 2026: IBKR
will not accept orders that cash does not cover, so §3.88's overbooking is out).
book_sim tier2_cash: the bench is funded from the core's orders, only on
mornings when an admitted bench name is bidding; orders sum to cash.
  slice b   up to b of the morning cash to the bench
  cap c     core orders above c x equity are cut; the excess funds the bench
Configs: rebound names deep-drop admitted (X40 N60), diversifiers always on --
§3.88's best -- and all bench gated; plus the bench without APLD/AAOI.
"""
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

    def go(tag, bench, gated, tc, overbook=False):
        names = TWELVE + bench
        sl = [x for x in s_all if x['name'] in names]
        nb = {n: set(cal) - admitted(d[n], 0.40, 60, None) for n in gated if n in bench}
        kw = dict(tier2=set(bench), tier2_cash=tc) if bench else {}
        r = simulate(d, sl, cal, capital=CAP, mode='pooled', collect_trades=True,
                     excl_fn=excl, no_buy=nb, **kw)
        assert min(r['cash']) > -1e-6, (tag, min(r['cash']))
        bp = sum(t['pnl'] for t in r['trades'] if t['name'] in bench)
        ap = sum(t['pnl'] for t in r['trades'])
        row = dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'],
                   test_dd=mdd(r['equity'][k:]), fills_yr=r['fills'] / yrs,
                   bench_share=bp / ap, squeezed=r['t2_cut'] + r['t2_skip'])
        out[tag] = row
        print(f'  {tag:44s}{row["full"]*100:>6.1f}{row["train"]*100:>7.1f}{row["test"]*100:>7.1f}'
              f'{row["maxdd"]*100:>7.1f}{row["test_dd"]*100:>7.1f}{row["fills_yr"]:>6.0f}'
              f'{row["bench_share"]*100:>6.0f}%{row["squeezed"]:>5d}', flush=True)

    print(f'  {"arm":44s}{"full":>6s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"tstDD":>7s}'
          f'{"fills":>6s}{"bnch$":>7s}{"sqz":>5s}')
    go('twelve (live)', [], [], None)
    noaa = [b for b in BENCH if b not in ('APLD', 'AAOI')]
    for lab, bench, gated in (('rebound-gated', BENCH, REBOUND), ('all-gated', BENCH, BENCH),
                              ('rebound-gated, no APLD/AAOI', noaa, REBOUND)):
        print(f'  -- {lab}')
        go(f'{lab}: overbook (§3.88)', bench, gated, None)
        for b in (0.10, 0.20, 0.30):
            go(f'{lab}: slice {int(b*100)}%', bench, gated, ('slice', b))
        for c in (0.05, 0.075, 0.10, 0.15):
            go(f'{lab}: core cap {c*100:g}% of equity', bench, gated, ('cap', c))
    json.dump(out, open('managed20_cash.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
