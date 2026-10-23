"""
toggle17.py — what should the include-toggle do in the new book? (user, 23 Oct
2026). Chosen book (§3.95 (b): 200dma K>=6 + E to NEM LEN DLTR RKT TEAM) with
the 25% name cap (§3.97). The user toggled CF and VLO off when he judged they
would not fill; three brackets from §3.77:
  S1  off on mornings neither sleeve could fill (perfect foresight -- generous)
  S2  off while above their 50dma (the "major upward trajectory" toggle)
  S3  off permanently
each with the toggled share redistributed (today's workbook), held in cash, or
lent to the bench. Both periods.
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

TOG = ('CF', 'VLO')


def scen(D, cal):
    out = {'S0 none': None}
    s1, s2, s3 = {}, {}, {}
    for n in TOG:
        nd = D[n]
        s1[n] = {nd['dts'][i] for i in range(1, len(nd['dts']))
                 if [b for b in (nd['X'][i], nd['AM'][i]) if b is not None]
                 and nd['L'][i] > max(b for b in (nd['X'][i], nd['AM'][i]) if b is not None) + 1e-12}
        C = nd['C']
        s2[n] = {nd['dts'][i] for i in range(50, len(C)) if C[i - 1] > sum(C[i - 50:i]) / 50}
        s3[n] = set(nd['dts'])
    out.update({'S1 off on no-fill mornings': s1, 'S2 off while above 50dma': s2,
                'S3 off permanently': s3})
    return out


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
    P = {'24': (d, s_all, cal, dict(excl_fn=excl), gate_sets(TWELVE, 6)[0]),
         '22': (bd, bs, bcal, dict(date_lo=bb.Y0, date_hi=bb.END),
                gates({n: dma_gate_dates(bd[n]['dts'], bd[n]['C']) for n in TWELVE}, 6))}
    S = {per: scen(P[per][0], P[per][2]) for per in P}
    print(f'  {"toggle / where its share goes":44s}| 24-26 full  test maxDD tstDD fills | 2022  to Jun23 maxDD')
    for sc in S['24']:
        for to in (('redistribute', 'cash', 'bench') if S['24'][sc] else ('-',)):
            res = {}
            for per in ('24', '22'):
                D, SL, C_, kw, G = P[per]
                nb = {n: set(G[n]) for n in TWELVE}
                ex = dict(gate_cash=True, tier2=set(DIVERS), exp_cap=0.25, exp_to='cash')
                if S[per][sc]:
                    ex.update(toggle_off=S[per][sc], toggle_to=to)
                r = simulate(D, SL, C_, capital=CAP, mode='pooled', collect_trades=True,
                             no_buy=nb, **ex, **kw)
                assert min(r['cash']) > -1e-6
                eq, c = r['equity'], r['cal']
                tf = sum(1 for t in r['trades'] if t['name'] in TOG)
                bf = sum(1 for t in r['trades'] if t['name'] in DIVERS)
                if per == '24':
                    res[per] = dict(full=r['full'], test=r['test'], maxdd=r['maxdd'], test_dd=mdd(eq[k:]),
                                    fills_yr=r['fills'] / (len(c) / 252), tog_fills=tf, bench_fills=bf)
                else:
                    i22 = max(i for i, x in enumerate(c) if x <= bb.Y1)
                    res[per] = dict(y2022=eq[i22] / eq[0] - 1, to_jun23=eq[-1] / eq[0] - 1,
                                    maxdd=r['maxdd'], tog_fills=tf, bench_fills=bf)
            tag = f'{sc} | {to}'
            out[tag] = res
            a, b = res['24'], res['22']
            print(f'  {tag:44s}| {a["full"]*100:5.1f} {a["test"]*100:6.1f} {a["maxdd"]*100:5.1f} {a["test_dd"]*100:5.1f}'
                  f' {a["fills_yr"]:4.0f} | {b["y2022"]*100:5.1f}% {b["to_jun23"]*100:6.1f}% {b["maxdd"]*100:5.1f}%',
                  flush=True)
    for per in ('24', '22'):
        for sc, v in S[per].items():
            if v:
                C_ = P[per][2]
                print(f'  {per} {sc}: ' + ', '.join(f'{n} off {len(v[n] & set(C_))/len(C_)*100:.0f}% of days' for n in TOG))
    json.dump(out, open('toggle17.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
