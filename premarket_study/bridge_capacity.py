"""
bridge_capacity.py — can Bayesian Capital actually release cash on a date certain?

User, 16 Oct 2026: *"If BC is fully invested, I may not have the option to do a
temporary partial loan repayment"* — which is the right challenge, because the
whole December funding plan pivots on that bridge being available.

Two things decide it and both are measurable from the book's own record:

  CASH ON HAND   the pooled book holds whatever is not in positions. If that is
                 routinely large the bridge needs no planning at all.
  RUN-OFF        if the book STOPS BIDDING on date T, open positions still exit
                 on their own schedule -- a resting take-profit or the 50-day
                 stop, neither of which depends on placing new orders. So the
                 cash released by T+k is exact, not a forecast: it is the
                 proceeds of positions already open at T that exit by T+k, and
                 §3.49's median hold of one day says that should be quick.

Standing down is not free: entries forgone during the wind-down are the cost,
and that is reported too.

A caveat the numbers cannot carry: the book trades US equities and the tax bill
is in euro, so a drawdown in EURUSD between the stand-down and the payment date
is an unhedged exposure this script does not model.

Usage: BAYES_WORKBOOK=<xlsx> python3 bridge_capacity.py [--capital 6900000]
"""
import collections
import datetime as dt
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
OUT = 'bridge_capacity.json'
TARGETS = (300_000, 700_000, 1_000_000)
HORIZONS = (0, 1, 2, 3, 5, 10, 15, 20)


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * q))] if xs else float('nan')


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
    names = ROSTER + NEW
    d, s, cal = load_all(names=names, params_override=po)
    r = simulate(d, s, cal, capital=cap, mode='pooled', collect_trades=True,
                 excl_fn=pm_rule_for(d, set(names)), name_cap={'PARR': PARR_CAP})
    cash, eq, cal, trades = r['cash'], r['equity'], r['cal'], r['trades']
    N = len(cal)
    out = {'capital': cap, 'n_sessions': N,
           'span': [str(cal[0]), str(cal[-1])]}

    print(f'twelve-name book, PM on all 12, PARR<=$400k, capital ${cap/1e6:.2f}m')
    print(f'{N} sessions, {cal[0]} -> {cal[-1]}\n')

    # ---- 1. cash sitting in the book on an ordinary day
    frac = [cash[i]/eq[i] for i in range(N)]
    print('=== 1. CASH ON HAND, no action taken ===\n')
    print(f'  {"":14s}{"10th":>12s}{"25th":>12s}{"median":>12s}{"75th":>12s}{"90th":>12s}')
    print(f'  {"% of equity":14s}' + ''.join(f'{pct(frac,q)*100:>11.1f}%'
                                             for q in (0.10, 0.25, 0.50, 0.75, 0.90)))
    print(f'  {"$ on hand":14s}' + ''.join(f'{pct(cash,q)/1e6:>11.2f}m'
                                           for q in (0.10, 0.25, 0.50, 0.75, 0.90)))
    print(f'\n  share of days with cash already at or above:')
    for t in TARGETS:
        n = sum(1 for x in cash if x >= t)
        print(f'    ${t/1e3:>5.0f}k : {n/N*100:>5.1f}% of days')
        out.setdefault('cash_at_or_above', {})[str(t)] = n/N
    out['cash_frac'] = {q: pct(frac, q) for q in (0.10, 0.25, 0.50, 0.75, 0.90)}
    out['cash_abs'] = {q: pct(cash, q) for q in (0.10, 0.25, 0.50, 0.75, 0.90)}

    # ---- 2. stand-down run-off. Positions open at T exit on their own schedule.
    ix = {dd: i for i, dd in enumerate(cal)}
    by_exit = collections.defaultdict(list)
    for t in trades:
        by_exit[t['exit']].append(t)
    released = {}
    for T in range(N):
        d0 = cal[T]
        run, tot = [], 0.0
        for k in range(max(HORIZONS) + 1):
            if T + k < N:
                for t in by_exit.get(cal[T + k], ()):
                    if k > 0 and t['entry'] <= d0:
                        tot += t['cost'] + t['pnl']
            run.append(cash[T] + tot)
        released[T] = run

    print(f'\n=== 2. STAND-DOWN RUN-OFF — stop bidding on day T, cash by T+k ===\n')
    print(f'  {"sessions":>9s}{"10th":>11s}{"25th":>11s}{"median":>11s}'
          + ''.join(f'{f">=${t/1e3:.0f}k":>11s}' for t in TARGETS))
    for k in HORIZONS:
        vals = [released[T][k] for T in range(N) if T + k < N]
        row = f'  {k:>9d}' + ''.join(f'{pct(vals,q)/1e6:>10.2f}m' for q in (0.10, 0.25, 0.50))
        row += ''.join(f'{sum(1 for v in vals if v >= t)/len(vals)*100:>10.0f}%' for t in TARGETS)
        print(row)
        out.setdefault('runoff', {})[str(k)] = dict(
            p10=pct(vals, 0.10), p25=pct(vals, 0.25), median=pct(vals, 0.50),
            hit={str(t): sum(1 for v in vals if v >= t)/len(vals) for t in TARGETS})

    # ---- 3. the operational question: lead time needed, worst cases
    print(f'\n=== 3. LEAD TIME — sessions to reach the target from a standing start ===\n')
    print(f'  {"target":>9s}{"median":>9s}{"75th":>9s}{"90th":>9s}{"95th":>9s}{"never":>9s}')
    for t in TARGETS:
        need = []
        never = 0
        for T in range(N):
            hit = next((k for k in range(max(HORIZONS)+1)
                        if T + k < N and released[T][k] >= t), None)
            if hit is None:
                never += 1
            else:
                need.append(hit)
        print(f'  ${t/1e3:>7.0f}k{pct(need,0.50):>9.0f}{pct(need,0.75):>9.0f}'
              f'{pct(need,0.90):>9.0f}{pct(need,0.95):>9.0f}{never/N*100:>8.1f}%')
        out.setdefault('lead_time', {})[str(t)] = dict(
            median=pct(need, 0.50), p75=pct(need, 0.75), p90=pct(need, 0.90),
            p95=pct(need, 0.95), never=never/N)

    # ---- 4. mid-December specifically, since that is the date that matters
    print(f'\n=== 4. MID-DECEMBER in the archive (the 15 Dec payment date) ===\n')
    for T in range(N):
        dd = cal[T]
        if dd.month == 12 and 8 <= dd.day <= 16:
            k5, k10 = released[T][5], released[T][10]
            print(f'  {dd}  cash on hand ${cash[T]/1e6:>5.2f}m   '
                  f'+5 sessions ${k5/1e6:>5.2f}m   +10 ${k10/1e6:>5.2f}m')

    # ---- 5. what standing down costs
    print(f'\n=== 5. COST OF STANDING DOWN — entries forgone ===\n')
    yrs = N/252
    print(f'  book full-period return {(eq[-1]/eq[0]-1)*100:.1f}% over {yrs:.2f}y'
          f'  ({((eq[-1]/eq[0])**(1/yrs)-1)*100:.1f}%/yr)')
    for k in (5, 10, 20):
        print(f'    {k:>2d} sessions idle at that rate ~ '
              f'{((eq[-1]/eq[0])**(1/yrs)-1)*100*k/252:>5.2f}% of book '
              f'= ${cap*((eq[-1]/eq[0])**(1/yrs)-1)*k/252/1e3:>6.0f}k')

    json.dump(out, open(OUT, 'w'), indent=1, default=str)
    print(f'\nwrote {OUT}\nDONE', flush=True)


if __name__ == '__main__':
    main()
