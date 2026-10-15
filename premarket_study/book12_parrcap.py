"""
book12_parrcap.py — the twelve-name book with a hard $400k-per-order cap on PARR.

User, 15 Oct 2026: *"I think we're going into too much detail here. CF has very
few fills over the year anyway. I've never had an issue with filling VLO in
practice. Can you run the 12 stock model and cap PARR at $400k"* — so the
cap_frac sweep of §3.62, which throttled EVERY name to fix one, is set aside.
$400k is also looser than the $0.29m §3.62 estimated for PARR, and that estimate
was built on a borrowed 1% threshold the participation study (§3.63) then
declined to endorse.

The cap is per ORDER. PARR has two sleeves (Bayes, OU), so a day on which both
fill places $800k against one name's book -- the per-NAME daily total is reported
alongside, since that is what the at-bid volume actually has to absorb.

Capped capital is NOT left idle: the remainder re-divides over the other free
sleeves that morning (book_sim name_cap), which is what the live allocation does.

Usage: BAYES_WORKBOOK=<xlsx> python3 book12_parrcap.py [--capital 6900000]
"""
import collections
import json
import statistics
import sys

from baseline_check import ROSTER
from book12 import NEW, GATE_K, pm_rule_for
from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import t0
from fresh_opt_cands import aw_params
from parallel_book import gate_sets, load_rho, load_vecs
from two_day import x0_vector

PARR_CAP = 400_000
OUT = 'book12_parrcap.json'


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
    d12, s12, c12 = load_all(names=names12, params_override=po)
    d9, s9, c9 = load_all(names=ROSTER, params_override=po)
    pm_all = pm_rule_for(d12, set(names12))
    pm9_9 = pm_rule_for(d9, set(ROSTER))
    nb9, _ = gate_sets(ROSTER, GATE_K)
    cap_map = {'PARR': PARR_CAP}

    out, res = {}, {}
    print(f'capital ${cap/1e6:.2f}m   PARR cap ${PARR_CAP/1e3:.0f}k per order\n')
    print(f'  {"arm":40s}{"full":>8s}{"train":>8s}{"test":>8s}{"maxDD":>8s}'
          f'{"fills":>8s}{"/yr":>7s}{"ret/DD":>8s}')

    def row(tag, data, sl, cal, **kw):
        r = simulate(data, sl, cal, capital=cap, collect_trades=True, **kw)
        y = len(cal)/252
        rd = r['full']/r['maxdd'] if r['maxdd'] else float('nan')
        print(f'  {tag:40s}{r["full"]*100:>8.1f}{r["train"]*100:>8.1f}{r["test"]*100:>8.1f}'
              f'{r["maxdd"]*100:>8.1f}{r["fills"]:>8d}{r["fills"]/y:>7.0f}{rd:>8.2f}', flush=True)
        out[tag] = dict(full=r['full'], train=r['train'], test=r['test'],
                        maxdd=r['maxdd'], fills=r['fills'], per_yr=r['fills']/y,
                        ret_dd=rd)
        res[tag] = r
        return r

    base = row('NINE, live config (baseline)', d9, s9, c9, mode='pooled', excl_fn=pm9_9)
    unc = row('TWELVE, PM on all 12, NO cap', d12, s12, c12, mode='pooled', excl_fn=pm_all)
    cp4 = row('TWELVE, PM on all 12, PARR<=$400k', d12, s12, c12, mode='pooled',
              excl_fn=pm_all, name_cap=cap_map)
    cg = row(f'TWELVE, + breadth K>={GATE_K} on 9, PARR<=$400k', d12, s12, c12,
             mode='pooled', excl_fn=pm_all, no_buy=nb9, name_cap=cap_map)
    row('TWELVE captive, PARR<=$400k', d12, s12, c12, mode='captive',
        excl_fn=pm_all, name_cap=cap_map)

    # Does PARR earn its place once capped? If the eleven match the capped twelve,
    # the cap has reduced PARR to a fixed-size sleeve that contributes nothing.
    n11 = ROSTER + ['RTX', 'DE']
    d11, s11, c11 = load_all(names=n11, params_override=po)
    row('ELEVEN (no PARR), PM on all 11', d11, s11, c11, mode='pooled',
        excl_fn=pm_rule_for(d11, set(n11)))

    # ---- regression: the no-cap arm must still reproduce book12's stored figure
    try:
        prev = json.load(open('book12.json'))['TWELVE, PM on all 12']['full']
        print(f'\n  regression: no-cap arm {unc["full"]*100:.1f}% vs book12.json '
              f'{prev*100:.1f}%  ({abs(unc["full"]-prev)*100:.3f}pp)')
    except (OSError, KeyError):
        pass

    print(f'\n  cost of the cap: full {(cp4["full"]-unc["full"])*100:+.1f}pp   '
          f'test {(cp4["test"]-unc["test"])*100:+.1f}pp   '
          f'maxDD {(cp4["maxdd"]-unc["maxdd"])*100:+.1f}pp')
    print(f'  vs the nine-name baseline: full {(cp4["full"]-base["full"])*100:+.1f}pp   '
          f'test {(cp4["test"]-base["test"])*100:+.1f}pp   '
          f'maxDD {(cp4["maxdd"]-base["maxdd"])*100:+.1f}pp')

    # ---- order sizes
    for tag in ('TWELVE, PM on all 12, NO cap', 'TWELVE, PM on all 12, PARR<=$400k'):
        print(f'\n  ORDER SIZES — {tag}\n')
        by, byday = {}, collections.defaultdict(float)
        for t in res[tag]['trades']:
            by.setdefault(t['name'], []).append(t['cost'])
            byday[(t['name'], t['entry'])] += t['cost']
        print(f'    {"name":6s}{"orders":>8s}{"median":>10s}{"p95":>9s}{"max":>9s}'
              f'{"over 400k":>11s}')
        for n in NEW:
            cs = sorted(by.get(n, []))
            if not cs:
                continue
            p95 = cs[min(len(cs)-1, int(len(cs)*0.95))]
            ov = sum(1 for x in cs if x > PARR_CAP + 1)
            print(f'    {n:6s}{len(cs):>8d}{statistics.median(cs)/1e6:>9.2f}m'
                  f'{p95/1e6:>8.2f}m{max(cs)/1e6:>8.2f}m{ov:>6d}/{len(cs):<4d}')
            out.setdefault('orders', {}).setdefault(tag, {})[n] = dict(
                n=len(cs), median=statistics.median(cs), p95=p95, mx=max(cs), over=ov)
        pd = sorted(v for (n, _), v in byday.items() if n == 'PARR')
        if pd:
            both = sum(1 for x in pd if x > PARR_CAP + 1)
            print(f'\n    PARR per-DAY total (both sleeves): {len(pd)} days, median '
                  f'${statistics.median(pd)/1e3:.0f}k  max ${max(pd)/1e3:.0f}k'
                  f'   days over ${PARR_CAP/1e3:.0f}k: {both}/{len(pd)}'
                  f' ({both/len(pd)*100:.0f}%)')
            out.setdefault('parr_day', {})[tag] = dict(
                n=len(pd), median=statistics.median(pd), mx=max(pd), over=both)

    json.dump(out, open(OUT, 'w'), indent=1)
    print(f'\nwrote {OUT}\nDONE', flush=True)


if __name__ == '__main__':
    main()
