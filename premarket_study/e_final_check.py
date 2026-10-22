"""
e_final_check.py — (1) were APLD's and AAOI's profits isolated runs? Standalone
trade P&L by calendar month (§3.87 single-name setup) and the share of each
name's total from its best 3 months, against the other bench names. (2) the user
chose breadth K>=6 + E without APLD/AAOI (18 names); test candidates for the
two empty slots, each added alone to the bench as always-eligible tier 2.
"""
import collections
import json

from fresh_opt import SPLIT
from lowdd_book import TWELVE, params
from book12 import pm_rule_for
from book_sim import load_all, simulate
from bear_stop import CAP
from parallel_book import gate_sets
from recap_9v12 import mdd
from managed20 import REBOUND, EPS, admitted

BENCH6 = ['PLTR', 'TSLA', 'RKLB', 'NEM', 'LEN', 'DLTR']
CANDS = ['APLD', 'AAOI', 'CEG', 'UAL', 'LUNR', 'NVTS', 'AXTI', 'TEAM', 'FCX', 'EXPE', 'HUM', 'RKT']


def main():
    out = {}
    names = TWELVE + BENCH6 + CANDS
    po, _ = params(names)
    ek = {n: dict(ath_target_guard=EPS) for n in names}
    d, s_all, cal_all = load_all(engine_kwargs_per_name=ek, names=names, params_override=po)
    excl = pm_rule_for(d, set(names))

    print('(1) standalone trade P&L concentration ($1m alone, 2024-26)')
    conc = {}
    for n in BENCH6 + CANDS:
        D = d[n]
        sl = [x for x in s_all if x['name'] == n]
        r = simulate({n: D}, sl, list(D['dts']), capital=1_000_000, mode='pooled',
                     collect_trades=True, excl_fn=excl)
        m = collections.defaultdict(float)
        for t in r['trades']:
            m[t['exit'].strftime('%Y-%m')] += t['pnl']
        tot = sum(m.values())
        top = sorted(m.items(), key=lambda kv: -kv[1])[:3]
        px0, px1 = D['C'][0], D['C'][-1]
        conc[n] = dict(total=tot, top3=sum(v for _, v in top), top3_months=[k for k, _ in top],
                       stock_move=px1 / px0 - 1)
        print(f'  {n:5s} total ${tot/1e3:+6.0f}k  best 3 months ${conc[n]["top3"]/1e3:+6.0f}k '
              f'({conc[n]["top3"]/tot*100 if tot > 0 else float("nan"):4.0f}% of total) '
              f'{",".join(k for k, _ in top)}   stock {px0:.1f} -> {px1:.1f} ({(px1/px0-1)*100:+.0f}%)')
    out['concentration'] = conc

    print('\n(2) breadth K>=6 + E, bench = PLTR TSLA RKLB (drop-admitted X40) + NEM LEN DLTR, + one candidate')
    cal = cal_all
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    yrs = len(cal) / 252
    g6 = gate_sets(TWELVE, 6)[0]
    print(f'  {len(cal)} sessions')
    print(f'  {"arm":24s}{"full":>6s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"tstDD":>7s}{"fills":>6s}{"cand$":>8s}')
    for c in [None] + CANDS:
        bench = BENCH6 + ([c] if c else [])
        nb = {n: set(g6[n]) for n in TWELVE}
        nb.update({n: set(cal) - admitted(d[n], 0.40, 60, None) for n in ('PLTR', 'TSLA', 'RKLB')})
        sl = [x for x in s_all if x['name'] in TWELVE + bench]
        r = simulate(d, sl, cal, capital=CAP, mode='pooled', collect_trades=True, excl_fn=excl,
                     no_buy=nb, gate_cash=True, tier2=set(bench))
        cp = sum(t['pnl'] for t in r['trades'] if t['name'] == c) if c else 0.0
        tag = f'+{c}' if c else 'eighteen (chosen)'
        row = dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'],
                   test_dd=mdd(r['equity'][k:]), fills_yr=r['fills'] / yrs, cand_pnl=cp)
        out[tag] = row
        print(f'  {tag:24s}{row["full"]*100:>6.1f}{row["train"]*100:>7.1f}{row["test"]*100:>7.1f}'
              f'{row["maxdd"]*100:>7.1f}{row["test_dd"]*100:>7.1f}{row["fills_yr"]:>6.0f}{cp/1e3:>+7.0f}k',
              flush=True)
    json.dump(out, open('e_final_check.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
