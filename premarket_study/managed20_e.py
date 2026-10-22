"""
managed20_e.py — OPTION E for the managed book (user, 22 Oct 2026): the cash a
gated core name holds back is lent to admitted bench names. Cash-account safe
(orders never exceed cash) and the core's orders are untouched on days with no
gate. book_sim tier2 + gate_cash.

Core gate: breadth K>=6 of the twelve (fires only in Feb-Apr 2025, all train
half) or the per-name 200dma gate (fires often, both halves). Bench admission
as §3.88: deep drop X40 N60 for the rebound names; diversifiers either always
eligible or also drop-admitted. The bench is NOT subject to the 200dma gate
(a deep-drop name is below its 200dma by construction).
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
    gates = {'breadth K>=6': gate_sets(TWELVE, 6)[0], 'per-name 200dma': gate_sets(TWELVE, 1)[0]}
    for g, gs in gates.items():
        on = [len([x for x in gs[n] if x in set(cal[k:])]) for n in TWELVE]
        print(f'  {g}: core name-days gated, test half: {sum(on)} ({sum(on)/(12*(len(cal)-k))*100:.0f}%)')

    def go(tag, bench, gated, core_gate):
        names = TWELVE + bench
        sl = [x for x in s_all if x['name'] in names]
        nb = {n: set(cal) - admitted(d[n], 0.40, 60, None) for n in gated if n in bench}
        kw = {}
        if core_gate:
            nb.update({n: set(gates[core_gate][n]) for n in TWELVE})
            kw['gate_cash'] = True
        if bench:
            kw['tier2'] = set(bench)
        r = simulate(d, sl, cal, capital=CAP, mode='pooled', collect_trades=True,
                     excl_fn=excl, no_buy=nb or None, **kw)
        assert min(r['cash']) > -1e-6, tag
        tr = r['trades']
        bp = sum(t['pnl'] for t in tr if t['name'] in bench)
        row = dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'],
                   test_dd=mdd(r['equity'][k:]), fills_yr=r['fills'] / yrs,
                   bench_fills_yr=sum(1 for t in tr if t['name'] in bench) / yrs,
                   bench_pnl=bp, bench_by_name={n: sum(t['pnl'] for t in tr if t['name'] == n)
                                                for n in bench})
        out[tag] = row
        print(f'  {tag:52s}{row["full"]*100:>6.1f}{row["train"]*100:>7.1f}{row["test"]*100:>7.1f}'
              f'{row["maxdd"]*100:>7.1f}{row["test_dd"]*100:>7.1f}{row["fills_yr"]:>6.0f}'
              f'{row["bench_fills_yr"]:>6.0f}{bp/1e3:>+8.0f}k', flush=True)

    print(f'\n  {"arm":52s}{"full":>6s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"tstDD":>7s}'
          f'{"fills":>6s}{"bench":>6s}{"bench$":>9s}')
    go('twelve, no gate (live)', [], [], None)
    noaa = [b for b in BENCH if b not in ('APLD', 'AAOI')]
    for g in gates:
        print(f'  -- core gate: {g}, gated share held in cash')
        go(f'{g}: twelve, cash held (no bench)', [], [], g)
        go(f'{g}: E, rebound drop-admitted, divers. always', BENCH, REBOUND, g)
        go(f'{g}: E, all bench drop-admitted', BENCH, BENCH, g)
        go(f'{g}: E, all bench always eligible', BENCH, [], g)
        go(f'{g}: E, rebound/divers., no APLD/AAOI', noaa, REBOUND, g)
        go(f'{g}: E, rebound/divers., no APLD/AAOI/RKLB',
           [b for b in noaa if b != 'RKLB'], [b for b in REBOUND if b != 'RKLB'], g)
    json.dump(out, open('managed20_e.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
