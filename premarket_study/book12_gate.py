"""
book12_gate.py — the TWELVE with the pre-market rule on all twelve and the
breadth gate re-stated for twelve names (K>=5 and K>=6).

User, 16 Oct 2026: *"can you try with the 12 +PM+breadth K>=5 or 6. I like the
increase in fill numbers with the 12"* — PARR comes back in. Fill count is the
stated objective, so it leads the table: nine 529/yr, eleven 577, twelve 618.

§3.65 found that carrying §3.23's K>=4 across from nine names to eleven cost
0.33 of ret/DD, and that the PROPORTIONAL K was the right one (4/9 = 0.444, so
K=5 of eleven). On twelve that same proportion is 5.3, which is why the user's
two candidates bracket it: K>=5 is slightly looser than the nine's calibration,
K>=6 slightly tighter.

PARR is run BOTH ways. §3.64 found the $400k per-order cap costs nothing
(full +0.8pp, fills identical) while removing the one liquidity exposure that
could never be measured (PARR's Box file has no volume column, §3.63). Both are
shown so the cap is a choice rather than an assumption.

Usage: BAYES_WORKBOOK=<xlsx> python3 book12_gate.py [--capital 6900000]
"""
import json
import statistics
import sys

from baseline_check import ROSTER
from book12 import NEW, pm_rule_for
from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import t0
from fresh_opt_cands import aw_params
from parallel_book import gate_sets, load_rho, load_vecs
from two_day import x0_vector

PARR_CAP = 400_000
OUT = 'book12_gate.json'


def main():
    cap = 6_900_000
    if '--capital' in sys.argv:
        cap = float(sys.argv[sys.argv.index('--capital') + 1])
    rho, vecs = load_rho(), load_vecs()
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    for n in NEW:
        r = rho.get(n)
        po[n] = params_from_vec(vecs[n] if (r is not None and r >= 0.20 and n in vecs)
                                else x0_vector(1), t0())

    names12 = ROSTER + NEW
    names11 = ROSTER + ['RTX', 'DE']
    d12, s12, c12 = load_all(names=names12, params_override=po)
    d11, s11, c11 = load_all(names=names11, params_override=po)
    d9, s9, c9 = load_all(names=ROSTER, params_override=po)
    pm12 = pm_rule_for(d12, set(names12))
    pm11 = pm_rule_for(d11, set(names11))
    pm9 = pm_rule_for(d9, set(ROSTER))
    g4, _ = gate_sets(names12, 4)
    g5, _ = gate_sets(names12, 5)
    g6, _ = gate_sets(names12, 6)
    g5_11, _ = gate_sets(names11, 5)
    cmap = {'PARR': PARR_CAP}

    out, res = {}, {}
    print(f'capital ${cap/1e6:.2f}m   PARR cap ${PARR_CAP/1e3:.0f}k where applied\n')
    print(f'  {"arm":44s}{"fills/yr":>10s}{"full":>8s}{"train":>8s}{"test":>8s}'
          f'{"maxDD":>8s}{"ret/DD":>8s}')

    def row(tag, data, sl, cal, **kw):
        r = simulate(data, sl, cal, capital=cap, collect_trades=True, **kw)
        y = len(cal)/252
        rd = r['full']/r['maxdd'] if r['maxdd'] else float('nan')
        print(f'  {tag:44s}{r["fills"]/y:>10.0f}{r["full"]*100:>8.1f}'
              f'{r["train"]*100:>8.1f}{r["test"]*100:>8.1f}{r["maxdd"]*100:>8.1f}'
              f'{rd:>8.2f}', flush=True)
        out[tag] = dict(full=r['full'], train=r['train'], test=r['test'],
                        maxdd=r['maxdd'], fills=r['fills'], per_yr=r['fills']/y,
                        ret_dd=rd)
        res[tag] = r
        return out[tag]

    base = row('NINE, live config (baseline)', d9, s9, c9, mode='pooled', excl_fn=pm9)
    e11 = row('ELEVEN, PM all + K>=5 of 11 (§3.65 pick)', d11, s11, c11,
              mode='pooled', excl_fn=pm11, no_buy=g5_11)
    print()
    row('TWELVE, PM all, no breadth gate', d12, s12, c12, mode='pooled', excl_fn=pm12)
    row('TWELVE, PM all + K>=4 of 12', d12, s12, c12, mode='pooled',
        excl_fn=pm12, no_buy=g4)
    u5 = row('TWELVE, PM all + K>=5 of 12', d12, s12, c12, mode='pooled',
             excl_fn=pm12, no_buy=g5)
    u6 = row('TWELVE, PM all + K>=6 of 12', d12, s12, c12, mode='pooled',
             excl_fn=pm12, no_buy=g6)
    print()
    row('TWELVE, PM all, no gate, PARR<=$400k', d12, s12, c12, mode='pooled',
        excl_fn=pm12, name_cap=cmap)
    c5 = row('TWELVE, PM all + K>=5 of 12, PARR<=$400k', d12, s12, c12, mode='pooled',
             excl_fn=pm12, no_buy=g5, name_cap=cmap)
    c6 = row('TWELVE, PM all + K>=6 of 12, PARR<=$400k', d12, s12, c12, mode='pooled',
             excl_fn=pm12, no_buy=g6, name_cap=cmap)

    print(f'\n  cost of the PARR cap at K>=5: full {(c5["full"]-u5["full"])*100:+.1f}pp'
          f'   test {(c5["test"]-u5["test"])*100:+.1f}pp'
          f'   maxDD {(c5["maxdd"]-u5["maxdd"])*100:+.1f}pp')
    print(f'  cost of the PARR cap at K>=6: full {(c6["full"]-u6["full"])*100:+.1f}pp'
          f'   test {(c6["test"]-u6["test"])*100:+.1f}pp'
          f'   maxDD {(c6["maxdd"]-u6["maxdd"])*100:+.1f}pp')

    pick = max((c5, c6, u5, u6), key=lambda x: x['ret_dd'])
    for tag, v in out.items():
        if v is pick:
            print(f'\n  best twelve by ret/DD: {tag}')
            print(f'    vs the NINE   : fills/yr {v["per_yr"]:.0f} vs {base["per_yr"]:.0f}'
                  f'   full {(v["full"]-base["full"])*100:+.1f}pp'
                  f'   maxDD {(v["maxdd"]-base["maxdd"])*100:+.1f}pp'
                  f'   ret/DD {v["ret_dd"]:.2f} vs {base["ret_dd"]:.2f}')
            print(f'    vs the ELEVEN : fills/yr {v["per_yr"]:.0f} vs {e11["per_yr"]:.0f}'
                  f'   full {(v["full"]-e11["full"])*100:+.1f}pp'
                  f'   maxDD {(v["maxdd"]-e11["maxdd"])*100:+.1f}pp'
                  f'   ret/DD {v["ret_dd"]:.2f} vs {e11["ret_dd"]:.2f}')
            best_tag = tag
            break

    # ---- what the extra fills are actually worth
    print(f'\n  PER-NAME on "{best_tag}"\n')
    print(f'    {"name":6s}{"fills":>7s}{"P&L $":>11s}{"share":>8s}{"win%":>7s}'
          f'{"med $":>9s}{"max $":>9s}')
    by = {}
    for t in res[best_tag]['trades']:
        by.setdefault(t['name'], []).append(t)
    tot = sum(sum(x['pnl'] for x in v) for v in by.values())
    for n in sorted(by, key=lambda k: -sum(x['pnl'] for x in by[k])):
        v = by[n]
        pnl = sum(x['pnl'] for x in v)
        cs = [x['cost'] for x in v]
        print(f'    {n:6s}{len(v):>7d}{pnl/1e3:>10.0f}k{pnl/tot*100:>7.1f}%'
              f'{sum(1 for x in v if x["pnl"] > 0)/len(v)*100:>6.0f}%'
              f'{statistics.median(cs)/1e6:>8.2f}m{max(cs)/1e6:>8.2f}m')
        out.setdefault('per_name', {})[n] = dict(
            fills=len(v), pnl=pnl, share=pnl/tot,
            win=sum(1 for x in v if x['pnl'] > 0)/len(v),
            median=statistics.median(cs), mx=max(cs))
    print(f'    {"TOTAL":6s}{sum(len(v) for v in by.values()):>7d}{tot/1e3:>10.0f}k')

    json.dump(out, open(OUT, 'w'), indent=1)
    print(f'\nwrote {OUT}\nDONE', flush=True)


if __name__ == '__main__':
    main()
