"""
The pooled weekly book.

Every weekly number in this file so far -- NVDA, AVGO, the thirteen candidates,
the RTX/NEM freeze -- is a CAPTIVE result: one name, three tranches, each tranche
owning a third of that name's capital and compounding alone. A real weekly book
does what the daily book does (book_sim.py, HANDOVER 3.9): one pot of cash, and
each Monday the free sleeves divide whatever is not already committed. A sleeve
that is holding, or whose week prices no bid, does not idle its share -- it
thickens everybody else's order.

That matters more on the weekly clock than the daily one, and in the opposite
direction. The weekly model's holding periods are long (RTX 26 days median, NEM
14, and the sample ends with most sleeves still in), so a captive book spends
much of its life with capital parked in sleeves that cannot use it. Pooling
should therefore help more here. Against that, the weekly names fill in the same
weeks as each other when the market dips, so the pool can be claimed all at once
and the uplift is counter-cyclical -- exactly what HANDOVER 3.9 found daily.

Mechanics per week, in order:
  Monday    pool = cash on hand. Each sleeve that is free, active and prices a
            bid this week takes pool/n (equal weights; cap_frac caps one share).
  fills     a sleeve fills if any session low in the week reaches its bid.
            Same-day round trips only where the 5-minute checker proves the low
            preceded the high.
  exits     target hit anywhere in the week -> sold at target. Proceeds land in
            the pool and are usable NEXT Monday, since this Monday's allocations
            are already fixed. max_hold (weeks) adds the 26-week cap of 3.6.
  interest  3.14%/yr on idle cash, accrued at the start of each week on the
            calendar gap between week ends.

Entry, target and fill rules are lifted from weekly_anchor_test.tranche line for
line, including the quirks: a zero-range previous week skips the whole week (no
bid AND no exit scan), the ATH accumulator seeds from each tranche's own start
week, and the same-day verify only applies on the fill day.

VALIDATION: mode='captive' pins each sleeve to its own fixed slice and accrues
interest on its own name's dates, which reproduces Name.seg() exactly. `python3
weekly_book_sim.py --validate` checks that to 0.01pp before any pooled number is
worth reading.

Usage:  python3 weekly_book_sim.py            # the book runs
        python3 weekly_book_sim.py --validate # captive == Name.seg
"""
import json
import math
import statistics
import sys

from minute_index import make_checker
from weekly_anchor_test import group_weeks, wstats
from weekly_mr import P
from weekly_name import DATA, pr

COMM, INTEREST = 0.005, 0.0314
SPLIT_WEEK_DATE = __import__('datetime').date(2025, 5, 23)

# Frozen vectors -- every one a TRAIN-HALF pick, so the whole book sits on one
# protocol and no number below carries lookahead. RTX and NEM are HANDOVER 3.46
# (NEM at 0.070/0.110, the cell its train half picks at four of five cuts, not
# the base cut's 0.065/0.150). AVGO and DE come from the same freeze run and are
# included to be MEASURED, not because they qualify: both post a NEGATIVE edge
# over the no-fit baseline on the half they did not see (AVGO 30.9% against
# 33.0%, train 106.1% -> test 30.9%; DE 20.1% against 22.3%).
VEC = {'RTX': (0.050, 0.070), 'NEM': (0.070, 0.110),
       'AVGO': (0.095, 0.085), 'DE': (0.135, 0.180)}


def _as_date(x):
    return x.date() if hasattr(x, 'date') else x


def load(names):
    """Per-name weekly series on a COMMON week calendar (Monday anchor)."""
    per, keys = {}, None
    for s in names:
        dts, O, H, L, C = DATA[s]
        wk = {}
        for idxs in group_weeks(dts, 0):
            k = (dts[idxs[0]] - __import__('datetime').timedelta(days=0)).isocalendar()[:2]
            wk[k] = wstats(idxs, O, H, L, C)
        per[s] = dict(dts=dts, O=O, H=H, L=L, C=C, wk=wk,
                      chk=make_checker(s, dts, O))
        keys = set(wk) if keys is None else (keys & set(wk))
    order = sorted(keys, key=lambda k: min(_as_date(per[s]['dts'][per[s]['wk'][k]['idxs'][0]])
                                           for s in names))
    for s in names:
        per[s]['WS'] = [per[s]['wk'][k] for k in order]
        dropped = len(per[s]['wk']) - len(order)
        per[s]['dropped'] = dropped
    # one date per global week. `ends` is the latest session end across the book;
    # `starts` the earliest session start. Name.ann measures a range from the FIRST
    # session of w0 to the LAST of w1, so the annualiser below must do the same or
    # it silently inflates every number by a few tenths of a point.
    ends = [max(_as_date(per[s]['dts'][per[s]['WS'][i]['idxs'][-1]]) for s in names)
            for i in range(len(order))]
    starts = [min(_as_date(per[s]['dts'][per[s]['WS'][i]['idxs'][0]]) for s in names)
              for i in range(len(order))]
    return per, len(order), (starts, ends)


def cut_index(per, names, cal):
    for i, d in enumerate(cal[1]):
        if d >= SPLIT_WEEK_DATE:
            return i
    return None


def simulate(names, per, N, cal, params=None, capital=1_000_000, mode='pooled',
             w_lo=1, w_hi=None, n_tranche=3, stag=1, cap_frac=None, max_hold=None):
    """Returns a dict of results. mode 'pooled' | 'captive'."""
    params = params or {s: pr(*VEC[s]) for s in names}
    starts, ends = cal
    w_hi = (N - 1) if w_hi is None else w_hi
    sleeves = []
    for s in names:
        for t in range(n_tranche):
            sleeves.append(dict(name=s, t=t, start=w_lo + t*stag, holding=False,
                                shares=0.0, buy=None, tgt=None, entry_wi=None,
                                ath=None, own=0.0))
    nsl = len(sleeves)
    for sl in sleeves:
        sl['own'] = capital/nsl
    cash = capital if mode == 'pooled' else 0.0
    curve, trades, fills, holds = [], 0, 0, []
    alloc_hist, free_hist = [], []

    for wi in range(w_lo, w_hi + 1):
        # ---- interest
        if mode == 'pooled':
            if wi > w_lo:
                gap = (ends[wi] - ends[wi-1]).days
                cash *= 1 + INTEREST*gap/365.0
        # ---- price every sleeve's week
        live = []
        for sl in sleeves:
            nd = per[sl['name']]
            p = params[sl['name']]
            if wi <= sl['start']:
                sl['_skip'] = True
                continue
            prev, cwk = nd['WS'][wi-1], nd['WS'][wi]
            if sl['ath'] is None:
                sl['ath'] = max(nd['H'][i] for i in nd['WS'][sl['start']]['idxs'])
            sl['ath'] = max(sl['ath'], prev['h'])
            if mode == 'captive' and not sl['holding']:
                dts = nd['dts']
                g = (_as_date(dts[cwk['idxs'][-1]]) - _as_date(dts[prev['idxs'][-1]])).days
                sl['own'] *= 1 + INTEREST*g/365.0
            rng = prev['h'] - prev['l']
            if rng <= 0:                     # tranche() skips the week entirely
                sl['_skip'] = True
                continue
            sl['_skip'] = False
            raw = statistics.mean([p['m']*(prev['h']+prev['l'])/2, prev['c']*p['w']]) \
                + math.log10(rng)*p['g']
            Lp = min(raw, cwk['o'])
            if not sl['holding']:
                sl['buy'] = min(Lp, sl['ath']*(1 - p['cap']))
                sl['tgt'] = sl['buy'] + prev['c']*p['prem']
                live.append(sl)
        # ---- Monday allocation
        if mode == 'pooled':
            n_live = len(live)
            share = cash/n_live if n_live else 0.0
            if cap_frac is not None:
                share = min(share, cash*cap_frac)
            for sl in live:
                sl['_alloc'] = share
            alloc_hist.append(share)
        else:
            for sl in live:
                sl['_alloc'] = sl['own']
        free_hist.append(len(live))
        # ---- fills and exits, sleeve by sleeve
        spent = 0.0
        for sl in sleeves:
            if sl.get('_skip'):
                continue
            nd = per[sl['name']]
            idxs = nd['WS'][wi]['idxs']
            H, L, C = nd['H'], nd['L'], nd['C']
            if not sl['holding']:
                bd = next((k for k, i in enumerate(idxs) if L[i] <= sl['buy']), None)
                if bd is None:
                    continue
                fund = sl['_alloc']
                if fund <= 0:
                    continue
                sl['shares'] = fund/(sl['buy'] + COMM)
                spent += fund
                if mode == 'captive':
                    sl['own'] = 0.0
                sl['holding'] = True
                sl['entry_wi'] = wi
                fills += 1
                for k in range(bd, len(idxs)):
                    i = idxs[k]
                    if H[i] >= sl['tgt']:
                        if k == bd and nd['chk'](i, sl['buy'], sl['tgt']) is False:
                            continue
                        proc = sl['shares']*(sl['tgt'] - COMM)
                        sl['shares'] = 0.0; sl['holding'] = False
                        trades += 1; holds.append(0)
                        if mode == 'pooled':
                            cash += proc
                        else:
                            sl['own'] = proc
                        break
            else:
                for i in idxs:
                    if H[i] >= sl['tgt']:
                        proc = sl['shares']*(sl['tgt'] - COMM)
                        sl['shares'] = 0.0; sl['holding'] = False
                        trades += 1; holds.append(wi - sl['entry_wi'])
                        if mode == 'pooled':
                            cash += proc
                        else:
                            sl['own'] = proc
                        break
            if (max_hold is not None and sl['holding']
                    and wi - sl['entry_wi'] >= max_hold):
                proc = sl['shares']*(C[idxs[-1]] - COMM)
                sl['shares'] = 0.0; sl['holding'] = False
                trades += 1; holds.append(wi - sl['entry_wi'])
                if mode == 'pooled':
                    cash += proc
                else:
                    sl['own'] = proc
        if mode == 'pooled':
            cash -= spent
        # ---- mark
        mv = sum(sl['shares']*per[sl['name']]['C'][per[sl['name']]['WS'][wi]['idxs'][-1]]
                 for sl in sleeves)
        eq = (cash if mode == 'pooled' else sum(s['own'] for s in sleeves)) + mv
        curve.append(eq)

    yrs = (ends[w_hi] - starts[w_lo]).days/365.25
    final = curve[-1]
    mv_end = sum(sl['shares']*per[sl['name']]['C'][per[sl['name']]['WS'][w_hi]['idxs'][-1]]
                 for sl in sleeves)
    peak, dd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        dd = max(dd, 1 - v/peak)
    return dict(mode=mode, names=list(names), weeks=w_hi - w_lo + 1, yrs=yrs,
                ann=((final/capital)**(1/yrs) - 1)*100,
                final=final, trades=trades, fills=fills,
                trades_yr=trades/yrs, maxdd=dd*100,
                open_frac=mv_end/final*100,
                ann_mark20=(((final - mv_end*0.20)/capital)**(1/yrs) - 1)*100,
                median_hold_wk=(statistics.median(holds) if holds else None),
                still=sum(1 for sl in sleeves if sl['holding']), sleeves=nsl,
                mean_free=(statistics.mean(free_hist) if free_hist else None),
                curve=curve)


def validate():
    """captive, one name at a time, must reproduce Name.seg to 0.01pp."""
    from weekly_name import Name
    print('captive vs Name.seg (the held construction this file must reproduce)', flush=True)
    ok = True
    for s in ('RTX', 'NEM'):
        per, N, cal = load([s])
        c, q = VEC[s]
        r = simulate([s], per, N, cal, mode='captive')
        nm = Name(s)
        assert nm.N == N, f'{s}: week count {nm.N} vs {N}'
        rw, tw = nm.seg(pr(c, q), 1, N-1)
        a = nm.ann(rw, 1, N-1)*100
        d = r['ann'] - a
        dr = (r['final']/1_000_000 - 1) - rw          # total return, no annualiser
        ok &= abs(d) < 0.01 and abs(dr) < 1e-9 and r['trades'] == tw
        print(f'  {s}: sim {r["ann"]:7.3f}% ({r["trades"]} trades)   '
              f'seg {a:7.3f}% ({tw} trades)   diff {d:+.4f}pp  '
              f'total-return diff {dr:+.2e}', flush=True)
    print('VALIDATION', 'PASS' if ok else 'FAIL', flush=True)
    return ok


def row(lbl, r):
    print(f'{lbl:28s}{r["ann"]:>8.1f}%{r["maxdd"]:>8.1f}%{r["trades"]:>8d}'
          f'{r["trades_yr"]:>9.1f}{r["open_frac"]:>8.0f}%{r["ann_mark20"]:>10.1f}%'
          f'{(r["mean_free"] or 0):>8.1f}', flush=True)


def head(title):
    print(f'\n{"="*86}\n{title}', flush=True)
    print(f'{"book":28s}{"ann":>9s}{"maxDD":>8s}{"trades":>8s}{"/yr":>9s}'
          f'{"open":>8s}{"mark-20%":>10s}{"free/wk":>8s}', flush=True)


def run():
    out = {}
    books = [('RTX', ['RTX']), ('NEM', ['NEM']),
             ('RTX+NEM', ['RTX', 'NEM']),
             ('RTX+NEM+DE', ['RTX', 'NEM', 'DE']),
             ('RTX+NEM+AVGO', ['RTX', 'NEM', 'AVGO']),
             ('RTX+NEM+AVGO+DE', ['RTX', 'NEM', 'AVGO', 'DE'])]
    for window in ('full', 'test'):
        head(f'{window.upper()} SAMPLE  (pooled above captive for each book)')
        for lbl, nms in books:
            per, N, cal = load(nms)
            lo = 1 if window == 'full' else cut_index(per, nms, cal)
            pl = simulate(nms, per, N, cal, mode='pooled', w_lo=lo)
            cp = simulate(nms, per, N, cal, mode='captive', w_lo=lo)
            row(f'{lbl}  pooled', pl)
            row(f'{lbl}  captive', cp)
            print(f'{"":28s}{"uplift":>8s} {pl["ann"]-cp["ann"]:+.1f}pp', flush=True)
            out[f'{window}:{lbl}'] = {k: v for k, v in
                                      dict(pooled=pl, captive=cp).items()}
            for v in out[f'{window}:{lbl}'].values():
                v.pop('curve', None)
            out[f'{window}:{lbl}']['uplift_pp'] = pl['ann'] - cp['ann']
    # 26-week cap sensitivity on the chosen book
    head('26-WEEK MAXIMUM HOLD (HANDOVER 3.6) on RTX+NEM, full sample')
    per, N, cal = load(['RTX', 'NEM'])
    for mh in (None, 26, 13):
        r = simulate(['RTX', 'NEM'], per, N, cal, mode='pooled', w_lo=1, max_hold=mh)
        row(f'RTX+NEM pooled, cap {mh or "none":>4}', r)
        r.pop('curve', None)
        out[f'maxhold:{mh}'] = r
    # ---- capacity: what capping one sleeve's share of the pool costs
    # The liquidity gate (3.37) binds on the single ORDER, not the book: at most
    # ~1% of a name's median at-bid dollar volume and ~10% on a thin (10th pct)
    # day. From liquidity_check.json that is $2.03m for RTX (the tighter of the
    # two) and $2.89m for NEM. Uncapped pooling lets one sleeve claim the entire
    # free pot, so the book can be no larger than one order. cap_frac fixes the
    # largest share one sleeve may take, and the implied book size is
    # order_cap / cap_frac.
    ORDER_CAP = 2_030_000
    head('CAPACITY: capping one sleeve\'s share of the pool (RTX+NEM, full sample)')
    for cf in (None, 0.5, 1/3, 0.25, 1/6):
        r = simulate(['RTX', 'NEM'], per, N, cal, mode='pooled', w_lo=1, cap_frac=cf)
        sz = ORDER_CAP/(cf or 1.0)
        row(f'cap_frac {("none" if cf is None else f"{cf:.3f}"):>5} -> ${sz/1e6:.1f}m', r)
        r.pop('curve', None)
        out[f'capfrac:{cf}'] = dict(r, implied_book_usd=sz)
    with open('weekly_book_sim.json', 'w') as f:
        json.dump(out, f, indent=1)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    if '--validate' in sys.argv:
        sys.exit(0 if validate() else 1)
    if not validate():
        print('captive does not reproduce the held construction; pooled numbers withheld')
        sys.exit(1)
    run()
