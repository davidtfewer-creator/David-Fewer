"""
Does another $2m fit, measured on the orders the book actually places?

§3.43 put the equal-weight ceiling at ~$7.3m by dividing the thinnest name's
gate (CF, $0.81m) across the book, and flagged the assumption: "it assumes every
name funded at once, where a typical morning funds about six sleeves". That makes
it conservative but imprecise. This measures the real thing -- run the pooled
book at the proposed capital, collect every fill, and compare each name's ACTUAL
order sizes against its own liquidity gate.

The gate is §3.37's: an order is acceptable under ~1% of the name's MEDIAN
at-bid dollar volume and under ~10% on a thin (10th-percentile) fill day. At-bid
volume, not ADV, because the model rests a limit buy below the market and is
filled by someone else's selling.

TWO LIMITS, both material:
  * The liquidity figures come from the 5-minute archive, which ends Aug 2026.
    Volumes since are unmeasured, and in a rates shock they are more likely to
    be higher than lower, which would be favourable -- so this is conservative
    in that direction but it is NOT a current reading.
  * Capital is the book's MARK, which has just fallen. A ceiling measured at a
    drawdown mark understates how much the book must carry when it recovers.

Usage: BAYES_WORKBOOK=<xlsx> python3 capacity_recheck.py [--capital 6900000]
"""
import json
import statistics
import sys

from baseline_check import ROSTER
from book_sim import load_all, simulate
from cf_swap_test import pm_rule_for, t0
from fresh_opt_cands import aw_params

MED_FRAC, THIN_FRAC = 0.01, 0.10


def caps():
    liq = json.load(open('liquidity_check.json'))
    out = {}
    for n in ROSTER:
        d = liq.get(n)
        if not d:
            continue
        cm, ct = d['depth_dv']*MED_FRAC, d['depth_dv_p10']*THIN_FRAC
        out[n] = dict(median_at_bid=d['depth_dv'], thin=d['depth_dv_p10'],
                      cap=min(cm, ct), binds=('median' if cm < ct else 'thin day'))
    return out


def run(capital, po):
    data, sleeves, cal = load_all(names=ROSTER, params_override=po)
    r = simulate(data, sleeves, cal, capital=capital,
                 excl_fn=pm_rule_for(data), collect_trades=True)
    by = {}
    for t in r['trades']:
        by.setdefault(t['name'], []).append(t['cost'])
    return r, by


def main():
    cap_req = 6_900_000
    if '--capital' in sys.argv:
        cap_req = float(sys.argv[sys.argv.index('--capital')+1])
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    G = caps()
    out = {}
    for lbl, K in (('now  ~$4.9m', 4_900_000), (f'+$2m ~${cap_req/1e6:.1f}m', cap_req)):
        r, by = run(K, po)
        print(f'\n{"="*96}\n{lbl}   book {r["full"]*100:.1f}% full / {r["test"]*100:.1f}% test, '
              f'{r["fills"]} fills\n')
        print(f'{"name":6s}{"gate cap":>11s}{"binds":>11s}{"orders":>8s}{"median":>11s}'
              f'{"95th":>11s}{"max":>11s}{"over cap":>10s}{"worst":>9s}')
        tot_over = 0
        for n in ROSTER:
            cs = sorted(by.get(n, []))
            g = G.get(n)
            if not cs or not g:
                continue
            p95 = cs[min(len(cs)-1, int(len(cs)*0.95))]
            over = sum(1 for x in cs if x > g['cap'])
            tot_over += over
            worst = max(cs)/g['cap']
            out.setdefault(lbl, {})[n] = dict(cap=g['cap'], binds=g['binds'], n=len(cs),
                                              median=statistics.median(cs), p95=p95,
                                              mx=max(cs), over=over, worst_x=worst)
            flag = '  <<<' if over else ''
            print(f'{n:6s}{g["cap"]/1e6:>10.2f}m{g["binds"]:>11s}{len(cs):>8d}'
                  f'{statistics.median(cs)/1e6:>10.2f}m{p95/1e6:>10.2f}m{max(cs)/1e6:>10.2f}m'
                  f'{over:>7d}/{len(cs):<3d}{worst:>8.2f}x{flag}', flush=True)
        n_all = sum(len(v) for v in by.values())
        print(f'\n  orders breaching the gate: {tot_over} of {n_all} '
              f'({tot_over/n_all*100:.1f}%)')
    json.dump(out, open('capacity_recheck.json', 'w'), indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()


def sweep():
    """At what capital does the book stop respecting its own liquidity gate?"""
    import json as _j
    c = _j.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    G = caps()
    print(f'\n{"="*96}\nCAPITAL SWEEP — share of orders breaching §3.37\n')
    print(f'{"capital":>10s}{"all":>9s}{"CF":>12s}{"VLO":>12s}{"GM":>12s}{"VST":>12s}'
          f'{"CF median":>12s}{"vs CF cap":>11s}')
    rows = {}
    for K in (4_000_000, 4_900_000, 5_500_000, 6_000_000, 6_900_000, 8_000_000):
        r, by = run(K, po)
        tot = sum(len(v) for v in by.values())
        over = {}
        for n in ('CF', 'VLO', 'GM', 'VST'):
            cs = by.get(n, [])
            over[n] = sum(1 for x in cs if x > G[n]['cap'])/max(len(cs), 1)*100
        allover = sum(sum(1 for x in by.get(n, []) if x > G[n]['cap'])
                      for n in G)/tot*100
        cfmed = statistics.median(by['CF'])
        rows[K] = dict(all_pct=allover, per_name=over, cf_median=cfmed,
                       cf_ratio=cfmed/G['CF']['cap'], ann=r['full'])
        print(f'{K/1e6:>9.1f}m{allover:>8.1f}%{over["CF"]:>11.0f}%{over["VLO"]:>11.0f}%'
              f'{over["GM"]:>11.0f}%{over["VST"]:>11.0f}%{cfmed/1e6:>11.2f}m'
              f'{cfmed/G["CF"]["cap"]:>10.2f}x', flush=True)
    _j.dump(rows, open('capacity_sweep.json', 'w'), indent=1)
    print('\n  CF median vs cap crossing 1.00x = the MEDIAN CF order is over the gate,')
    print('  not just the tail. That is the point the book stops being fundable as built.')
