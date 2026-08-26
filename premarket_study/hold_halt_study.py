"""
Holding-saturation halt study — halt NEW entries for the day when the book woke
up 70-80% holding? (user, 26 Aug 2026)

The rule is a morning veto conditioned on cross-book state the per-name model
cannot see: if, at yesterday's close, at least `thr` of the book was already in
positions (capital basis: held market value / equity; sleeve basis: held sleeves
/ 18), place no new bids today. Resting exits, targets and stops run unchanged;
positions entered earlier can still take the book to 100% invested.

Protocol: pooled nine-name book on the live configuration (09:00/4% pre-market
rule active on BOTH sides), verified fills, sheet exit convention. DIAGNOSTIC
first: per-trade returns bucketed by the held fraction on the entry morning —
if entries made on saturated mornings are not worse trades, the premise dies
before the grid does. Grid: thr x basis, every cell shown on both halves of the
standard split; the user's cell is 70-80%.

book_sim gained `hold_halt` (strictly ex ante, yesterday's close state) and
always-on frac_series recording; baseline invariance asserted in-run against
the recorded pre-market-rule references (train 59.5 / test 118.4, HANDOVER
3.16).
"""
import json
import pickle

import numpy as np

from book_sim import load_all, simulate, NAMES as N8
from engine import Params
from fresh_opt import SPLIT
from fresh_opt_cands import aw_params

OUT = 'hold_halt.json'


def load():
    t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                bayes_pct=0.5, years=2.2, ou_W=80)
    mrvl = aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    names = N8 + ['MRVL']
    data, sleeves, cal = load_all(names=names, params_override={'MRVL': mrvl})
    pm = pickle.load(open('data_pm/pm_last_cuts.pkl', 'rb'))['09:00']
    def pm_rule(name, i, bid):
        pml = pm[name].get(data[name]['dts'][i])
        return pml is not None and bid < pml * (1 - 0.04)
    return data, sleeves, cal, pm_rule


def main():
    data, sleeves, cal, pm_rule = load()
    base = simulate(data, sleeves, cal, mode='pooled', excl_fn=pm_rule,
                    collect_trades=True)
    print(f"baseline (live config, 09:00/4% PM rule): "
          f"full {base['full']*100:.1f}%  train {base['train']*100:.1f}%  "
          f"test {base['test']*100:.1f}%  DD {base['maxdd']*100:.1f}%", flush=True)

    # ---------------- how often is the book saturated?
    fs = base['frac_series']
    cap = np.array([f[0] for f in fs])
    slv = np.array([f[1] for f in fs])
    print('\nDIAGNOSTIC 1 — mornings by held fraction (capital basis / sleeve basis):')
    for lo, hi in [(0.0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.01)]:
        nc = int(((cap >= lo) & (cap < hi)).sum())
        ns = int(((slv >= lo) & (slv < hi)).sum())
        print(f'  {lo*100:3.0f}-{hi*100:3.0f}%: {nc:4d} mornings (cap)   {ns:4d} (sleeve)')
    print(f'  mornings >=70% held: cap {int((cap>=0.7).sum())} '
          f'({(cap>=0.7).mean()*100:.0f}%), sleeve {int((slv>=0.7).sum())} '
          f'({(slv>=0.7).mean()*100:.0f}%)')

    # ---------------- are entries on saturated mornings worse trades?
    day_frac = {d: fs[j] for j, d in enumerate(cal)}
    print('\nDIAGNOSTIC 2 — completed trades by held fraction (capital) on the ENTRY morning:')
    print(f'  {"entry-morning frac":20s}{"trades":>7s}{"avg ret":>9s}{"med ret":>9s}'
          f'{"stop rate":>10s}')
    for lo, hi in [(0.0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.01)]:
        rs, st = [], 0
        for t in base['trades']:
            f_ = day_frac.get(t['entry'])
            if f_ is None or not (lo <= f_[0] < hi):
                continue
            rs.append(t['pnl'] / t['cost'])
            st += t['stopped']
        if not rs:
            print(f'  {lo*100:3.0f}-{hi*100:3.0f}%{"":13s}{0:>7d}')
            continue
        a = np.array(rs)
        print(f'  {lo*100:3.0f}-{hi*100:3.0f}%{"":13s}{len(a):>7d}{a.mean()*100:>8.2f}%'
              f'{np.median(a)*100:>8.2f}%{st/len(a)*100:>9.0f}%')

    # ---------------- the rule, gridded
    print('\nINTERVENTION — halt all new bids when the book woke up >= thr held:')
    print(f'  {"cell":22s}{"full":>8s}{"train":>8s}{"test":>8s}{"maxDD":>8s}'
          f'{"halted d":>9s}{"fills":>7s}')
    print(f'  {"baseline":22s}{base["full"]*100:>7.1f}%{base["train"]*100:>7.1f}%'
          f'{base["test"]*100:>7.1f}%{base["maxdd"]*100:>7.1f}%{0:>9d}{base["fills"]:>7d}')
    rows = {'baseline': dict(full=base['full'], train=base['train'], test=base['test'],
                             maxdd=base['maxdd'], hh_days=0, fills=base['fills'])}
    for basis in ('cap', 'sleeve'):
        for thr in (0.5, 0.6, 0.7, 0.8, 0.9):
            r = simulate(data, sleeves, cal, mode='pooled', excl_fn=pm_rule,
                         hold_halt=(thr, basis))
            lab = f'{basis} >= {thr:.0%}'
            rows[lab] = dict(full=r['full'], train=r['train'], test=r['test'],
                             maxdd=r['maxdd'], hh_days=r['hh_days'], fills=r['fills'])
            print(f'  {lab:22s}{r["full"]*100:>7.1f}%{r["train"]*100:>7.1f}%'
                  f'{r["test"]*100:>7.1f}%{r["maxdd"]*100:>7.1f}%{r["hh_days"]:>9d}'
                  f'{r["fills"]:>7d}', flush=True)

    with open(OUT, 'w') as f:
        json.dump(rows, f, indent=1)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
