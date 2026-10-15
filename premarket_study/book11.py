"""
book11.py — the ELEVEN-name book: the nine plus RTX and DE. PARR dropped.

User, 15 Oct 2026: *"drop PARR and run the eleven"*. §3.64's control arm already
showed the eleven beating the $400k-capped twelve on full return, train and
ret/DD; this is the full run — overlay variants, pooling uplift, per-name
contribution and the half-sample split — so the eleven can be judged as a
deployment candidate rather than as somebody else's control.

Why PARR went: capped at $400k it was pinned to a fixed size on all 93 orders
(§3.64), it runs on a NEUTRAL vector because it is unfittable (rho −0.49, §3.61),
and its liquidity could never be measured at all (no volume column, §3.61/§3.63).
RTX and DE keep their fitted vectors (rho +0.36, +0.38).

Overlays tested rather than assumed: §3.62 found the PM rule belongs on ALL
twelve, not on the nine only, because in a pooled book a suppressed entry frees
capital for everyone else. That should hold at eleven, and is re-checked here.
The breadth gate's K=4 was calibrated on NINE names (§3.23), so applying it to
eleven needs K re-stated -- both the nine-only set and a proportional K=5 of
eleven are run.

Usage: BAYES_WORKBOOK=<xlsx> python3 book11.py [--capital 6900000]
"""
import json
import statistics
import sys

from baseline_check import ROSTER
from book12 import pm_rule_for
from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import t0
from fresh_opt_cands import aw_params
from parallel_book import gate_sets, load_rho, load_vecs
from two_day import x0_vector

ADDED = ['RTX', 'DE']
OUT = 'book11.json'


def main():
    cap = 6_900_000
    if '--capital' in sys.argv:
        cap = float(sys.argv[sys.argv.index('--capital') + 1])
    rho, vecs = load_rho(), load_vecs()
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    basis = {}
    for n in ADDED:
        r = rho.get(n)
        if r is not None and r >= 0.20 and n in vecs:
            po[n] = params_from_vec(vecs[n], t0()); basis[n] = f'fitted ({r:+.2f})'
        else:
            po[n] = params_from_vec(x0_vector(1), t0()); basis[n] = f'NEUTRAL ({r:+.2f})'
    print('added:', ', '.join(f'{n} {basis[n]}' for n in ADDED))
    print(f'capital ${cap/1e6:.2f}m\n')

    names11 = ROSTER + ADDED
    d11, s11, c11 = load_all(names=names11, params_override=po)
    d9, s9, c9 = load_all(names=ROSTER, params_override=po)
    pm_all = pm_rule_for(d11, set(names11))
    pm_9 = pm_rule_for(d11, set(ROSTER))
    pm9_9 = pm_rule_for(d9, set(ROSTER))
    nb9, _ = gate_sets(ROSTER, 4)                  # §3.23 as calibrated, nine names
    nb11, _ = gate_sets(names11, 5)                # proportional K on eleven

    out, res = {}, {}
    print(f'  {"arm":42s}{"full":>8s}{"train":>8s}{"test":>8s}{"maxDD":>8s}'
          f'{"fills":>8s}{"/yr":>7s}{"ret/DD":>8s}')

    def row(tag, data, sl, cal, **kw):
        r = simulate(data, sl, cal, capital=cap, collect_trades=True, **kw)
        y = len(cal)/252
        rd = r['full']/r['maxdd'] if r['maxdd'] else float('nan')
        print(f'  {tag:42s}{r["full"]*100:>8.1f}{r["train"]*100:>8.1f}{r["test"]*100:>8.1f}'
              f'{r["maxdd"]*100:>8.1f}{r["fills"]:>8d}{r["fills"]/y:>7.0f}{rd:>8.2f}',
              flush=True)
        out[tag] = dict(full=r['full'], train=r['train'], test=r['test'],
                        maxdd=r['maxdd'], fills=r['fills'], per_yr=r['fills']/y,
                        ret_dd=rd)
        res[tag] = r
        return out[tag]

    base = row('NINE, live config (baseline)', d9, s9, c9, mode='pooled', excl_fn=pm9_9)
    row('ELEVEN, no overlays', d11, s11, c11, mode='pooled')
    row('ELEVEN, PM on the NINE only', d11, s11, c11, mode='pooled', excl_fn=pm_9)
    best = row('ELEVEN, PM on all 11', d11, s11, c11, mode='pooled', excl_fn=pm_all)
    g9 = row('ELEVEN, PM all + breadth K>=4 on NINE', d11, s11, c11, mode='pooled',
             excl_fn=pm_all, no_buy=nb9)
    g11 = row('ELEVEN, PM all + breadth K>=5 on ELEVEN', d11, s11, c11, mode='pooled',
              excl_fn=pm_all, no_buy=nb11)
    cp = row('ELEVEN captive (for uplift)', d11, s11, c11, mode='captive', excl_fn=pm_all)

    print(f'\n  vs the NINE baseline  : full {(best["full"]-base["full"])*100:+.1f}pp'
          f'   test {(best["test"]-base["test"])*100:+.1f}pp'
          f'   maxDD {(best["maxdd"]-base["maxdd"])*100:+.1f}pp'
          f'   ret/DD {best["ret_dd"]:.2f} vs {base["ret_dd"]:.2f}')
    print(f'  with the breadth gate : full {(g9["full"]-base["full"])*100:+.1f}pp'
          f'   test {(g9["test"]-base["test"])*100:+.1f}pp'
          f'   maxDD {(g9["maxdd"]-base["maxdd"])*100:+.1f}pp'
          f'   ret/DD {g9["ret_dd"]:.2f} vs {base["ret_dd"]:.2f}')
    print(f'  pooling uplift        : full {(best["full"]-cp["full"])*100:+.1f}pp'
          f'   test {(best["test"]-cp["test"])*100:+.1f}pp')

    # ---- per-name contribution and order sizes on the chosen arm
    print(f'\n  PER-NAME, "ELEVEN, PM on all 11"\n')
    print(f'    {"name":6s}{"fills":>7s}{"P&L $":>11s}{"share":>8s}{"win%":>7s}'
          f'{"stops":>7s}{"med $":>9s}{"max $":>9s}')
    by = {}
    for t in res['ELEVEN, PM on all 11']['trades']:
        by.setdefault(t['name'], []).append(t)
    tot = sum(sum(x['pnl'] for x in v) for v in by.values())
    for n in sorted(by, key=lambda k: -sum(x['pnl'] for x in by[k])):
        v = by[n]
        pnl = sum(x['pnl'] for x in v)
        cs = [x['cost'] for x in v]
        st = sum(1 for x in v if x['stopped'])
        wins = sum(1 for x in v if x['pnl'] > 0)
        print(f'    {n:6s}{len(v):>7d}{pnl/1e3:>10.0f}k{pnl/tot*100:>7.1f}%'
              f'{wins/len(v)*100:>6.0f}%{st:>7d}{statistics.median(cs)/1e6:>8.2f}m'
              f'{max(cs)/1e6:>8.2f}m')
        out.setdefault('per_name', {})[n] = dict(
            fills=len(v), pnl=pnl, share=pnl/tot, win=wins/len(v), stops=st,
            median=statistics.median(cs), mx=max(cs))
    print(f'    {"TOTAL":6s}{sum(len(v) for v in by.values()):>7d}{tot/1e3:>10.0f}k')

    json.dump(out, open(OUT, 'w'), indent=1)
    print(f'\nwrote {OUT}\nDONE', flush=True)


if __name__ == '__main__':
    main()
