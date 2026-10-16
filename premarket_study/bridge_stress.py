"""
bridge_stress.py — bridge capacity CONDITIONAL ON BEING IN A DRAWDOWN.

bridge_capacity.py measured cash across all sessions and found the book is
rarely fully invested. But the unconditional figure is the wrong one for
December 2026: the user is in a drawdown right now (the October bond-yield
event), and a drawdown is exactly when the book holds MORE and carries LESS
cash -- positions that have not reached their targets stay open.

So this re-asks the same question on the days that look like today. It also
switches the target to DOLLARS NEEDED FOR A EURO BILL, since the book is in USD
and the tax is in EUR.

Usage: BAYES_WORKBOOK=<xlsx> python3 bridge_stress.py [--eurusd 1.15]
"""
import collections
import json
import statistics
import sys

from baseline_check import ROSTER
from book12 import NEW, pm_rule_for
from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import t0
from fresh_opt_cands import aw_params
from parallel_book import load_rho, load_vecs
from two_day import x0_vector

PARR_CAP = 400_000
OUT = 'bridge_stress.json'
BANDS = ((0.00, 0.05, 'at/near a high (0-5% off)'),
         (0.05, 0.10, 'mild (5-10% off)'),
         (0.10, 0.15, 'moderate (10-15% off)'),
         (0.15, 1.00, 'deep (>15% off)'))


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * q))] if xs else float('nan')


def main():
    fx = 1.15
    if '--eurusd' in sys.argv:
        fx = float(sys.argv[sys.argv.index('--eurusd') + 1])
    cap = 6_900_000
    needs = {'EUR 300k': 300_000*fx, 'EUR 700k': 700_000*fx, 'EUR 1.0m': 1_000_000*fx}

    rho, vecs = load_rho(), load_vecs()
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    for n in NEW:
        r = rho.get(n)
        po[n] = params_from_vec(vecs[n] if (r is not None and r >= 0.20 and n in vecs)
                                else x0_vector(1), t0())
    names = ROSTER + NEW
    d, s, cal = load_all(names=names, params_override=po)
    r = simulate(d, s, cal, capital=cap, mode='pooled', collect_trades=True,
                 excl_fn=pm_rule_for(d, set(names)), name_cap={'PARR': PARR_CAP})
    cash, eq, cal, trades = r['cash'], r['equity'], r['cal'], r['trades']
    N = len(cal)

    print(f'twelve-name book, capital ${cap/1e6:.2f}m, EURUSD {fx}')
    print(f'euro needs in dollars: ' + '  '.join(f'{k}=${v/1e6:.2f}m'
                                                 for k, v in needs.items()) + '\n')

    # drawdown depth per session
    peak, dd = eq[0], []
    for v in eq:
        peak = max(peak, v)
        dd.append(1 - v/peak)

    by_exit = collections.defaultdict(list)
    for t in trades:
        by_exit[t['exit']].append(t)

    def runoff(T, k):
        tot = 0.0
        for j in range(1, k+1):
            if T + j < N:
                for t in by_exit.get(cal[T+j], ()):
                    if t['entry'] <= cal[T]:
                        tot += t['cost'] + t['pnl']
        return cash[T] + tot

    out = {'eurusd': fx, 'capital': cap}
    print('=== CASH ON HAND BY DRAWDOWN DEPTH ===\n')
    print(f'  {"state":28s}{"days":>6s}{"10th":>9s}{"median":>9s}'
          + ''.join(f'{k:>11s}' for k in needs))
    for lo, hi, lbl in BANDS:
        ixs = [i for i in range(N) if lo <= dd[i] < hi]
        if not ixs:
            continue
        cs = [cash[i] for i in ixs]
        row = f'  {lbl:28s}{len(ixs):>6d}{pct(cs,0.10)/1e6:>8.2f}m{pct(cs,0.50)/1e6:>8.2f}m'
        row += ''.join(f'{sum(1 for x in cs if x >= v)/len(cs)*100:>10.0f}%'
                       for v in needs.values())
        print(row)
        out.setdefault('by_dd', {})[lbl] = dict(
            days=len(ixs), p10=pct(cs, 0.10), median=pct(cs, 0.50),
            hit={k: sum(1 for x in cs if x >= v)/len(cs) for k, v in needs.items()})

    print(f'\n=== THE STRESS CASE: deep drawdown, after standing down k sessions ===\n')
    deep = [i for i in range(N) if dd[i] >= 0.15]
    print(f'  {len(deep)} sessions more than 15% off the high\n')
    print(f'  {"sessions":>9s}{"10th":>10s}{"median":>10s}' + ''.join(f'{k:>11s}' for k in needs))
    for k in (0, 1, 3, 5, 10, 15):
        vals = [runoff(T, k) for T in deep if T + k < N]
        if not vals:
            continue
        row = f'  {k:>9d}{pct(vals,0.10)/1e6:>9.2f}m{pct(vals,0.50)/1e6:>9.2f}m'
        row += ''.join(f'{sum(1 for v in vals if v >= x)/len(vals)*100:>10.0f}%'
                       for x in needs.values())
        print(row)
        out.setdefault('deep_runoff', {})[str(k)] = dict(
            p10=pct(vals, 0.10), median=pct(vals, 0.50),
            hit={kk: sum(1 for v in vals if v >= x)/len(vals)
                 for kk, x in needs.items()})

    print(f'\n=== ABSOLUTE WORST SESSION IN THE ARCHIVE ===\n')
    w = min(range(N), key=lambda i: cash[i])
    print(f'  lowest cash: {cal[w]}  ${cash[w]/1e3:.0f}k on hand '
          f'({cash[w]/eq[w]*100:.1f}% of equity, {dd[w]*100:.1f}% off the high)')
    for k in (1, 3, 5, 10):
        print(f'    + {k:>2d} sessions standing down -> ${runoff(w, k)/1e6:.2f}m')
    out['worst'] = dict(date=str(cal[w]), cash=cash[w], frac=cash[w]/eq[w], dd=dd[w],
                        runoff={str(k): runoff(w, k) for k in (1, 3, 5, 10)})

    json.dump(out, open(OUT, 'w'), indent=1, default=str)
    print(f'\nwrote {OUT}\nDONE', flush=True)


if __name__ == '__main__':
    main()
