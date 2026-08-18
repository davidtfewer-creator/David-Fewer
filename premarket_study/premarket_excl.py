"""
The pre-market exclusion rule (user's manual intervention, made mechanical).

Idea (user, 18 Aug 2026): each morning, some buy limits are visibly dead --
the model's bid sits far below where the stock is actually trading pre-market
(information the model does not have). Excluding those sleeves pools their
capital into orders that can actually fill.

The prevClose version of this rule FAILED (HANDOVER 3.15): depth measured
against yesterday's close mismeasures the distance to the market, and deep-vs-
close fills are the book's best trades. Measured against the 09:25 PRE-MARKET
price the picture inverts:

  fill rates by bid depth vs PM-last:  0-2%: 64%   2-4%: 24%   4-6%: 13%
                                       6-8%: 6.6%  8-12%: 4.1%  >12%: 0/133
  and the rare deep-vs-PM fills average ~zero or negative (adverse-information
  days: a stock that gaps up and still crashes through a deep bid is a news
  reversal, not a harvestable dip).

RULE: exclude a sleeve's order when bid < PM_last * (1 - thr). Strictly ex ante
(PM_last = last pre-market print before 09:30, the screen at 09:25); names/days
without PM data leave the rule inactive.

RESULT (pooled nine-name book, train-pick frozen): thr = 4% is a BOTH-HALVES
WIN, the first structural overlay to clear the bar in eleven tests:
  train 45.4% -> 53.3%   TEST 110.7% -> 122.4%   maxDD 29.2% -> 27.5%
Robust: every threshold 3-12% beats baseline on the tested half (a plateau,
not a spike); gains spread across 7 of 9 names (RKLB is the exception -- its
deep fills stay good); 23.9% of sleeve-days excluded. It survives where the
other overlays died because it does not reshape the harvest -- it adds
information the model lacks, pruning orders that rarely fill and fill badly.

Requires data_pm/{NAME}_pm.xlsx (04:00-09:25 bars) and the pm_last.pkl cache.
"""
import json
import pickle

import numpy as np

from engine import Params
from fresh_opt_cands import aw_params
from book_sim import load_all, simulate, NAMES as N8

BUCKETS = [(-0.02, 0.0), (-0.04, -0.02), (-0.06, -0.04),
           (-0.08, -0.06), (-0.12, -0.08), (-1.0, -0.12)]


def load():
    t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                bayes_pct=0.5, years=2.2, ou_W=80)
    mrvl = aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    names = N8 + ['MRVL']
    data, sleeves, cal = load_all(names=names, params_override={'MRVL': mrvl})
    pm = pickle.load(open('data_pm/pm_last.pkl', 'rb'))
    return data, sleeves, cal, pm, names


def diagnostic(data, sleeves, pm):
    stats = {b: dict(days=0, fills=0, rets=[]) for b in BUCKETS}
    for s in sleeves:
        nd = data[s['name']]
        pms = pm[s['name']]
        for i in range(1, len(nd['dts'])):
            bid = nd[s['bids']][i]
            d_ = nd['dts'][i]
            if bid is None or d_ not in pms:
                continue
            dep = bid / pms[d_] - 1
            b = next((bb for bb in BUCKETS if bb[0] <= dep < bb[1]), None)
            if b is None:
                continue
            stats[b]['days'] += 1
            if nd['L'][i] <= bid + 1e-12:
                stats[b]['fills'] += 1
                tgt = bid + nd['C'][i - 1] * s['prem']
                if nd['H'][i] >= tgt - 1e-12 and nd['chk'](i, bid, tgt):
                    stats[b]['rets'].append(tgt / bid - 1)
                else:
                    for j in range(i + 1, len(nd['dts'])):
                        if nd['H'][j] >= tgt - 1e-12:
                            stats[b]['rets'].append(tgt / bid - 1)
                            break
                        if (nd['dts'][j] - nd['dts'][i]).days >= 50:
                            stats[b]['rets'].append(nd['O'][j] / bid - 1)
                            break
    print('DIAGNOSTIC — fill rate by bid depth vs the 09:25 pre-market price:')
    for b in BUCKETS:
        st = stats[b]
        if not st['days']:
            continue
        r = np.array(st['rets']) if st['rets'] else np.array([0.0])
        print(f'  {b[0]*100:4.0f}% to {b[1]*100:3.0f}%: {st["days"]:5d} days  '
              f'{st["fills"]:4d} fills ({st["fills"]/st["days"]*100:4.1f}%)  '
              f'avg {r.mean()*100:+5.2f}%  med {np.median(r)*100:+5.2f}%', flush=True)


def mk_rule(data, pm, thr):
    def fn(name, i, bid):
        pml = pm[name].get(data[name]['dts'][i])
        return pml is not None and bid < pml * (1 - thr)
    return fn


def main():
    data, sleeves, cal, pm, names = load()
    diagnostic(data, sleeves, pm)
    print('\nINTERVENTION — pooled nine-name book:', flush=True)
    cells = []
    for thr in [None, 0.03, 0.035, 0.04, 0.045, 0.05, 0.06, 0.08, 0.12]:
        fn = None if thr is None else mk_rule(data, pm, thr)
        r = simulate(data, sleeves, cal, capital=9_000_000, excl_fn=fn)
        lab = 'baseline' if thr is None else f'PM-depth >{thr*100:.1f}%'
        cells.append((thr, r))
        print(f'  {lab:18s} full {r["full"]*100:6.1f}%  train {r["train"]*100:5.1f}%  '
              f'TEST {r["test"]*100:6.1f}%  DD {r["maxdd"]*100:4.1f}%', flush=True)
    best = max(cells[1:], key=lambda c: c[1]['train'])
    print(f'\n  train-pick {best[0]*100:.1f}% -> frozen TEST {best[1]["test"]*100:.1f}% '
          f'(baseline {cells[0][1]["test"]*100:.1f}%)', flush=True)


if __name__ == '__main__':
    main()
