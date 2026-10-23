"""
bear20_bench.py — follow-up to bear20_gates (§3.94): E lost money in 2022.
Bench P&L by name for 200dma K>=6 + E in both periods, each bench stock's own
2022 move, and E restricted to subsets of the bench (diversifiers only; no
rebound names; each name alone).
"""
import collections
import functools
import json

import bear12_breadth as bb
from bear_replay import dma_gate_dates, _load
from bear_stop import CAP
from book12 import pm_rule_for
from book20 import TWELVE, BENCH, REBOUND, DIVERS, X, N as HOLD, EPS
from book_sim import load_all, simulate
from fresh_opt import SPLIT
from lowdd_book import params
from managed20 import admitted
from parallel_book import gate_sets
from recap_9v12 import mdd
from bear20_gates import gates


def main():
    out = {}
    names = TWELVE + BENCH
    po, _ = params(names)
    ek = {n: dict(ath_target_guard=EPS) for n in names}
    d, s_all, cal = load_all(engine_kwargs_per_name=ek, names=names, params_override=po)
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    excl = pm_rule_for(d, set(names))
    g24 = gate_sets(TWELVE, 6)[0]
    orig = bb.run_model
    bb.run_model = functools.partial(orig, ath_target_guard=EPS)
    bb.NAMES = names
    bd, bs, bcal = bb.build()
    bb.run_model = orig
    g22 = gates({n: dma_gate_dates(bd[n]['dts'], bd[n]['C']) for n in TWELVE}, 6)

    print('bench stocks, calendar 2022 price move:')
    for n in BENCH:
        (dts, O, H, L, C), _ = _load(n)
        i0 = max(i for i, x in enumerate(dts) if x < bb.Y0)
        i1 = max(i for i, x in enumerate(dts) if x <= bb.Y1)
        print(f'  {n:5s} {(C[i1]/C[i0]-1)*100:+6.1f}%')

    subsets = [('all eight (§3.93)', BENCH), ('diversifiers only', DIVERS),
               ('no TEAM/RKT', [b for b in BENCH if b not in ('TEAM', 'RKT')]),
               ('NEM LEN DLTR', ['NEM', 'LEN', 'DLTR'])] + [(f'{b} alone', [b]) for b in BENCH]
    print(f'\n  {"bench":20s}| 24-26 full  test maxDD | 2022   to Jun23 maxDD | bench $k 24-26 / 2022')
    for lab, bench in subsets:
        res = {}
        for per, D, S, C_, G, kw in (('24', d, s_all, cal, g24, dict(excl_fn=excl)),
                                     ('22', bd, bs, bcal, g22, dict(date_lo=bb.Y0, date_hi=bb.END))):
            nb = {n: set(G[n]) for n in TWELVE}
            nb.update({n: set(C_) - admitted(D[n], X, HOLD, None) for n in REBOUND if n in bench})
            sl = [x for x in S if x['name'] in TWELVE + bench]
            r = simulate(D, sl, C_, capital=CAP, mode='pooled', collect_trades=True, no_buy=nb,
                         gate_cash=True, tier2=set(bench), **kw)
            pn = collections.defaultdict(float)
            for t in r['trades']:
                pn[t['name']] += t['pnl']
            eq, c = r['equity'], r['cal']
            if per == '24':
                res[per] = dict(full=r['full'], test=r['test'], maxdd=r['maxdd'])
            else:
                i22 = max(i for i, x in enumerate(c) if x <= bb.Y1)
                res[per] = dict(y2022=eq[i22] / eq[0] - 1, to_jun23=eq[-1] / eq[0] - 1, maxdd=r['maxdd'])
            res[per]['bench_pnl'] = {n: pn[n] for n in bench}
        out[lab] = res
        a, b = res['24'], res['22']
        print(f'  {lab:20s}| {a["full"]*100:5.1f} {a["test"]*100:6.1f} {a["maxdd"]*100:5.1f} | '
              f'{b["y2022"]*100:5.1f}% {b["to_jun23"]*100:6.1f}% {b["maxdd"]*100:5.1f}% | '
              f'{sum(a["bench_pnl"].values())/1e3:+6.0f} / {sum(b["bench_pnl"].values())/1e3:+6.0f}', flush=True)
    print('\n  bench P&L by name, all eight ($k): 24-26 | 2022')
    for n in BENCH:
        print(f'    {n:5s} {out["all eight (§3.93)"]["24"]["bench_pnl"][n]/1e3:+6.0f} | '
              f'{out["all eight (§3.93)"]["22"]["bench_pnl"][n]/1e3:+6.0f}')
    json.dump(out, open('bear20_bench.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
