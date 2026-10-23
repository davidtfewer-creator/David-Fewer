"""
bear17_fast.py — would a faster trigger suit the chosen book (§3.95, bench =
NEM LEN DLTR RKT TEAM)? (user, 23 Oct 2026, after the Oct 2026 AI sell-off left
only 3 of the nine below their 200dma but 7 below their 50dma.) Breadth gate on
the 200/100/50dma at K>=6 and K>=5, E to the diversifier bench, both periods.
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
from fresh_opt_cands import daily_from_5min
from lowdd_book import params
from recap_9v12 import mdd
from bear20_gates import gates, breach_full


def main():
    out = {}
    names = TWELVE + DIVERS
    po, _ = params(names)
    ek = {n: dict(ath_target_guard=EPS) for n in names}
    d, s_all, cal = load_all(engine_kwargs_per_name=ek, names=names, params_override=po)
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    excl = pm_rule_for(d, set(names))
    daily = {n: daily_from_5min(n) for n in TWELVE}
    orig = bb.run_model
    bb.run_model = functools.partial(orig, ath_target_guard=EPS)
    bb.NAMES = names
    bd, bs, bcal = bb.build()
    bb.run_model = orig
    print(f'  {"core gate (bench = 5 diversifiers)":34s}| 24-26 full  test maxDD tstDD gated | 2022  to Jun23 maxDD gated')
    arms = [('live twelve, no gate', None, None, False)]
    for w in (200, 100, 50):
        for K in (6, 5):
            arms += [(f'{w}dma K>={K} + E', w, K, True)]
    arms += [('50dma K>=6, hold cash, no bench', 50, 6, False),
             ('200dma K>=6, hold cash, no bench', 200, 6, False)]
    for tag, w, K, bench in arms:
        res = {}
        for per in ('24', '22'):
            if per == '24':
                D, S, C_, kw = d, s_all, cal, dict(excl_fn=excl)
                br = (lambda n: breach_full(daily[n][0], daily[n][4], w)) if w else None
            else:
                D, S, C_, kw = bd, bs, bcal, dict(date_lo=bb.Y0, date_hi=bb.END)
                br = (lambda n: dma_gate_dates(bd[n]['dts'], bd[n]['C'], n=w, min_n=min(w, 100))) if w else None
            nb, ex = {}, {}
            if w:
                g = gates({n: br(n) for n in TWELVE}, K)
                nb = {n: g[n] for n in TWELVE}
                ex['gate_cash'] = True
            if bench:
                ex['tier2'] = set(DIVERS)
            sl = [x for x in S if x['name'] in TWELVE + (DIVERS if bench else [])]
            r = simulate(D, sl, C_, capital=CAP, mode='pooled', collect_trades=True,
                         no_buy=nb or None, **ex, **kw)
            eq, c = r['equity'], r['cal']
            gated = sum(len(nb[n] & set(c)) for n in TWELVE) / (12 * len(c)) if w else 0.0
            if per == '24':
                res[per] = dict(full=r['full'], test=r['test'], maxdd=r['maxdd'], test_dd=mdd(eq[k:]), gated=gated)
            else:
                i22 = max(i for i, x in enumerate(c) if x <= bb.Y1)
                res[per] = dict(y2022=eq[i22] / eq[0] - 1, to_jun23=eq[-1] / eq[0] - 1, maxdd=r['maxdd'], gated=gated)
        out[tag] = res
        a, b = res['24'], res['22']
        print(f'  {tag:34s}| {a["full"]*100:5.1f} {a["test"]*100:6.1f} {a["maxdd"]*100:5.1f} {a["test_dd"]*100:5.1f}'
              f' {a["gated"]*100:4.0f}% | {b["y2022"]*100:5.1f}% {b["to_jun23"]*100:6.1f}% {b["maxdd"]*100:5.1f}%'
              f' {b["gated"]*100:4.0f}%', flush=True)
    json.dump(out, open('bear17_fast.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
