"""
participation.py — how big is the book's order against the liquidity a RESTING
LIMIT can actually reach? (user, 15 Oct 2026)

§3.37 established the denominator: not ADV, but the dollar volume trading AT OR
BELOW the bid, because the order is a passive limit filled by someone else's
selling. §3.20 then showed 56-80% of fills land in the first hour, which makes
the FIRST-HOUR at-bid figure the honest one. But the 1%/10% caps §3.37 applied
on top of that denominator were reverse-engineered from what the incumbent names
happened to pass -- a guard-rail, not a measurement (§3.62).

This replaces the guard-rail with the book's own record: every historical fill,
sized as a share of the liquidity reachable that day at that bid.

  BUY   notional / dollar volume in bars whose LOW <= the bid
          - whole session, and first hour only
          - with ADV shown alongside, to show how much the usual metric flatters
  SELL  passive (target hit): proceeds / dollar volume in bars whose HIGH >= the
          target. The take-profit is a resting limit too.
        marketable (50-day stop): proceeds / the OPENING BAR's dollar volume, and
          / the first 30 minutes. This is the only part of the loop that crosses
          the spread, and it is where impact actually lives.

Participation scales LINEARLY in capital, so the per-name capacity line -- the
capital at which the 95th-percentile order reaches a given participation -- comes
free, and is the number worth having.

PARR is excluded: its Box file carries no volume column (§3.61).

Usage: BAYES_WORKBOOK=<xlsx> python3 participation.py [--capital 6900000]
"""
import collections
import datetime as dt
import json
import os
import pickle
import statistics
import sys

import openpyxl

from baseline_check import ROSTER
from book_sim import load_all, simulate
from cf_speed_g5 import params_from_vec
from cf_swap_test import t0
from fresh_opt_cands import aw_params
from parallel_book import load_rho, load_vecs
from two_day import x0_vector

OUT = 'participation.json'
DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_5min')
RTH0, RTH1 = dt.time(9, 30), dt.time(16, 0)
HOUR1, MIN30, OPEN1 = dt.time(10, 30), dt.time(10, 0), dt.time(9, 35)
ADDED = ['RTX', 'DE']
# participation levels to tabulate, as a share of first-hour at-bid dollar volume
LEVELS = (0.01, 0.02, 0.05, 0.10, 0.20, 0.50)


def load_bars(nm):
    """{date: [(time, high, low, dollar_volume)]}, regular hours only."""
    wb = openpyxl.load_workbook(os.path.join(DIR, f'{nm}_5min.xlsx'),
                                read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    next(it)
    by = collections.defaultdict(list)
    for r in it:
        d = r[0]
        if not isinstance(d, dt.datetime) or r[1] is None:
            continue
        t = d.time()
        if not (RTH0 <= t < RTH1):
            continue
        h, l, c = float(r[2]), float(r[3]), float(r[4])
        v = float(r[5]) if len(r) > 5 and r[5] is not None else 0.0
        by[d.date()].append((t, h, l, c * v))
    wb.close()
    return {d: sorted(v) for d, v in by.items()}


def pm_rule_for(data, only, cut='09:00', thr=0.04):
    """The §3.16 pre-market rule, applied ONLY to the named set."""
    pm = pickle.load(open('data_pm/pm_last_cuts.pkl', 'rb'))[cut]
    def f(name, i, bid):
        if name not in only:
            return False
        p = pm.get(name, {}).get(data[name]['dts'][i])
        return p is not None and bid < p*(1 - thr)
    return f


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return float('nan')
    return xs[min(len(xs) - 1, int(len(xs) * q))]


def measure(trades, bars):
    """Attach participation ratios to every trade whose day is in the archive."""
    rows, miss = [], 0
    for t in trades:
        nm = t['name']
        b = bars.get(nm)
        if b is None:
            continue
        day = b.get(t['entry'])
        if day is None:
            miss += 1
            continue
        bid = t['bid']
        dv_day = sum(x[3] for x in day)
        buy_all = sum(x[3] for x in day if x[2] <= bid + 1e-9)
        buy_h1 = sum(x[3] for x in day if x[2] <= bid + 1e-9 and x[0] < HOUR1)
        # A quarter of fills never see the bid in the first hour -- the order simply
        # rests until later in the session. Dropping those would silently remove the
        # hardest cases, so they are carried at the SESSION denominator ('blend'),
        # which is the figure that actually applies to them.
        r = dict(name=nm, kind=t['kind'], entry=t['entry'], exit=t['exit'],
                 notional=t['cost'], stopped=t['stopped'], late=buy_h1 <= 0,
                 p_adv=t['cost'] / dv_day if dv_day else None,
                 p_buy_all=t['cost'] / buy_all if buy_all else None,
                 p_buy_h1=t['cost'] / buy_h1 if buy_h1 else None,
                 p_blend=(t['cost'] / buy_h1 if buy_h1
                          else (t['cost'] / buy_all if buy_all else None)))
        # ---- sell side
        xd = b.get(t['exit'])
        proceeds = t['cost'] + t['pnl']
        if xd is not None:
            if t['stopped']:
                o1 = sum(x[3] for x in xd if x[0] < OPEN1)
                o30 = sum(x[3] for x in xd if x[0] < MIN30)
                r['p_stop_open'] = proceeds / o1 if o1 else None
                r['p_stop_30'] = proceeds / o30 if o30 else None
            else:
                tg = t['target']
                sv = sum(x[3] for x in xd if x[1] >= tg - 1e-9)
                r['p_sell_all'] = proceeds / sv if sv else None
        rows.append(r)
    return rows, miss


def dist(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return dict(n=len(xs), median=statistics.median(xs), p75=pct(xs, 0.75),
                p95=pct(xs, 0.95), mx=max(xs))


def report(tag, rows, cap, out):
    print(f'\n{"="*96}\n  {tag}   (capital ${cap/1e6:.2f}m, {len(rows)} measured fills)'
          f'\n{"="*96}')
    print(f'\n  BUY SIDE — order as a share of the liquidity a resting limit reaches\n')
    print(f'  {"name":6s}{"fills":>7s}{"median $":>10s}{"max $":>9s}'
          f'{"| %ADV":>9s}{"%at-bid":>9s}{"%1st hr":>9s}{"p95 1st hr":>12s}{"late":>7s}{"p95 blend":>11s}')
    per = {}
    for nm in sorted({r['name'] for r in rows}):
        rs = [r for r in rows if r['name'] == nm]
        h1 = dist([r['p_buy_h1'] for r in rs])
        al = dist([r['p_buy_all'] for r in rs])
        ad = dist([r['p_adv'] for r in rs])
        bd = dist([r['p_blend'] for r in rs])
        ns = [r['notional'] for r in rs]
        late = sum(1 for r in rs if r['late']) / len(rs)
        if not h1:
            continue
        per[nm] = dict(fills=len(rs), notional_median=statistics.median(ns),
                       notional_max=max(ns), adv=ad, at_bid=al, hour1=h1,
                       blend=bd, late_share=late)
        print(f'  {nm:6s}{len(rs):>7d}{statistics.median(ns)/1e6:>9.2f}m{max(ns)/1e6:>8.2f}m'
              f'{ad["median"]*100:>8.2f}%{al["median"]*100:>8.2f}%{h1["median"]*100:>8.2f}%'
              f'{h1["p95"]*100:>11.1f}%{late*100:>6.0f}%{bd["p95"]*100:>10.1f}%')
    allh1 = [r['p_buy_h1'] for r in rows]
    a, ab = dist(allh1), dist([r['p_blend'] for r in rows])
    lateb = sum(1 for r in rows if r['late']) / len(rows)
    print(f'  {"BOOK":6s}{len(rows):>7d}{statistics.median([r["notional"] for r in rows])/1e6:>9.2f}m'
          f'{max(r["notional"] for r in rows)/1e6:>8.2f}m'
          f'{dist([r["p_adv"] for r in rows])["median"]*100:>8.2f}%'
          f'{dist([r["p_buy_all"] for r in rows])["median"]*100:>8.2f}%'
          f'{a["median"]*100:>8.2f}%{a["p95"]*100:>11.1f}%{lateb*100:>6.0f}%'
          f'{ab["p95"]*100:>10.1f}%')
    print(f'\n  "late" = the share of fills whose bid was never reached in the first '
          f'hour; those\n  rest into the session, so "blend" carries them at the '
          f'whole-session denominator.')

    print(f'\n  share of fills ABOVE a given participation in first-hour at-bid volume\n')
    print(f'  {"name":6s}' + ''.join(f'{f">{L*100:g}%":>9s}' for L in LEVELS))
    xs = [x for x in allh1 if x is not None]
    for nm in sorted(per):
        rs = [r['p_buy_h1'] for r in rows if r['name'] == nm and r['p_buy_h1'] is not None]
        per[nm]['above'] = {str(L): sum(1 for x in rs if x > L)/len(rs) for L in LEVELS}
        print(f'  {nm:6s}' + ''.join(
            f'{sum(1 for x in rs if x > L)/len(rs)*100:>8.0f}%' for L in LEVELS))
    print(f'  {"BOOK":6s}' + ''.join(
        f'{sum(1 for x in xs if x > L)/len(xs)*100:>8.0f}%' for L in LEVELS))

    # ---- capacity: participation is linear in capital
    print(f'\n  CAPACITY — book capital at which the 95th-pct order reaches a given'
          f'\n  share of first-hour at-bid volume (linear scaling from ${cap/1e6:.2f}m)\n')
    print(f'  {"name":6s}{"@5%":>10s}{"@10%":>10s}{"@20%":>10s}')
    for nm in sorted(per):
        p95 = per[nm]['hour1']['p95']
        per[nm]['capacity'] = {str(L): cap * L / p95 for L in (0.05, 0.10, 0.20)}
        print(f'  {nm:6s}' + ''.join(f'{cap*L/p95/1e6:>9.0f}m' for L in (0.05, 0.10, 0.20)))
    p95b = a['p95']
    print(f'  {"BOOK":6s}' + ''.join(f'{cap*L/p95b/1e6:>9.0f}m' for L in (0.05, 0.10, 0.20)))
    core = [r['p_blend'] for r in rows if r['name'] not in ('CF', 'VLO')
            and r['p_blend'] is not None]
    if core and len(core) < len(rows):
        p95c, p95a = pct(core, 0.95), dist([r['p_blend'] for r in rows])['p95']
        print(f'  {"-CF-VLO":7s}' + ''.join(f'{cap*L/p95c/1e6:>8.0f}m'
                                            for L in (0.05, 0.10, 0.20))
              + f'   (pooled p95 {p95c*100:.1f}% vs {p95a*100:.1f}% with them)')
        out.setdefault('_core', {})[tag] = dict(
            n=len(core), p95=p95c, p95_with=p95a,
            capacity={str(L): cap*L/p95c for L in (0.05, 0.10, 0.20)})

    # ---- sell side
    ps = dist([r.get('p_sell_all') for r in rows])
    st = [r for r in rows if r['stopped']]
    so = dist([r.get('p_stop_open') for r in st])
    s30 = dist([r.get('p_stop_30') for r in st])
    print(f'\n  SELL SIDE\n')
    if ps:
        print(f'    passive (target hit, resting limit): {ps["n"]} exits, '
              f'median {ps["median"]*100:.2f}%  p95 {ps["p95"]*100:.1f}%  '
              f'max {ps["mx"]*100:.1f}%  of at-or-above-target volume')
    if so:
        print(f'    MARKETABLE (50-day stop, sells at the open): {so["n"]} of {len(rows)} '
              f'exits ({so["n"]/len(rows)*100:.1f}%)')
        print(f'      vs the opening 5-min bar : median {so["median"]*100:.1f}%  '
              f'p95 {so["p95"]*100:.1f}%  max {so["mx"]*100:.1f}%')
        print(f'      vs the first 30 minutes  : median {s30["median"]*100:.1f}%  '
              f'p95 {s30["p95"]*100:.1f}%  max {s30["mx"]*100:.1f}%')
    # keep the raw per-fill ratios: every later slice (drop a name, change the
    # threshold) comes off these instead of another full simulation.
    out[tag + ' :: rows'] = [dict(name=r['name'], entry=str(r['entry']),
                                  notional=round(r['notional'], 2),
                                  late=r['late'], stopped=r['stopped'],
                                  adv=r['p_adv'], at_bid=r['p_buy_all'],
                                  h1=r['p_buy_h1'], blend=r['p_blend'],
                                  sell=r.get('p_sell_all'),
                                  stop_open=r.get('p_stop_open'),
                                  stop_30=r.get('p_stop_30')) for r in rows]
    out[tag] = dict(capital=cap, n=len(rows), per_name=per,
                    book=dict(adv=dist([r['p_adv'] for r in rows]),
                              at_bid=dist([r['p_buy_all'] for r in rows]),
                              hour1=a, blend=ab, late_share=lateb,
                              above={str(L): sum(1 for x in xs if x > L)/len(xs)
                                     for L in LEVELS},
                              capacity={str(L): cap*L/p95b for L in (0.05, 0.10, 0.20)}),
                    sell_passive=ps, stop_open=so, stop_30=s30)


def main():
    cap = 6_900_000
    if '--capital' in sys.argv:
        cap = float(sys.argv[sys.argv.index('--capital') + 1])
    names11 = ROSTER + ADDED
    print('loading the 5-minute archive ...', flush=True)
    bars = {nm: load_bars(nm) for nm in names11}

    rho, vecs = load_rho(), load_vecs()
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    for n in ADDED:
        r = rho.get(n)
        po[n] = params_from_vec(vecs[n] if (r is not None and r >= 0.20 and n in vecs)
                                else x0_vector(1), t0())

    out = {'_note': ('order sizes measured against the dollar volume a RESTING LIMIT '
                     'reaches: bars whose low <= the bid (buy) / high >= the target '
                     '(passive sell); first hour per §3.20. PARR excluded, no volume '
                     'column.')}

    d9, s9, c9 = load_all(names=ROSTER, params_override=po)
    r9 = simulate(d9, s9, c9, capital=cap, mode='pooled', collect_trades=True,
                  excl_fn=pm_rule_for(d9, set(ROSTER)))
    rows9, m9 = measure(r9['trades'], bars)
    report('NINE, live config', rows9, cap, out)
    print(f'\n  ({m9} fills dropped: entry date not in the 5-minute archive)')

    d11, s11, c11 = load_all(names=names11, params_override=po)
    r11 = simulate(d11, s11, c11, capital=cap, mode='pooled', collect_trades=True,
                   excl_fn=pm_rule_for(d11, set(ROSTER)))
    rows11, m11 = measure(r11['trades'], bars)
    report('ELEVEN (nine + RTX + DE), PM on the nine only', rows11, cap, out)
    print(f'\n  ({m11} fills dropped: entry date not in the 5-minute archive)')

    b9 = out['NINE, live config']['book']
    b11 = out['ELEVEN (nine + RTX + DE), PM on the nine only']['book']
    print(f'\n  DILUTION: adding two names moves the book\'s median first-hour '
          f'participation {b9["hour1"]["median"]*100:.2f}% -> {b11["hour1"]["median"]*100:.2f}%'
          f', p95 {b9["hour1"]["p95"]*100:.1f}% -> {b11["hour1"]["p95"]*100:.1f}%')

    json.dump(out, open(OUT, 'w'), indent=1, default=str)
    print(f'\nwrote {OUT}\nDONE', flush=True)


if __name__ == '__main__':
    main()
