"""
book12_nvda.py — the twelve-name book as the user has now specified it:
the nine, plus RTX, DE and NVDA. PARR is out.

User, 16 Oct 2026: *"add NVDA to the book and re-run the 12 stock sim"*.

Roster history, so the composition is traceable:
  nine            TSM VRT VST AVGO MU GM VLO CF MRVL      (live)
  +RTX +DE        §3.65, fitted vectors, rho +0.36 / +0.38
  +PARR           §3.62/§3.64 — dropped: neutral vector (rho -0.49), capped at
                  $400k it was pinned on all 93 orders and contributed 2.1%
  +NVDA           §3.69 — rho +0.41, the highest in the universe; relieves the
                  liquidity ceiling rather than consuming it

Overlays: the pre-market rule goes on ALL twelve (§3.62 found it transports and
§3.65 confirmed it at eleven). The breadth gate is run but NOT recommended —
§3.66 found it fires 0 times in the test half, so every figure it produces is
in-sample.

Writes book12_nvda.json plus deployed_book12.json, a roster-and-vector file the
live workbook can be rebuilt from.

Usage: BAYES_WORKBOOK=<xlsx> python3 book12_nvda.py [--capital 6900000]
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
from parallel_book import gate_sets, load_rho, load_vecs
from two_day import x0_vector

ADDED = ['RTX', 'DE', 'NVDA']
OUT, CFG = 'book12_nvda.json', 'deployed_book12.json'
AI = {'AVGO', 'MU', 'TSM', 'MRVL', 'VRT', 'VST', 'NVDA'}


def main():
    cap = 6_900_000
    if '--capital' in sys.argv:
        cap = float(sys.argv[sys.argv.index('--capital') + 1])
    rho, vecs = load_rho(), load_vecs()
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    basis = {}
    for n in ADDED + ['PARR']:
        r = rho.get(n)
        use_fit = r is not None and r >= 0.20 and n in vecs
        po[n] = params_from_vec(vecs[n] if use_fit else x0_vector(1), t0())
        basis[n] = f'{"fitted" if use_fit else "NEUTRAL"} (rho {r:+.2f})'

    names12 = ROSTER + ADDED
    names11 = ROSTER + ['RTX', 'DE']
    old12 = ROSTER + ['PARR', 'RTX', 'DE']
    print('TWELVE =', ' '.join(names12))
    for n in ADDED:
        print(f'  {n:5s} {basis[n]}')
    print(f'  capital ${cap/1e6:.2f}m\n')

    out, res = {}, {}
    print(f'  {"arm":42s}{"full":>8s}{"train":>8s}{"test":>8s}{"maxDD":>8s}'
          f'{"ret/DD":>8s}{"fills/yr":>10s}')

    def row(tag, names, mode='pooled', pm=True, no_buy=None, cmap=None):
        d, s, cal = load_all(names=names, params_override=po)
        kw = {}
        if pm:
            kw['excl_fn'] = pm_rule_for(d, set(names))
        if no_buy is not None:
            kw['no_buy'] = no_buy
        if cmap:
            kw['name_cap'] = cmap
        r = simulate(d, s, cal, capital=cap, mode=mode, collect_trades=True, **kw)
        y = len(cal)/252
        rd = r['full']/r['maxdd'] if r['maxdd'] else float('nan')
        print(f'  {tag:42s}{r["full"]*100:>8.1f}{r["train"]*100:>8.1f}{r["test"]*100:>8.1f}'
              f'{r["maxdd"]*100:>8.1f}{rd:>8.2f}{r["fills"]/y:>10.0f}', flush=True)
        out[tag] = dict(full=r['full'], train=r['train'], test=r['test'], maxdd=r['maxdd'],
                        ret_dd=rd, fills=r['fills'], per_yr=r['fills']/y)
        res[tag] = (r, cal)
        return out[tag]

    print('  --- what it replaces')
    nine = row('NINE, live config', ROSTER)
    el = row('ELEVEN (nine + RTX + DE)', names11)
    row('TWELVE with PARR, capped $400k', old12, cmap={'PARR': 400_000})
    print('  --- the new twelve')
    row('TWELVE + NVDA, no overlays', names12, pm=False)
    pick = row('TWELVE + NVDA, PM on all 12', names12)
    g6, _ = gate_sets(names12, 6)
    row('TWELVE + NVDA, PM + breadth K>=6 *', names12, no_buy=g6)
    capt = row('TWELVE + NVDA, captive', names12, mode='captive')

    print('\n  * the breadth gate fires 0 times in the test half (§3.66) — in-sample only.\n')
    print(f'  vs NINE   : full {(pick["full"]-nine["full"])*100:+.1f}pp   '
          f'test {(pick["test"]-nine["test"])*100:+.1f}pp   '
          f'maxDD {(pick["maxdd"]-nine["maxdd"])*100:+.1f}pp   '
          f'fills {pick["per_yr"]-nine["per_yr"]:+.0f}/yr')
    print(f'  vs ELEVEN : full {(pick["full"]-el["full"])*100:+.1f}pp   '
          f'test {(pick["test"]-el["test"])*100:+.1f}pp   '
          f'maxDD {(pick["maxdd"]-el["maxdd"])*100:+.1f}pp   '
          f'fills {pick["per_yr"]-el["per_yr"]:+.0f}/yr')
    print(f'  pooling uplift : {(pick["full"]-capt["full"])*100:+.1f}pp full   '
          f'{(pick["test"]-capt["test"])*100:+.1f}pp test')

    # ---- per-name
    r12, cal12 = res['TWELVE + NVDA, PM on all 12']
    print(f'\n  PER-NAME\n')
    print(f'    {"name":6s}{"fills":>7s}{"/yr":>7s}{"P&L $":>11s}{"share":>8s}{"win%":>7s}'
          f'{"med $":>9s}{"max $":>9s}')
    by = {}
    for t in r12['trades']:
        by.setdefault(t['name'], []).append(t)
    y = len(cal12)/252
    tot = sum(sum(x['pnl'] for x in v) for v in by.values())
    ai = 0.0
    for n in sorted(by, key=lambda k: -sum(x['pnl'] for x in by[k])):
        v = by[n]; pnl = sum(x['pnl'] for x in v); cs = [x['cost'] for x in v]
        if n in AI:
            ai += pnl
        print(f'    {n:6s}{len(v):>7d}{len(v)/y:>7.0f}{pnl/1e3:>10.0f}k{pnl/tot*100:>7.1f}%'
              f'{sum(1 for x in v if x["pnl"]>0)/len(v)*100:>6.0f}%'
              f'{statistics.median(cs)/1e6:>8.2f}m{max(cs)/1e6:>8.2f}m')
        out.setdefault('per_name', {})[n] = dict(
            fills=len(v), per_yr=len(v)/y, pnl=pnl, share=pnl/tot,
            win=sum(1 for x in v if x['pnl'] > 0)/len(v),
            median=statistics.median(cs), mx=max(cs))
    print(f'    {"TOTAL":6s}{sum(len(v) for v in by.values()):>7d}{sum(len(v) for v in by.values())/y:>7.0f}'
          f'{tot/1e3:>10.0f}k')
    print(f'\n    AI-related share of P&L: {ai/tot*100:.1f}%')
    out['ai_share'] = ai/tot

    # ---- stress
    print(f'\n  STRESS WINDOWS\n')
    print(f'    {"arm":34s}' + ''.join(f'{w[0][:20]:>22s}' for w in WINDOWS))
    for tag in ('NINE, live config', 'ELEVEN (nine + RTX + DE)', 'TWELVE + NVDA, PM on all 12'):
        r, cal = res[tag]; eq = r['equity']; vals = []
        for _, lo, hi in WINDOWS:
            ix = [i for i, dd in enumerate(cal) if lo <= dd <= hi]
            vals.append((eq[ix[-1]]/eq[ix[0]]-1)*100 if len(ix) > 1 else float('nan'))
        print(f'    {tag:34s}' + ''.join(f'{v:>21.1f}%' for v in vals))
        out.setdefault('stress', {})[tag] = vals

    # ---- deployable config
    d12, s12, _ = load_all(names=names12, params_override=po)
    cfg = {'_note': ('The twelve-name book as specified 16 Oct 2026: the nine plus RTX, DE and '
                     'NVDA. PARR removed (§3.64/§3.69). Overlay: the §3.16 pre-market rule on '
                     'ALL twelve, 09:00 cut, 4% threshold. NO breadth gate — §3.66 found it '
                     'fires 0 times in the test half. Stop: 50 calendar days. Pooled '
                     'allocation across 24 sleeves.'),
           'roster': names12, 'capital': cap,
           'overlays': {'pm_rule': {'names': names12, 'cut': '09:00', 'thr': 0.04},
                        'breadth_gate': None, 'stop_days': 50},
           'vector_basis': {n: basis.get(n, 'live workbook / reference') for n in names12},
           'params': {}}
    for n in names12:
        p = d12[n]['p']
        cfg['params'][n] = {k: getattr(p, k) for k in
                            ('lam', 'phi_L', 'psi', 'k', 'premium', 'peak_cap',
                             'ou_buf_k', 'ou_prem', 'ou_cap', 'ou_W')}
    json.dump(cfg, open(CFG, 'w'), indent=1, default=float)
    json.dump(out, open(OUT, 'w'), indent=1, default=str)
    print(f'\nwrote {OUT} and {CFG}\nDONE', flush=True)


if __name__ == '__main__':
    main()
