"""
dd_anatomy.py — what the headline "20.9% max drawdown" actually describes.

User, 20 Oct 2026: *"When you say 20% drawdown what does it mean? Does it mean
the book can drop 20% from its high at a time during the trading period?"*

book_sim computes it as  max over days of (running peak - equity)/running peak,
on the DAILY CLOSE equity curve, where equity = cash + mark-to-market of open
positions. So it is the deepest single peak-to-trough fall anywhere in the
backtest -- one episode out of 2.3 years, not a per-year or typical figure.
This measures the rest of the shape: when it happened, how long it lasted, how
long to recover, and how much of the time the book spends underwater at all.
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
from parallel_book import load_rho, load_vecs
from two_day import x0_vector

ADDED = ['RTX', 'DE', 'NVDA']
OUT = 'dd_anatomy.json'


def episodes(cal, eq, thr):
    """Every peak-to-trough-to-recovery episode deeper than thr."""
    out, peak, pi = [], eq[0], 0
    i, n = 1, len(eq)
    while i < n:
        if eq[i] >= peak:
            peak, pi = eq[i], i
            i += 1
            continue
        j, trough, ti = i, eq[i], i
        while j < n and eq[j] < peak:
            if eq[j] < trough:
                trough, ti = eq[j], j
            j += 1
        depth = (peak - trough) / peak
        if depth >= thr:
            out.append(dict(depth=depth, peak=cal[pi], trough=cal[ti],
                            recovered=(cal[j] if j < n else None),
                            fall_days=(cal[ti] - cal[pi]).days,
                            rec_days=((cal[j] - cal[ti]).days if j < n else None),
                            fall_sess=ti - pi, rec_sess=(j - ti if j < n else None)))
        if j >= n:
            break
        peak, pi, i = eq[j], j, j + 1
    return out


def main():
    cap = 6_900_000
    rho, vecs = load_rho(), load_vecs()
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    for n in ADDED:
        r = rho.get(n)
        po[n] = params_from_vec(vecs[n] if (r is not None and r >= 0.20 and n in vecs)
                                else x0_vector(1), t0())
    names = ROSTER + ADDED
    d, s, cal = load_all(names=names, params_override=po)
    r = simulate(d, s, cal, capital=cap, mode='pooled', collect_trades=True,
                 excl_fn=pm_rule_for(d, set(names)))
    eq, N = r['equity'], len(cal)
    print(f'twelve-name book, ${cap/1e6:.2f}m, {N} sessions {cal[0]} -> {cal[-1]}')
    print(f'reported maxDD {r["maxdd"]*100:.1f}%\n')

    peak, dd = eq[0], []
    for v in eq:
        peak = max(peak, v)
        dd.append((peak - v) / peak)
    worst = max(range(N), key=lambda i: dd[i])

    print('=== 1. THE WORST EPISODE — this is the headline number ===\n')
    eps = episodes(cal, eq, 0.05)
    w = max(eps, key=lambda e: e['depth'])
    print(f'  depth            {w["depth"]*100:.1f}%   (${w["depth"]*cap/1e6:.2f}m on a '
          f'${cap/1e6:.1f}m book)')
    print(f'  peak             {w["peak"]}')
    print(f'  trough           {w["trough"]}   {w["fall_sess"]} sessions / '
          f'{w["fall_days"]} calendar days later')
    print(f'  back to the peak {w["recovered"]}   ' +
          (f'{w["rec_sess"]} sessions / {w["rec_days"]} days after the trough'
           if w['recovered'] else 'NOT RECOVERED in the archive'))
    tot = (w['fall_sess'] + (w['rec_sess'] or 0))
    print(f'  underwater       {tot} sessions end to end '
          f'({tot/252*12:.1f} months)')

    print('\n=== 2. IT IS ONE EPISODE, NOT A TYPICAL YEAR ===\n')
    print(f'  {"deeper than":>13s}{"episodes":>10s}{"median depth":>14s}'
          f'{"median recovery":>17s}')
    for thr in (0.05, 0.10, 0.15, 0.20):
        es = [e for e in eps if e['depth'] >= thr]
        if not es:
            print(f'  {thr*100:>12.0f}%{0:>10d}{"-":>14s}{"-":>17s}')
            continue
        recs = [e['rec_sess'] for e in es if e['rec_sess'] is not None]
        print(f'  {thr*100:>12.0f}%{len(es):>10d}'
              f'{statistics.median(e["depth"] for e in es)*100:>13.1f}%'
              f'{(f"{statistics.median(recs):.0f} sessions" if recs else "-"):>17s}')

    print('\n=== 3. HOW MUCH OF THE TIME IS THE BOOK UNDERWATER AT ALL ===\n')
    for lo, hi, lbl in ((0.0, 0.01, 'at/near a high (<1% off)'),
                        (0.01, 0.05, '1-5% off'), (0.05, 0.10, '5-10% off'),
                        (0.10, 0.15, '10-15% off'), (0.15, 1.0, 'more than 15% off')):
        k = sum(1 for x in dd if lo <= x < hi)
        print(f'  {lbl:26s}{k:>6d} sessions{k/N*100:>7.1f}%')
    print(f'\n  median drawdown on a random day: {statistics.median(dd)*100:.1f}%')
    print(f'  95th percentile                : {sorted(dd)[int(N*0.95)]*100:.1f}%')

    print('\n=== 4. WHAT A SINGLE DAY CAN DO ===\n')
    rets = [(eq[i]/eq[i-1] - 1) for i in range(1, N)]
    print(f'  worst single session  {min(rets)*100:.2f}%   '
          f'(${abs(min(rets))*cap/1e3:,.0f}k on ${cap/1e6:.1f}m)')
    print(f'  worst 5 sessions      {min((eq[i]/eq[i-5]-1) for i in range(5, N))*100:.2f}%')
    print(f'  best single session   {max(rets)*100:+.2f}%')
    print(f'\n  NOTE: all of this is measured on DAILY CLOSES. Intraday the book went')
    print(f'  lower than these figures on the way to each trough — the archive cannot')
    print(f'  say how much lower without marking every open position intraday.')

    json.dump(dict(maxdd=r['maxdd'], worst=w,
                   episodes=[{k: str(v) for k, v in e.items()} for e in eps],
                   time_at_depth={lbl: sum(1 for x in dd if lo <= x < hi)/N
                                  for lo, hi, lbl in
                                  ((0.0, 0.01, 'lt1'), (0.01, 0.05, '1to5'),
                                   (0.05, 0.10, '5to10'), (0.10, 0.15, '10to15'),
                                   (0.15, 1.0, 'gt15'))},
                   worst_day=min(rets)), open(OUT, 'w'), indent=1, default=str)
    print(f'\nwrote {OUT}')


if __name__ == '__main__':
    main()
