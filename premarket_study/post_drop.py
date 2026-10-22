"""
post_drop.py — do names trade better for this model after a significant drop?
(user, 22 Oct 2026: "some stocks perform well and are volatile after a
significant drop (e.g. PLTR, RKLB)" — the premise for a managed-book admission
gate.)

Every name with data is run ALONE (its two sleeves, $1m, 50-day stop; PM rule and
ATH gate on for 2024-26, ATH gate on for 2021-23), and each trade is tagged with
the name's state at entry:
  dd   drawdown of the prior close from its trailing 252-session high
       (needs >= 60 sessions of history, else untagged)
  vol  trailing 20-session realised vol relative to the name's own median
Two lenses, bucketed by dd:
  stock  every day: forward 60-session return and forward 20-session vol
  model  every trade: return on cost, days held, stop rate, and return per
         100 days of capital held (what a pooled book actually earns)
Periods: 2024-26 (data_5min, ~49 names) and 2021-23 (data_bear, 12 names).
Caveat: 2024-26 files start Apr 2024, so the first year's "high" is a
truncated one.
"""
import collections
import functools
import json
import math
import sys

import numpy as np

import bear12_breadth as bb
from book12 import pm_rule_for
from book_sim import load_all, simulate
from lowdd_book import params
from minute_index import DIR

BUCKETS = [(0.0, 0.10), (0.10, 0.25), (0.25, 0.40), (0.40, 1.01)]
LBL = ['<10%', '10-25%', '25-40%', '>40%']
EPS = 0.0


def state(C):
    """dd and relative vol known at the OPEN of session i (uses closes < i)."""
    n = len(C)
    dd, rv = [None] * n, [None] * n
    r = np.diff(np.log(C), prepend=np.nan)
    for i in range(60, n):
        hi = max(C[max(0, i - 252):i])
        dd[i] = 1 - C[i - 1] / hi
        w = r[i - 20:i]
        rv[i] = np.nanstd(w) * math.sqrt(252)
    med = np.nanmedian([x for x in rv if x is not None])
    rv = [None if x is None else x / med for x in rv]
    return dd, rv


def bucket(x):
    for k, (lo, hi) in enumerate(BUCKETS):
        if lo <= x < hi:
            return k
    return None


def scan(period, data, names, sim_kw):
    stock = collections.defaultdict(list)          # bucket -> (fwd60, fwdvol)
    model = collections.defaultdict(list)          # bucket -> trade rows
    per_name = {}
    for n in names:
        D = data[n]
        C = np.array(D['C'], float)
        dts = D['dts']
        dd, rv = state(list(C))
        lr = np.diff(np.log(C))
        for i in range(60, len(C) - 60):
            b = bucket(dd[i])
            stock[b].append((C[i + 59] / C[i - 1] - 1, np.std(lr[i:i + 20]) * math.sqrt(252)))
        sl = [dict(name=n, kind='B', bids='X', prem=D['p'].premium),
              dict(name=n, kind='O', bids='AM', prem=D['p'].ou_prem)]
        r = simulate({n: D}, sl, list(dts), capital=1_000_000, mode='pooled',
                     collect_trades=True, **sim_kw(n, D))
        pos = {d: i for i, d in enumerate(dts)}
        rows = []
        for t in r['trades']:
            i = pos[t['entry']]
            if dd[i] is None:
                continue
            held = max(1, pos[t['exit']] - i)
            row = dict(b=bucket(dd[i]), ret=t['pnl'] / t['cost'], held=held,
                       stopped=t['stopped'], rv=rv[i],
                       up20=bool(C[i - 1] > C[i - 20:i].mean()),
                       up50=bool(C[i - 1] > C[max(0, i - 50):i].mean()))
            rows.append(row)
            model[row['b']].append(row)
        per_name[n] = rows
    return stock, model, per_name


def report(period, stock, model, per_name, out):
    print(f'\n===== {period} =====')
    print(f'  {"dd at entry":12s}{"days%":>7s}{"fwd60":>8s}{"fwdvol":>8s} |'
          f'{"trades":>7s}{"win%":>6s}{"ret/tr":>8s}{"held":>6s}{"stop%":>7s}{"ret/100d":>9s}')
    tot_days = sum(len(v) for v in stock.values())
    res = {}
    for k, l in enumerate(LBL):
        s, m = stock.get(k, []), model.get(k, [])
        f60 = np.mean([x[0] for x in s]) if s else float('nan')
        fv = np.mean([x[1] for x in s]) if s else float('nan')
        if m:
            ret = np.mean([x['ret'] for x in m])
            win = np.mean([x['ret'] > 0 for x in m])
            held = np.mean([x['held'] for x in m])
            stop = np.mean([x['stopped'] for x in m])
            eff = sum(x['ret'] for x in m) / sum(x['held'] for x in m) * 100
        else:
            ret = win = held = stop = eff = float('nan')
        print(f'  {l:12s}{len(s)/tot_days*100:>6.0f}%{f60*100:>7.1f}%{fv*100:>7.0f}% |'
              f'{len(m):>7d}{win*100:>5.0f}%{ret*100:>7.2f}%{held:>6.1f}{stop*100:>6.0f}%{eff*100:>8.2f}%')
        res[l] = dict(day_share=len(s) / tot_days, fwd60=f60, fwdvol=fv, trades=len(m), win=win,
                      ret=ret, held=held, stop=stop, ret_per_100d=eff)
    out[period] = dict(buckets=res)
    # per name: efficiency when deep (>=25%) vs not
    nm = {}
    for n, rows in per_name.items():
        deep = [x for x in rows if x['b'] is not None and x['b'] >= 2]
        shal = [x for x in rows if x['b'] is not None and x['b'] < 2]
        e = lambda xs: (sum(x['ret'] for x in xs) / sum(x['held'] for x in xs) * 100
                        if xs else float('nan'))
        nm[n] = dict(n_deep=len(deep), n_shallow=len(shal), eff_deep=e(deep), eff_shallow=e(shal))
    out[period]['per_name'] = nm
    print(f'\n  deep (>=25% off high) trades by trend at entry: return per 100 days held')
    tr = {}
    for key, lab in (('up20', '20dma'), ('up50', '50dma')):
        for side in (True, False):
            xs = [x for rows in per_name.values() for x in rows
                  if x['b'] is not None and x['b'] >= 2 and x[key] == side]
            e = sum(x['ret'] for x in xs) / sum(x['held'] for x in xs) * 100 if xs else float('nan')
            st = np.mean([x['stopped'] for x in xs]) if xs else float('nan')
            tag = f'{"above" if side else "below"} {lab}'
            tr[tag] = dict(n=len(xs), ret_per_100d=e, stop=st)
            print(f'    {tag:14s} {len(xs):5d} trades  {e*100:7.2f}%/100d  stop {st*100:4.0f}%')
    out[period]['deep_by_trend'] = tr
    print(f'\n  per name, return per 100 days held: shallow (<25% off high) vs deep (>=25%)')
    for n, v in sorted(nm.items(), key=lambda kv: -(kv[1]['n_deep'])):
        if v['n_deep'] >= 5:
            print(f'    {n:5s} shallow {v["eff_shallow"]*100:6.2f}% ({v["n_shallow"]:3d})   '
                  f'deep {v["eff_deep"]*100:6.2f}% ({v["n_deep"]:3d})')


def main():
    out = {}
    import os
    names = sorted(f[:-len('_5min.xlsx')] for f in os.listdir(DIR) if f.endswith('_5min.xlsx'))
    po, _ = params(names)
    ek = {n: dict(ath_target_guard=EPS) for n in names}
    d, _, _ = load_all(engine_kwargs_per_name=ek, names=names, params_override=po)
    pm = {n: pm_rule_for({n: d[n]}, {n}) for n in names}
    report('2024-26', *scan('2024-26', d, names, lambda n, D: dict(excl_fn=pm[n])), out)

    bear = sorted(f[:-len('_5min.xlsx')] for f in os.listdir('data_bear') if f.endswith('_5min.xlsx'))
    orig = bb.run_model
    bb.run_model = functools.partial(orig, ath_target_guard=EPS)
    bb.NAMES = bear
    data, _, _ = bb.build()
    bb.run_model = orig
    report('2021-23', *scan('2021-23', data, bear, lambda n, D: {}), out)
    json.dump(out, open('post_drop.json', 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
