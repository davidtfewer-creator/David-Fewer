"""
toggle_trend.py — the realistic middle case: the diversifiers switched off for
the DURATION of an uptrend, not just on isolated no-fill mornings.

toggle_cost.py found that switching CF/VLO off on individual no-fill days costs
almost nothing (maxDD 24.3% vs 24.2%), because the reserved cash simply returns
to the pool the next morning. Switching them off PERMANENTLY costs +4.7pp of
drawdown. The user's description -- *"when VLO was on a major upward trajectory,
I would have toggled it to off"* -- is neither: a trend runs for weeks or months.

So the variable that matters is DURATION OFF. This brackets it with a sustained
rule: a name is off while it trades above its own 50-day moving average.
"""
import json
import statistics

from baseline_check import ROSTER
from book12 import pm_rule_for
from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import WINDOWS, t0
from fresh_opt_cands import aw_params

AI = {'AVGO', 'MU', 'TSM', 'MRVL', 'VRT', 'VST'}
CAP = 6_900_000


def main():
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    d, s, cal = load_all(names=ROSTER, params_override=po)
    W = 50
    nb = {}
    for nm in ('CF', 'VLO'):
        nd = d[nm]
        days = set()
        for i in range(W, len(nd['dts'])):
            ma = sum(nd['C'][i-W:i]) / W
            if nd['C'][i-1] > ma:                    # in an uptrend on the prior close
                days.add(nd['dts'][i])
        nb[nm] = days
        print(f'  {nm}: off on {len(days)} of {len(nd["dts"])-W} mornings '
              f'({len(days)/(len(nd["dts"])-W)*100:.0f}% of the time)')

    print(f'\n  {"arm":36s}{"full":>8s}{"test":>8s}{"maxDD":>8s}{"ret/DD":>8s}'
          f'{"med order":>11s}{"AI $":>8s}{"CF+VLO fills":>14s}')
    for tag, kw in (('all nine ON', {}), ('CF/VLO off while above 50dma', {'no_buy': nb})):
        r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True,
                     excl_fn=pm_rule_for(d, set(ROSTER)), **kw)
        cs = [t['cost'] for t in r['trades']]
        ai = sum(t['cost'] for t in r['trades'] if t['name'] in AI)
        nf = sum(1 for t in r['trades'] if t['name'] in ('CF', 'VLO'))
        eq = r['equity']
        w = []
        for _, lo, hi in WINDOWS:
            ix = [i for i, dd in enumerate(cal) if lo <= dd <= hi]
            w.append((eq[ix[-1]]/eq[ix[0]]-1)*100 if len(ix) > 1 else float('nan'))
        print(f'  {tag:36s}{r["full"]*100:>8.1f}{r["test"]*100:>8.1f}'
              f'{r["maxdd"]*100:>8.1f}{r["full"]/r["maxdd"]:>8.2f}'
              f'{statistics.median(cs)/1e3:>10.0f}k{ai/sum(cs)*100:>7.1f}%{nf:>14d}')
        print(f'  {"":36s}stress: ' + '  '.join(f'{x:+.1f}%' for x in w))
    print('\n  Compare: permanently OFF gave 72.5 / 97.4 / 29.0 / 2.50 / 1041k / 87.1%')


if __name__ == '__main__':
    main()
