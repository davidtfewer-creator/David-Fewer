"""
book15.py — the twelve-name book plus PLTR, TSLA and RKLB (user, 21 Oct 2026).

Vector basis by the established rule (parallel_book): train->test rho >= 0.20
earns the fitted vector, otherwise the NEUTRAL seed. All three failed:
PLTR -0.59, TSLA -0.30, RKLB -0.06 (fittability.py, 300 vectors), so all three
run on the neutral seed -- the same position PARR was in.

Each name is added on its own as well as all three together, so that a name
which helps is not hidden by one that hurts. PM rule on every name; no breadth
gate (§3.66).
"""
import json
import statistics

from baseline_check import ROSTER
from book12 import pm_rule_for
from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import WINDOWS, t0
from fresh_opt_cands import aw_params
from parallel_book import load_rho, load_vecs
from two_day import x0_vector

CAP = 6_900_000
TWELVE = ROSTER + ['RTX', 'DE', 'NVDA']
NEW = ['PLTR', 'TSLA', 'RKLB']
AI = {'AVGO', 'MU', 'TSM', 'MRVL', 'VRT', 'VST', 'NVDA', 'PLTR', 'TSLA', 'RKLB'}


def main():
    rho, vecs = load_rho(), load_vecs()
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    for n in ['RTX', 'DE', 'NVDA'] + NEW:
        r = rho.get(n)
        fit = r is not None and r >= 0.20 and n in vecs
        po[n] = params_from_vec(vecs[n] if fit else x0_vector(1), t0())
        print(f'  {n:5s} rho {r:+.2f} -> {"fitted" if fit else "NEUTRAL"}')
    print(f'  capital ${CAP/1e6:.2f}m\n')

    arms = [('TWELVE (current)', TWELVE)] + \
           [(f'+ {n} only', TWELVE + [n]) for n in NEW] + \
           [('FIFTEEN (+ all three)', TWELVE + NEW)]
    out = {}
    print(f'  {"arm":24s}{"full":>7s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"ret/DD":>8s}'
          f'{"fills/yr":>10s}{"AI $":>7s}   stress Jan-Apr25 / Feb-Jun25 / Jun-Jul26')
    for tag, names in arms:
        d, s, cal = load_all(names=names, params_override=po)
        r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True,
                     excl_fn=pm_rule_for(d, set(names)))
        y = len(cal) / 252
        cs = [t['cost'] for t in r['trades']]
        ai = sum(t['cost'] for t in r['trades'] if t['name'] in AI) / sum(cs)
        eq, st = r['equity'], []
        for _, lo, hi in WINDOWS:
            ix = [i for i, dd in enumerate(cal) if lo <= dd <= hi]
            st.append((eq[ix[-1]]/eq[ix[0]]-1)*100 if len(ix) > 1 else float('nan'))
        rd = r['full'] / r['maxdd']
        print(f'  {tag:24s}{r["full"]*100:>7.1f}{r["train"]*100:>7.1f}{r["test"]*100:>7.1f}'
              f'{r["maxdd"]*100:>7.1f}{rd:>8.2f}{r["fills"]/y:>10.0f}{ai*100:>6.0f}%   '
              + ' / '.join(f'{x:+.1f}%' for x in st))
        per = {}
        for t in r['trades']:
            per.setdefault(t['name'], [0, 0.0])
            per[t['name']][0] += 1
            per[t['name']][1] += t['pnl']
        out[tag] = dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'],
                        ret_dd=rd, per_yr=r['fills']/y, ai_share=ai, stress=st,
                        per_name={k: dict(fills=v[0], pnl=v[1]) for k, v in per.items()})

    base = out['TWELVE (current)']
    print(f'\n  vs TWELVE:')
    for tag in list(out)[1:]:
        o = out[tag]
        print(f'    {tag:24s} full {(o["full"]-base["full"])*100:+5.1f}pp  '
              f'test {(o["test"]-base["test"])*100:+5.1f}pp  '
              f'maxDD {(o["maxdd"]-base["maxdd"])*100:+5.1f}pp  '
              f'fills {o["per_yr"]-base["per_yr"]:+4.0f}/yr  '
              f'AI {(o["ai_share"]-base["ai_share"])*100:+4.0f}pp')

    f15 = out['FIFTEEN (+ all three)']['per_name']
    tot = sum(v['pnl'] for v in f15.values())
    print(f'\n  in the FIFTEEN, the three new names contribute:')
    for n in NEW:
        v = f15.get(n, dict(fills=0, pnl=0))
        print(f'    {n:5s} {v["fills"]:>4d} fills  ${v["pnl"]/1e3:>7.0f}k  '
              f'{v["pnl"]/tot*100:>5.1f}% of book P&L')
    json.dump(out, open('book15.json', 'w'), indent=1)
    print('\nwrote book15.json')


if __name__ == '__main__':
    main()
