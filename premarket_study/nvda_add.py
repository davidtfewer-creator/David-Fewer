"""
nvda_add.py — NVDA as a twelfth name alongside the nine plus RTX and DE.

User, 16 Oct 2026: *"I've done well out of holding NVDA and some of the early
iterations of the trading idea were underpinned by NVDA. If I did decide to sell
it now, I would like to consider adding it as a 12th name to the book. How
profit dilutive would this be?"* — the sentimental framing is the user's own and
is noted; the numbers below are indifferent to it.

Two measured facts frame the question before any simulation:

  FOR   NVDA's train->test rank correlation is rho = +0.41, the HIGHEST of any
        name screened (§3.59 family; RTX +0.36, DE +0.38, PARR -0.49). Fitting
        NVDA earns more than fitting anything else in the universe.
  AGAINST  G1 puts it at AI beta 0.727 and correlation 0.733 to the book's own
        AI factor — the most correlated candidate yet considered, into a book
        that is already AVGO, MU, TSM, MRVL, VRT and VST.

So this is not a dilution question so much as a concentration question, and the
drawdown column matters more than the return column.

Usage: BAYES_WORKBOOK=<xlsx> python3 nvda_add.py [--capital 6900000]
"""
import json
import statistics
import sys

from baseline_check import ROSTER
from book12 import pm_rule_for
from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import WINDOWS, t0
from fresh_opt_cands import aw_params
from parallel_book import load_rho, load_vecs
from two_day import x0_vector

OUT = 'nvda_add.json'
AI = {'AVGO', 'MU', 'TSM', 'MRVL', 'VRT', 'VST', 'NVDA'}


def main():
    cap = 6_900_000
    if '--capital' in sys.argv:
        cap = float(sys.argv[sys.argv.index('--capital') + 1])
    rho, vecs = load_rho(), load_vecs()
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    for n in ('RTX', 'DE', 'NVDA'):
        r = rho.get(n)
        po[n] = params_from_vec(vecs[n] if (r is not None and r >= 0.20 and n in vecs)
                                else x0_vector(1), t0())
        print(f'  {n}: rho {r:+.2f} -> {"fitted" if r >= 0.20 else "NEUTRAL"} vector')
    print(f'  capital ${cap/1e6:.2f}m\n')

    n11 = ROSTER + ['RTX', 'DE']
    n12 = n11 + ['NVDA']
    out, res = {}, {}
    print(f'  {"arm":40s}{"full":>8s}{"train":>8s}{"test":>8s}{"maxDD":>8s}'
          f'{"ret/DD":>8s}{"fills/yr":>10s}')

    def row(tag, names, **kw):
        d, s, cal = load_all(names=names, params_override=po)
        r = simulate(d, s, cal, capital=cap, mode='pooled', collect_trades=True,
                     excl_fn=pm_rule_for(d, set(names)), **kw)
        y = len(cal)/252
        rd = r['full']/r['maxdd'] if r['maxdd'] else float('nan')
        print(f'  {tag:40s}{r["full"]*100:>8.1f}{r["train"]*100:>8.1f}{r["test"]*100:>8.1f}'
              f'{r["maxdd"]*100:>8.1f}{rd:>8.2f}{r["fills"]/y:>10.0f}', flush=True)
        out[tag] = dict(full=r['full'], train=r['train'], test=r['test'],
                        maxdd=r['maxdd'], ret_dd=rd, per_yr=r['fills']/y)
        res[tag] = (r, cal)
        return out[tag]

    base = row('ELEVEN (nine + RTX + DE)', n11)
    nv = row('TWELVE (+ NVDA)', n12)
    cp = row('TWELVE (+ NVDA) captive', n12, mode_override=None) if False else None
    d, s, cal = load_all(names=n12, params_override=po)
    rcap = simulate(d, s, cal, capital=cap, mode='captive', collect_trades=True,
                    excl_fn=pm_rule_for(d, set(n12)))
    print(f'  {"TWELVE (+ NVDA) captive":40s}{rcap["full"]*100:>8.1f}'
          f'{rcap["train"]*100:>8.1f}{rcap["test"]*100:>8.1f}{rcap["maxdd"]*100:>8.1f}'
          f'{rcap["full"]/rcap["maxdd"]:>8.2f}{rcap["fills"]/(len(cal)/252):>10.0f}')

    print(f'\n  NVDA adds: full {(nv["full"]-base["full"])*100:+.1f}pp   '
          f'test {(nv["test"]-base["test"])*100:+.1f}pp   '
          f'maxDD {(nv["maxdd"]-base["maxdd"])*100:+.1f}pp   '
          f'ret/DD {nv["ret_dd"]:.2f} vs {base["ret_dd"]:.2f}')
    print(f'  pooling uplift with NVDA in: {(nv["full"]-rcap["full"])*100:+.1f}pp full')

    # ---- per-name, and what share NVDA takes
    print(f'\n  PER-NAME in the twelve\n')
    print(f'    {"name":6s}{"fills":>7s}{"P&L $":>11s}{"share":>8s}{"win%":>7s}{"med $":>9s}')
    r12 = res['TWELVE (+ NVDA)'][0]
    by = {}
    for t in r12['trades']:
        by.setdefault(t['name'], []).append(t)
    tot = sum(sum(x['pnl'] for x in v) for v in by.values())
    ai_pnl = 0.0
    for n in sorted(by, key=lambda k: -sum(x['pnl'] for x in by[k])):
        v = by[n]; pnl = sum(x['pnl'] for x in v); cs = [x['cost'] for x in v]
        if n in AI:
            ai_pnl += pnl
        print(f'    {n:6s}{len(v):>7d}{pnl/1e3:>10.0f}k{pnl/tot*100:>7.1f}%'
              f'{sum(1 for x in v if x["pnl"]>0)/len(v)*100:>6.0f}%'
              f'{statistics.median(cs)/1e6:>8.2f}m')
        out.setdefault('per_name', {})[n] = dict(fills=len(v), pnl=pnl, share=pnl/tot)
    print(f'    {"TOTAL":6s}{sum(len(v) for v in by.values()):>7d}{tot/1e3:>10.0f}k')

    # AI concentration, both books
    r11 = res['ELEVEN (nine + RTX + DE)'][0]
    by11 = {}
    for t in r11['trades']:
        by11[t['name']] = by11.get(t['name'], 0.0) + t['pnl']
    tot11 = sum(by11.values())
    ai11 = sum(v for k, v in by11.items() if k in AI)
    print(f'\n  AI-RELATED SHARE OF BOOK P&L')
    print(f'    eleven : {ai11/tot11*100:.1f}%')
    print(f'    twelve : {ai_pnl/tot*100:.1f}%   ({(ai_pnl/tot-ai11/tot11)*100:+.1f}pp)')
    out['ai_share'] = dict(eleven=ai11/tot11, twelve=ai_pnl/tot)

    # ---- stress windows: where concentration bites
    print(f'\n  STRESS WINDOWS\n')
    print(f'    {"arm":26s}' + ''.join(f'{w[0][:20]:>22s}' for w in WINDOWS))
    for tag in ('ELEVEN (nine + RTX + DE)', 'TWELVE (+ NVDA)'):
        r, cal = res[tag]
        eq = r['equity']
        vals = []
        for _, lo, hi in WINDOWS:
            ix = [i for i, dd in enumerate(cal) if lo <= dd <= hi]
            vals.append((eq[ix[-1]]/eq[ix[0]]-1)*100 if len(ix) > 1 else float('nan'))
        print(f'    {tag:26s}' + ''.join(f'{v:>21.1f}%' for v in vals))
        out.setdefault('stress', {})[tag] = vals

    json.dump(out, open(OUT, 'w'), indent=1, default=str)
    print(f'\nwrote {OUT}\nDONE', flush=True)


if __name__ == '__main__':
    main()
