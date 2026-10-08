"""
nem_add_honest.py — the one NEM configuration never tested on honest vectors
(8 Oct 2026).

§3.33 ran swap CF→NEM on all three vectors and ADD-NEM-as-a-tenth-name on the
full-sample reference only. The add case bought 2.3pp of drawdown there, which
is a real trade and was never checked without lookahead. If NEM's gate
classification is in doubt (user, 8 Oct), this is the gap worth closing.

Usage: BAYES_WORKBOOK=<workbook.xlsx> python nem_add_honest.py
"""
import json

from fresh_opt import a_params, b_params
from fresh_opt_cands import aw_params
from book_sim import load_all, simulate
from baseline_check import ROSTER
from cf_swap_test import pm_rule_for, shape_of, t0

c = json.load(open('fresh_opt_cands.json'))
po0 = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
       'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
ref = aw_params(c['NEM']['reference']['vec'], t0())
VEC = {'reference (full-sample)': ref,
       'variant A (train-half)': a_params(c['NEM']['A']['vec'], ref),
       'variant B (train-half)': b_params(c['NEM']['B']['vec'], ref, c['NEM']['B']['mle'])}

data, sl, cal = load_all(names=ROSTER, params_override=po0)
base = simulate(data, sl, cal, excl_fn=pm_rule_for(data), collect_trades=True)
print(f'  {"":32s}{"full":>7s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"fills":>7s}'
      f'{"NEM/yr":>8s}{"top3rd":>8s}   | deltas')
print(f'  {"nine names (baseline)":32s}{base["full"]*100:>7.1f}{base["train"]*100:>7.1f}'
      f'{base["test"]*100:>7.1f}{base["maxdd"]*100:>7.1f}{base["fills"]:>7d}'
      f'{"-":>8s}{"-":>8s}')
out = {}
for tag, p in VEC.items():
    po = dict(po0); po['NEM'] = p
    d2, s2, c2 = load_all(names=ROSTER + ['NEM'], params_override=po)
    r = simulate(d2, s2, c2, excl_fn=pm_rule_for(d2), collect_trades=True)
    sh = shape_of(r['trades'], 'NEM', len(c2) / 252)
    out[tag] = dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'])
    print(f'  {"add NEM, " + tag:32s}{r["full"]*100:>7.1f}{r["train"]*100:>7.1f}'
          f'{r["test"]*100:>7.1f}{r["maxdd"]*100:>7.1f}{r["fills"]:>7d}'
          f'{sh["per_yr"]:>8.0f}{(sh["top3"] or 0)*100:>7.0f}%'
          f'   | {(r["full"]-base["full"])*100:+5.1f}{(r["train"]-base["train"])*100:+6.1f}'
          f'{(r["test"]-base["test"])*100:+6.1f}{(r["maxdd"]-base["maxdd"])*100:+6.1f}')
json.dump(out, open('nem_add_honest.json', 'w'), indent=1, default=str)
print('\nsaved nem_add_honest.json')
