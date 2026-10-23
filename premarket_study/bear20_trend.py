"""
bear20_trend.py — E with a trend filter on the borrower (§3.94): a bench name
may receive the held-back core cash only while its own prior close is above its
own N-day average. Motivated by 2022, where E lent to names falling with the
market (§3.94) — so this rule was chosen AFTER seeing both episodes.
Rebound names: either kept on the deep-drop rule only (they are below trend by
construction), or dropped from the bench.
"""
import functools
import json

import bear12_breadth as bb
from bear_replay import dma_gate_dates
from bear_stop import CAP
from book12 import pm_rule_for
from book20 import TWELVE, BENCH, REBOUND, DIVERS, X, N as HOLD, EPS
from book_sim import load_all, simulate
from fresh_opt import SPLIT
from fresh_opt_cands import daily_from_5min
from lowdd_book import params
from managed20 import admitted
from parallel_book import gate_sets
from recap_9v12 import mdd
from bear20_gates import gates, breach_full


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
    daily = {n: daily_from_5min(n) for n in BENCH}

    def below24(n, w):
        dts, _, _, _, C = daily[n]
        return breach_full(dts, C, w)

    def below22(n, w):
        return dma_gate_dates(bd[n]['dts'], bd[n]['C'], n=w, min_n=min(w, 100))

    arms = [('§3.93: all eight, no filter', BENCH, None, True),
            ('divers. only, no filter', DIVERS, None, False)]
    for w in (200, 100, 50):
        arms += [(f'all eight, divers. need >{w}dma', BENCH, w, True),
                 (f'divers. only, need >{w}dma', DIVERS, w, False)]
    print(f'  {"arm":34s}| 24-26 full  test maxDD | 2022  to Jun23 maxDD')
    print(f'  {"live twelve, no gate":34s}|  71.3   94.3  20.5 | -13.8%   2.3%  23.7%   (bear20_gates)')
    print(f'  {"K>=6 hold cash, no bench":34s}|  65.9   94.3  15.1 | -11.2%   4.7%  15.1%   (bear20_gates)')
    for lab, bench, w, reb in arms:
        res = {}
        for per, D, S, C_, G, kw, below in (
                ('24', d, s_all, cal, g24, dict(excl_fn=excl), below24),
                ('22', bd, bs, bcal, g22, dict(date_lo=bb.Y0, date_hi=bb.END), below22)):
            nb = {n: set(G[n]) for n in TWELVE}
            for n in bench:
                if n in REBOUND:
                    nb[n] = set(C_) - admitted(D[n], X, HOLD, None)
                elif w:
                    nb[n] = set(below(n, w))
            sl = [x for x in S if x['name'] in TWELVE + bench]
            r = simulate(D, sl, C_, capital=CAP, mode='pooled', collect_trades=True, no_buy=nb,
                         gate_cash=True, tier2=set(bench), **kw)
            eq, c = r['equity'], r['cal']
            if per == '24':
                res[per] = dict(full=r['full'], test=r['test'], maxdd=r['maxdd'], test_dd=mdd(eq[k:]))
            else:
                i22 = max(i for i, x in enumerate(c) if x <= bb.Y1)
                res[per] = dict(y2022=eq[i22] / eq[0] - 1, to_jun23=eq[-1] / eq[0] - 1, maxdd=r['maxdd'])
        out[lab] = res
        a, b = res['24'], res['22']
        print(f'  {lab:34s}| {a["full"]*100:5.1f} {a["test"]*100:6.1f} {a["maxdd"]*100:5.1f} | '
              f'{b["y2022"]*100:5.1f}% {b["to_jun23"]*100:6.1f}% {b["maxdd"]*100:5.1f}%', flush=True)
    json.dump(out, open('bear20_trend.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
