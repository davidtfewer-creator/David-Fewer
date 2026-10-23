"""
liq_massive.py — liquidity at $10m for every slot, now that the Massive pull
(data_massive/2024_2026, 23 Oct 2026) gives all 25 a volume column
(HANDOVER 3.103). Same measure as liq17b: each fill's order against the
first-hour dollar volume at or below its bid, re-expressed for a book HELD at
$10m. Book = (b) + 25% name cap + CF 2% / 10% backstop. The eight Shadow names
are measured as if they were Bench names (each added alone, gate on as in the
backtest), which is how they would trade if admitted.
"""
import json
import os

import participation as P_
from book12 import pm_rule_for
from book20 import TWELVE, DIVERS, EPS
from book_sim import load_all, simulate
from lowdd_book import params
from parallel_book import gate_sets
from liq17 import trailing_h1, CAPITAL

SHADOW = ['PLTR', 'TSLA', 'RKLB', 'APLD', 'AAOI', 'CEG', 'UAL', 'LUNR']
P_.DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_massive', '2024_2026')


def run(names, bench, d, s_all, cal, excl, g, bars, med):
    L = {n: (0.02 if n == 'CF' else 0.10) for n in names}
    oc = {n: {x: L[n] * v for x, v in med[n].items()} for n in names if n in med}
    sl = [x for x in s_all if x['name'] in names]
    r = simulate(d, sl, cal, capital=CAPITAL, mode='pooled', collect_trades=True, excl_fn=excl,
                 no_buy={n: set(g[n]) for n in TWELVE}, gate_cash=True, tier2=set(bench),
                 exp_cap=0.25, exp_to='cash', order_cap=oc)
    pos = {x: i for i, x in enumerate(cal)}
    rows, _ = P_.measure(r['trades'], bars)
    out = {}
    for n in names:
        xs = sorted(x['p_blend'] * CAPITAL / r['equity'][max(0, pos[x['entry']] - 1)]
                    for x in rows if x['name'] == n and x['p_blend'] is not None)
        if xs:
            out[n] = dict(fills=len(xs), median=xs[len(xs) // 2], p95=xs[int(0.95 * (len(xs) - 1))],
                          over5=sum(1 for x in xs if x > 0.05) / len(xs))
    return out


def main():
    names = TWELVE + DIVERS + SHADOW
    po, _ = params(names)
    ek = {n: dict(ath_target_guard=EPS) for n in names}
    d, s_all, cal = load_all(engine_kwargs_per_name=ek, names=names, params_override=po)
    excl = pm_rule_for(d, set(names))
    g = gate_sets(TWELVE, 6)[0]
    bars = {n: P_.load_bars(n) for n in names}
    med = {n: trailing_h1(b) for n, b in bars.items()}
    res = run(TWELVE + DIVERS, DIVERS, d, s_all, cal, excl, g, bars, med)
    for sh in SHADOW:
        res.update({sh: run(TWELVE + DIVERS + [sh], DIVERS + [sh], d, s_all, cal, excl, g, bars, med).get(sh)})
    print(f'  {"name":5s}{"fills":>6s}{"median":>9s}{"p95":>8s}{"> 5%":>7s}   (order / first-hour at-bid $ volume, book held at $10m)')
    for n in names:
        v = res.get(n)
        print(f'  {n:5s}' + (f'{v["fills"]:>6d}{v["median"]*100:>8.2f}%{v["p95"]*100:>7.1f}%{v["over5"]*100:>6.0f}%'
                             if v else '   no fills'))
    json.dump(res, open('liq_massive.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
