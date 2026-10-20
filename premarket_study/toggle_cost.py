"""
toggle_cost.py — what does switching the diversifiers OFF cost in a drawdown?

User, 20 Oct 2026: *"I sometimes turned off stocks such as CF or VLO as I knew
they wouldn't fill. I didn't fully appreciate that holding capital for these
stocks was keeping the capital away from the AI stocks"* and *"when VLO was on
a major upward trajectory, I would have toggled it to off knowing trades
wouldn't fill."*

The toggle history cannot be recovered from a workbook snapshot, so this
BRACKETS the effect rather than measuring the actual path: the nine-name book
with CF and VLO always on, against the same book with them permanently off.
Reality sat somewhere between.

The mechanism being tested: the pooled allocation splits the morning pot across
sleeves that are free AND bidding. A sleeve that bids and does not fill still
reserved its slice that morning. Removing it enlarges everyone else's order --
and because this model only fills where prices FALL, the names left on are
disproportionately the ones going down.
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

AI = {'AVGO', 'MU', 'TSM', 'MRVL', 'VRT', 'VST'}
CAP = 6_900_000


def main():
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    arms = {'NINE — CF and VLO ON (as modelled)': ROSTER,
            'SEVEN — CF and VLO OFF (toggle extreme)':
                [n for n in ROSTER if n not in ('CF', 'VLO')]}
    out, res = {}, {}
    print(f'capital ${CAP/1e6:.2f}m\n')
    print(f'  {"arm":42s}{"full":>8s}{"test":>8s}{"maxDD":>8s}{"ret/DD":>8s}'
          f'{"med order":>11s}{"AI $ share":>12s}')
    for tag, names in arms.items():
        d, s, cal = load_all(names=names, params_override=po)
        r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True,
                     excl_fn=pm_rule_for(d, set(names)))
        costs = [t['cost'] for t in r['trades']]
        ai = sum(t['cost'] for t in r['trades'] if t['name'] in AI)
        tot = sum(costs)
        rd = r['full'] / r['maxdd']
        print(f'  {tag:42s}{r["full"]*100:>8.1f}{r["test"]*100:>8.1f}'
              f'{r["maxdd"]*100:>8.1f}{rd:>8.2f}'
              f'{statistics.median(costs)/1e3:>10.0f}k{ai/tot*100:>11.1f}%')
        out[tag] = dict(full=r['full'], test=r['test'], maxdd=r['maxdd'], ret_dd=rd,
                        med_order=statistics.median(costs), ai_share=ai/tot,
                        n=len(costs))
        res[tag] = (r, cal)

    a, b = list(out.values())
    print(f'\n  switching them off: full {(b["full"]-a["full"])*100:+.1f}pp   '
          f'test {(b["test"]-a["test"])*100:+.1f}pp   '
          f'maxDD {(b["maxdd"]-a["maxdd"])*100:+.1f}pp')
    print(f'  median order {a["med_order"]/1e3:.0f}k -> {b["med_order"]/1e3:.0f}k '
          f'({b["med_order"]/a["med_order"]-1:+.0%})')
    print(f'  AI share of deployed capital {a["ai_share"]*100:.1f}% -> '
          f'{b["ai_share"]*100:.1f}% ({(b["ai_share"]-a["ai_share"])*100:+.1f}pp)')

    print(f'\n  STRESS WINDOWS — where the concentration shows up\n')
    print(f'    {"arm":42s}' + ''.join(f'{w[0][:18]:>20s}' for w in WINDOWS))
    for tag in arms:
        r, cal = res[tag]
        eq = r['equity']
        v = []
        for _, lo, hi in WINDOWS:
            ix = [i for i, dd in enumerate(cal) if lo <= dd <= hi]
            v.append((eq[ix[-1]] / eq[ix[0]] - 1) * 100 if len(ix) > 1 else float('nan'))
        print(f'    {tag:42s}' + ''.join(f'{x:>19.1f}%' for x in v))

    print(f'\n=== THE TOGGLE AS ACTUALLY USED ===\n')
    rs = selective()
    out['SELECTIVE'] = dict(full=rs['full'], test=rs['test'], maxdd=rs['maxdd'])
    json.dump(out, open('toggle_cost.json', 'w'), indent=1)
    print('\nwrote toggle_cost.json')




def selective():
    """The toggle AS ACTUALLY USED: switch CF and VLO off only on mornings they
    would not have filled. Perfect foresight stands in for the user's judgement,
    which is generous to the toggle. Every CF/VLO trade is preserved -- the only
    thing removed is the capital those sleeves reserved on no-fill mornings."""
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    d, s, cal = load_all(names=ROSTER, params_override=po)
    nb = {}
    for nm in ('CF', 'VLO'):
        nd = d[nm]
        days = set()
        for i in range(1, len(nd['dts'])):
            bids = [b for b in (nd['X'][i], nd['AM'][i]) if b is not None]
            if bids and nd['L'][i] > max(bids) + 1e-12:
                days.add(nd['dts'][i])          # neither sleeve could have filled
        nb[nm] = days
        print(f'  {nm}: off on {len(days)} of {len(nd["dts"])-1} mornings '
              f'({len(days)/(len(nd["dts"])-1)*100:.0f}%)')
    r = simulate(d, s, cal, capital=CAP, mode='pooled', collect_trades=True,
                 excl_fn=pm_rule_for(d, set(ROSTER)), no_buy=nb)
    costs = [t['cost'] for t in r['trades']]
    ai = sum(t['cost'] for t in r['trades'] if t['name'] in AI)
    cfvlo = sum(1 for t in r['trades'] if t['name'] in ('CF', 'VLO'))
    print(f'\n  {"SELECTIVE toggle (what was actually done)":42s}'
          f'{r["full"]*100:>8.1f}{r["test"]*100:>8.1f}{r["maxdd"]*100:>8.1f}'
          f'{r["full"]/r["maxdd"]:>8.2f}{statistics.median(costs)/1e3:>10.0f}k'
          f'{ai/sum(costs)*100:>11.1f}%')
    print(f'  CF+VLO trades retained: {cfvlo}')
    eq, out = r['equity'], []
    for _, lo, hi in WINDOWS:
        ix = [i for i, dd in enumerate(cal) if lo <= dd <= hi]
        out.append((eq[ix[-1]]/eq[ix[0]]-1)*100 if len(ix) > 1 else float('nan'))
    print(f'  stress windows: ' + '  '.join(f'{x:+.1f}%' for x in out))
    return r


if __name__ == '__main__':
    main()
