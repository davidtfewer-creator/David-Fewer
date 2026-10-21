"""
stop_study.py — per-stock time stops in the twelve-name book (user, 21 Oct 2026).

User: *"look into the stop period for the 12 stock book and see what impact this
has on drawdown levels. At the moment, we have the stop at 50 days for each
stock but I think we can do better on the drawdown/return/trade frequency
through varying this by stock."*

Prior work (§3.5x dip_stop_sweep) found the uniform 50 days best for only 3 of 9
names in isolation, with a +7.4pp per-name gain that was pure hindsight. This
asks the untested version: DRAWDOWN, in the POOLED book, where a shorter stop
also frees capital for other names.

Twelve per-name stops is twelve new parameters, which is how a backtest gets
overfitted. So the protocol is fixed in advance:
  1. uniform sweep            the shape of the trade-off, all names together
  2. per-name selection       each name's stop chosen on the TRAIN half only,
                              coordinate-wise (one name at a time, others at 50)
  3. out-of-sample judgement  the assembled set vs the best UNIFORM stop (also
                              chosen on train), both scored on the TEST half
If per-name does not beat uniform on the test half, the extra parameters are
fitting noise and uniform is the answer.
"""
import json
import time

from fresh_opt import SPLIT
from lowdd_book import TWELVE, params, CAP
from book12 import pm_rule_for
from book_sim import load_all, simulate

NONE = 10_000                        # effectively no stop
GRID = [20, 30, 40, 50, 75, NONE]
UNIFORM = [10, 20, 30, 40, 50, 60, 75, 100, NONE]


def mdd(eq):
    pk, m = eq[0], 0.0
    for v in eq:
        pk = max(pk, v)
        m = max(m, (pk - v) / pk)
    return m


def lab(x):
    return 'none' if x >= NONE else f'{x}d'


def main():
    po, _ = params(TWELVE)
    t0 = time.time()
    d, s, cal = load_all(names=TWELVE, params_override=po)
    excl = pm_rule_for(d, set(TWELVE))
    k = max(i for i, x in enumerate(cal) if x <= SPLIT)
    y = len(cal) / 252
    print(f'loaded twelve in {time.time()-t0:.0f}s; split {SPLIT}\n')

    def go(stops):
        r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True,
                     excl_fn=excl, stop_days=stops)
        eq = r['equity']
        tr_dd, te_dd = mdd(eq[:k+1]), mdd(eq[k:])
        nstop = sum(1 for t in r['trades'] if t['stopped'])
        return dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'],
                    tr_dd=tr_dd, te_dd=te_dd, fills=r['fills']/y, stops=nstop/y,
                    tr_rd=r['train']/tr_dd if tr_dd else 0, te_rd=r['test']/te_dd if te_dd else 0)

    t1 = time.time()
    base = go(None)
    print(f'(one simulate = {time.time()-t1:.1f}s)')
    chk = go(50)
    assert abs(base['full'] - chk['full']) < 1e-12, 'stop_days=50 must equal the default'
    print(f'baseline check: default and stop_days=50 identical '
          f'({base["full"]*100:.1f}% / {base["maxdd"]*100:.1f}% DD)\n')

    hdr = (f'  {"stop":>6s}{"full":>7s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"trDD":>7s}'
           f'{"teDD":>7s}{"trR/DD":>8s}{"teR/DD":>8s}{"fills":>7s}{"stops":>7s}')

    print('=== 1. UNIFORM — every name on the same stop ===\n' + hdr)
    uni = {}
    for x in UNIFORM:
        m = go(x)
        uni[x] = m
        print(f'  {lab(x):>6s}{m["full"]*100:>7.1f}{m["train"]*100:>7.1f}{m["test"]*100:>7.1f}'
              f'{m["maxdd"]*100:>7.1f}{m["tr_dd"]*100:>7.1f}{m["te_dd"]*100:>7.1f}'
              f'{m["tr_rd"]:>8.2f}{m["te_rd"]:>8.2f}{m["fills"]:>7.0f}{m["stops"]:>7.1f}',
              flush=True)
    best_u = max(uni, key=lambda x: uni[x]['tr_rd'])           # chosen on TRAIN
    print(f'\n  best uniform chosen on TRAIN return/drawdown: {lab(best_u)}')

    print('\n=== 2. PER-NAME — each chosen on the TRAIN half, others held at 50 ===\n')
    print(f'  {"name":6s}' + ''.join(f'{lab(x):>8s}' for x in GRID) + '   pick   (train R/DD)')
    pick = {}
    for nm in TWELVE:
        row = {}
        for x in GRID:
            st = {n: 50 for n in TWELVE}
            st[nm] = x
            row[x] = go(st)['tr_rd']
        bx = max(row, key=row.get)
        pick[nm] = bx
        print(f'  {nm:6s}' + ''.join(f'{row[x]:>8.2f}' for x in GRID)
              + f'   {lab(bx):>5s}', flush=True)

    print('\n=== 3. OUT OF SAMPLE — judged on the TEST half ===\n' + hdr)
    arms = {'50d (current)': None, f'best uniform ({lab(best_u)})': best_u,
            'per-name set': pick}
    res = {}
    for tag, st in arms.items():
        m = go(st)
        res[tag] = m
        print(f'  {tag[:6]:>6s}{m["full"]*100:>7.1f}{m["train"]*100:>7.1f}{m["test"]*100:>7.1f}'
              f'{m["maxdd"]*100:>7.1f}{m["tr_dd"]*100:>7.1f}{m["te_dd"]*100:>7.1f}'
              f'{m["tr_rd"]:>8.2f}{m["te_rd"]:>8.2f}{m["fills"]:>7.0f}{m["stops"]:>7.1f}'
              f'   {tag}', flush=True)
    print('\n  per-name set: ' + ', '.join(f'{n} {lab(v)}' for n, v in pick.items()))

    json.dump(dict(uniform={lab(k): v for k, v in uni.items()}, best_uniform=lab(best_u),
                   per_name={n: lab(v) for n, v in pick.items()},
                   final={k: v for k, v in res.items()}),
              open('stop_study.json', 'w'), indent=1)
    print('\nwrote stop_study.json')


if __name__ == '__main__':
    main()
