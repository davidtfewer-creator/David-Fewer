"""
capacity17.py — (1) liquidity of the chosen book (§3.95 (b) + 25% name cap)
at $6.9m and $10m, measured as in participation.py (order vs first-hour
dollar volume at or below the bid); names whose 2024-26 file has no volume
column (NEM DLTR RKT TEAM) are reported as unmeasured. (2) how many trades it
takes to tell a name's edge from noise: per-trade return mean and sd by name,
n = (2 sd / mean)^2 for a t-stat of 2, and the years that takes at the name's
fill rate standalone ($1m alone).
"""
import json
import statistics

from book12 import pm_rule_for
from book20 import TWELVE, DIVERS, EPS
from book_sim import load_all, simulate
from lowdd_book import params
from parallel_book import gate_sets
from participation import load_bars, measure

SHADOW_CANDS = ['PLTR', 'TSLA', 'RKLB', 'APLD', 'AAOI', 'CEG', 'UAL', 'LUNR', 'BRKB', 'NVTS', 'AXTI', 'FCX']


def main():
    out = {}
    names = TWELVE + DIVERS
    allp = names + SHADOW_CANDS
    po, _ = params(allp)
    ek = {n: dict(ath_target_guard=EPS) for n in allp}
    d, s_all, cal = load_all(engine_kwargs_per_name=ek, names=allp, params_override=po)
    excl = pm_rule_for(d, set(allp))
    g = gate_sets(TWELVE, 6)[0]
    nb = {n: set(g[n]) for n in TWELVE}
    bars = {n: load_bars(n) for n in names}
    has_vol = {n: any(x[3] > 0 for day in list(bars[n].values())[:50] for x in day) for n in names}
    sl = [x for x in s_all if x['name'] in names]
    print('(1) first-hour participation: order / at-bid dollar volume in the first hour')
    print(f'  {"name":5s}' + ''.join(f'{"$"+str(c/1e6)+"m med":>12s}{"p95":>7s}{">5%":>6s}' for c in (6.9e6, 10e6)))
    res = {}
    for capv in (6.9e6, 10e6):
        r = simulate(d, sl, cal, capital=capv, mode='pooled', collect_trades=True, excl_fn=excl,
                     no_buy=nb, gate_cash=True, tier2=set(DIVERS), exp_cap=0.25, exp_to='cash')
        rows, _ = measure(r['trades'], {n: bars[n] for n in names if has_vol[n]})
        res[capv] = dict(full=r['full'], maxdd=r['maxdd'], rows=rows,
                         max_order=max(t['cost'] for t in r['trades']))
    for n in names:
        line = f'  {n:5s}'
        if not has_vol[n]:
            print(line + '   no volume column in the 2024-26 file -- unmeasured')
            continue
        for capv in (6.9e6, 10e6):
            xs = [x['p_blend'] for x in res[capv]['rows'] if x['name'] == n and x['p_blend'] is not None]
            if xs:
                xs.sort()
                line += (f'{statistics.median(xs)*100:>11.2f}%{xs[int(0.95*(len(xs)-1))]*100:>6.1f}%'
                         f'{sum(1 for x in xs if x > 0.05)/len(xs)*100:>5.0f}%')
            else:
                line += f'{"(no fills)":>25s}'
        print(line)
    for capv in (6.9e6, 10e6):
        print(f'  book at ${capv/1e6:.1f}m: full {res[capv]["full"]*100:.1f}%, maxDD {res[capv]["maxdd"]*100:.1f}%, '
              f'largest single order ${res[capv]["max_order"]/1e6:.2f}m')
    out['participation'] = {str(c): {n: [x['p_blend'] for x in v['rows'] if x['name'] == n]
                                     for n in names} for c, v in res.items()}

    print('\n(2) trades needed to tell edge from noise (standalone $1m, 2024-26)')
    print(f'  {"name":5s}{"trades":>7s}{"/yr":>6s}{"mean":>8s}{"sd":>7s}{"n for t=2":>11s}{"years":>7s}')
    need = {}
    yrs = len(cal) / 252
    for n in names + SHADOW_CANDS:
        D = d[n]
        s1 = [x for x in s_all if x['name'] == n]
        r = simulate({n: D}, s1, list(D['dts']), capital=1_000_000, mode='pooled',
                     collect_trades=True, excl_fn=excl)
        rets = [t['pnl'] / t['cost'] for t in r['trades']]
        if len(rets) < 3:
            continue
        m, sd = statistics.mean(rets), statistics.stdev(rets)
        nn = (2 * sd / m) ** 2 if m > 0 else float('inf')
        py = len(rets) / (len(D['dts']) / 252)
        need[n] = dict(trades=len(rets), per_yr=py, mean=m, sd=sd, n_needed=nn, years=nn / py)
        print(f'  {n:5s}{len(rets):>7d}{py:>6.0f}{m*100:>7.2f}%{sd*100:>6.1f}%{nn:>11.0f}{nn/py:>7.1f}')
    out['trades_needed'] = need
    json.dump(out, open('capacity17.json', 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
