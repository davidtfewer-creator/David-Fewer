"""
cap17.py — a per-name exposure cap (user, 23 Oct 2026: VRT is 27% of the live
book and 41% of the loss; "maybe this could be another way to bring in the
bench, i.e. free cash driven by caps"). book_sim exp_cap / exp_to.

  A  the live twelve + cap, freed cash held or redistributed to the core
  B  the chosen book (§3.95: 200dma K>=6 + E to NEM LEN DLTR RKT TEAM) + cap,
     freed cash to the bench (new funding route), the core, or held
Both periods; 2022 = Jan 2022 - Jun 2023 with NVDA in the twelve.
"""
import functools
import json

import bear12_breadth as bb
from bear_replay import dma_gate_dates
from bear_stop import CAP
from book12 import pm_rule_for
from book20 import TWELVE, DIVERS, EPS
from book_sim import load_all, simulate
from fresh_opt import SPLIT
from lowdd_book import params
from parallel_book import gate_sets
from recap_9v12 import mdd
from bear20_gates import gates

CAPS = (0.10, 0.125, 0.15, 0.20)


def main():
    out = {}
    names = TWELVE + DIVERS
    po, _ = params(names)
    ek = {n: dict(ath_target_guard=EPS) for n in names}
    d, s_all, cal = load_all(engine_kwargs_per_name=ek, names=names, params_override=po)
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    excl = pm_rule_for(d, set(names))
    orig = bb.run_model
    bb.run_model = functools.partial(orig, ath_target_guard=EPS)
    bb.NAMES = names
    bd, bs, bcal = bb.build()
    bb.run_model = orig
    G = {'24': gate_sets(TWELVE, 6)[0],
         '22': gates({n: dma_gate_dates(bd[n]['dts'], bd[n]['C']) for n in TWELVE}, 6)}
    P = {'24': (d, s_all, cal, dict(excl_fn=excl)),
         '22': (bd, bs, bcal, dict(date_lo=bb.Y0, date_hi=bb.END))}

    arms = [('A twelve, no cap', False, None, 'cash')]
    arms += [(f'A twelve, cap {c*100:g}% -> {to}', False, c, to) for c in CAPS for to in ('cash', 'core')]
    arms += [('B chosen, no cap', True, None, 'cash')]
    arms += [(f'B chosen, cap {c*100:g}% -> {to}', True, c, to) for c in CAPS
             for to in ('bench', 'core', 'cash')]
    print(f'  {"arm":30s}| 24-26 full  test maxDD tstDD fills  peak name   | 2022  to Jun23 maxDD  peak name')
    for tag, chosen, c, to in arms:
        res = {}
        for per in ('24', '22'):
            D, S, C_, kw = P[per]
            ex = dict(exp_cap=c, exp_to=to)
            nb = None
            if chosen:
                nb = {n: set(G[per][n]) for n in TWELVE}
                ex.update(gate_cash=True, tier2=set(DIVERS))
                sl = S
            else:
                sl = [x for x in S if x['name'] in TWELVE]
            r = simulate(D, sl, C_, capital=CAP, mode='pooled', collect_trades=True,
                         no_buy=nb, **ex, **kw)
            assert min(r['cash']) > -1e-6, tag
            eq, cc = r['equity'], r['cal']
            pk = max(r['exp_max'].items(), key=lambda kv: kv[1])
            bp = sum(t['pnl'] for t in r['trades'] if t['name'] in DIVERS)
            if per == '24':
                res[per] = dict(full=r['full'], test=r['test'], maxdd=r['maxdd'], test_dd=mdd(eq[k:]),
                                fills_yr=r['fills'] / (len(cc) / 252), peak=pk, bench_pnl=bp,
                                freed=r['exp_freed'])
            else:
                i22 = max(i for i, x in enumerate(cc) if x <= bb.Y1)
                res[per] = dict(y2022=eq[i22] / eq[0] - 1, to_jun23=eq[-1] / eq[0] - 1,
                                maxdd=r['maxdd'], peak=pk, bench_pnl=bp)
        out[tag] = res
        a, b = res['24'], res['22']
        print(f'  {tag:30s}| {a["full"]*100:5.1f} {a["test"]*100:6.1f} {a["maxdd"]*100:5.1f} {a["test_dd"]*100:5.1f}'
              f' {a["fills_yr"]:4.0f}  {a["peak"][0]:4s} {a["peak"][1]*100:4.0f}% | {b["y2022"]*100:5.1f}%'
              f' {b["to_jun23"]*100:6.1f}% {b["maxdd"]*100:5.1f}%  {b["peak"][0]:4s} {b["peak"][1]*100:4.0f}%',
              flush=True)
    json.dump(out, open('cap17.json', 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
