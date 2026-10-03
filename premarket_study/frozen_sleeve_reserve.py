"""
frozen_sleeve_reserve.py — the user's "second Today's orders" costed properly
(3 Oct 2026).

frozen_sleeve_diag.py sized the GROSS prize: the model's own bid is touched
~660 times a year on days when both of a name's sleeves are occupied, and
those entries look like ordinary book trades (median +2.64%, both halves
positive). That is not the number the proposal turns on.

The pool is fully allocated every morning -- on 2 Oct the whole $2.57m of
available cash went to six free sleeves at $429k each, with nothing left
over. So a second orders list cannot be funded out of air; it is funded by a
CARVE-OUT, and the question is whether the carved-out dollar earns more in
the second list than it earns in the first. That is the 3.27 lesson applied
in reverse: there, freed capital redeployed at the pool's MARGINAL return,
not its average; here, carved-out capital forfeits the marginal return to
chase the re-entry.

So this measures return on the RESERVED capital, counting every idle day --
the same yardstick dip_reserve.py used, and the only one that is honest
about a rule whose capital sits waiting for a trigger.

RULES TESTED (all strictly ex ante, deployed parameters, no fitting):
  per-name   one extra position at a time in each name, own carve-out
  shared     ONE extra position at a time across the whole book, one pot
             (the realistic shape of a second orders list)
  shared-N   as above with N concurrent slots

Entry: a frozen session whose low reaches a sleeve's bid. If both bids are
touched the SHALLOWER (higher) one is taken -- it is the one the tape reaches
first, and it is the worse price, so the bound stays conservative.
Exit: that sleeve's own target (bid + prev close x premium), else the open
after the 50-day stop. A position opened on day i cannot exit before i+1;
the 5-minute archive is still lost, so same-day round trips stay unverified
and uncounted (HANDOVER 3.28d).

Benchmarks it must beat: the pooled book earns ~0.306%/dollar-day (3.27) and
~72.4%/yr sheet convention on the current roster (3.28).

Usage: python frozen_sleeve_reserve.py <workbook.xlsx>
"""
import datetime as dt
import json
import statistics
import sys

import openpyxl

import frozen_sleeve_diag as diag

OUT = 'frozen_sleeve_reserve.json'
SPLIT = diag.SPLIT
INTEREST = 0.0314
BOOK_DOLLAR_DAY = 0.00306            # 3.27, the pooled book's average yield
STOP_DAYS = diag.STOP_DAYS


def candidates(rows, prem, same_day=False):
    """Every frozen session whose low reaches a bid, with the resulting trade.
    Returned in date order; the shallower touched bid wins the session."""
    out = []
    frozen = [bool(r['hold']['bayes']) and bool(r['hold']['ou']) for r in rows]
    for i in range(1, len(rows)):
        if not frozen[i]:
            continue
        best = None
        for s in ('bayes', 'ou'):
            bid = rows[i]['bid'][s]
            if isinstance(bid, (int, float)) and bid > 0 and rows[i]['L'] <= bid:
                if best is None or bid > best[1]:
                    best = (s, bid)
        if best is None:
            continue
        s, bid = best
        t = diag.trade_from(rows, i, bid, prem[s], same_day=same_day)
        if t:
            out.append(dict(i=i, date=rows[i]['date'], sleeve=s, bid=bid,
                            exit_i=i + t['hold'], ret=t['ret'], hold=t['hold'],
                            stop=t['stop']))
    return out


def run_slots(cands, n_sessions, slots):
    """Deploy a pot of 1.0 across `slots` concurrent positions, first come
    first served; idle cash earns interest. Returns the equity multiple and
    the trades actually taken."""
    cands = sorted(cands, key=lambda c: c['date'])
    busy = []                                     # exit index per open slot
    taken, skipped = [], 0
    per_slot = 1.0 / slots
    cash, deployed = 1.0, {}
    equity_days = 0.0
    for c in cands:
        busy = [b for b in busy if b > c['i']]
        if len(busy) >= slots:
            skipped += 1
            continue
        busy.append(c['exit_i'])
        taken.append(c)
    # value the pot: each taken trade compounds its own slot, idle time earns
    # interest. Slots are independent so the pot is their average.
    slot_books = [[] for _ in range(slots)]
    busy = []
    for c in taken:
        free = [k for k in range(slots)
                if not slot_books[k] or slot_books[k][-1]['exit_i'] <= c['i']]
        if free:
            slot_books[free[0]].append(c)
    mult = []
    for book in slot_books:
        m, used = 1.0, 0
        for c in book:
            m *= (1 + c['ret'])
            used += max(c['hold'], 1)
        idle = max(n_sessions - used, 0)
        m *= (1 + INTEREST) ** (idle / 252)
        mult.append(m)
        equity_days += used
    return dict(mult=statistics.fmean(mult), taken=taken, skipped=skipped,
                busy_days=equity_days, occupancy=equity_days / (n_sessions * slots))


def summarise(tag, taken, mult, occ, years, n_sessions, slots):
    if not taken:
        print(f'  {tag:28s} no trades')
        return None
    rets = [t['ret'] for t in taken]
    holds = [max(t['hold'], 1) for t in taken]
    ann = mult ** (1 / years) - 1
    dd_yield = statistics.fmean(r / h for r, h in zip(rets, holds))
    print(f'  {tag:28s} n={len(taken):4d}  ann {ann*100:+6.1f}%  occupancy {occ*100:4.1f}%'
          f'  avg {statistics.fmean(rets)*100:+5.2f}%  med hold {statistics.median(holds):>3.0f}d'
          f'  stops {sum(t["stop"] for t in taken):3d}'
          f'  {dd_yield*100:.3f}%/dollar-day')
    return dict(n=len(taken), ann=ann, occupancy=occ, avg=statistics.fmean(rets),
                med_hold=statistics.median(holds), stops=sum(t['stop'] for t in taken),
                dollar_day=dd_yield)


def main():
    wb = openpyxl.load_workbook(sys.argv[1], data_only=True)
    names = sorted(s[6:] for s in wb.sheetnames if s.startswith('Model '))
    data = {}
    for nm in names:
        rows, prem = diag.read_model(wb, nm)
        data[nm] = (rows, prem, candidates(rows, prem))
    n_sessions = len(data[names[0]][0])
    years = n_sessions / 252

    print(f'{len(names)} names, {n_sessions} sessions ({years:.2f} years), '
          f'conservative fills (no same-day exits)')
    print(f'benchmarks: pooled book ~0.306%/dollar-day, ~72.4%/yr\n')

    # the book's published 72.4%/yr is on the SHEET convention (same-day round
    # trips counted). Measured only on the conservative one, the carve-out is
    # being held to a harsher standard than the thing it is compared with, so
    # both conventions are run and each is compared with its own like.
    print('CONVENTION CHECK — shared pot, 3 slots')
    for lab, sd in (('conservative (no same-day)', False), ('sheet convention', True)):
        ac = []
        for nm in names:
            rows, prem = data[nm][0], data[nm][1]
            ac += [dict(c, name=nm) for c in candidates(rows, prem, same_day=sd)]
        r = run_slots(ac, n_sessions, 3)
        rets = [t['ret'] for t in r['taken']]
        holds = [max(t['hold'], 1) for t in r['taken']]
        agg = sum(rets) / sum(holds)
        print(f'  {lab:28s} n={len(rets):4d}  ann {r["mult"]**(1/years)-1:+6.1%}'
              f'  occupancy {r["occupancy"]*100:4.1f}%  avg {statistics.fmean(rets)*100:+5.2f}%'
              f'  med hold {statistics.median(holds):>3.0f}d'
              f'  aggregate {agg*100:.3f}%/dollar-day')
    print()

    res = {}
    print('PER-NAME CARVE-OUT (one extra position at a time in each name):')
    for nm in names:
        rows, prem, cands = data[nm]
        r = run_slots(cands, n_sessions, 1)
        res[f'per-name {nm}'] = summarise(nm, r['taken'], r['mult'], r['occupancy'],
                                          years, n_sessions, 1)

    allc = []
    for nm in names:
        allc += [dict(c, name=nm) for c in data[nm][2]]
    print(f'\nSHARED CARVE-OUT (one pot, N concurrent slots across all nine):')
    for slots in (1, 2, 3, 5, 9):
        r = run_slots(allc, n_sessions, slots)
        res[f'shared-{slots}'] = summarise(f'{slots} slot(s)', r['taken'], r['mult'],
                                           r['occupancy'], years, n_sessions, slots)
        if res[f'shared-{slots}']:
            res[f'shared-{slots}']['skipped'] = r['skipped']

    print('\nHALVES (shared pot, 3 slots — the middle case):')
    r = run_slots(allc, n_sessions, 3)
    for tag, sel in (('train', lambda t: t['date'] < SPLIT),
                     ('tested', lambda t: t['date'] >= SPLIT)):
        s = [t for t in r['taken'] if sel(t)]
        if s:
            rets = [t['ret'] for t in s]
            holds = [max(t['hold'], 1) for t in s]
            print(f'  {tag:28s} n={len(s):4d}  avg {statistics.fmean(rets)*100:+5.2f}%'
                  f'  med {statistics.median(rets)*100:+5.2f}%'
                  f'  stops {sum(t["stop"] for t in s):3d}'
                  f'  {statistics.fmean(a/b for a,b in zip(rets,holds))*100:.3f}%/dollar-day')
            res[f'shared-3 {tag}'] = dict(n=len(s), avg=statistics.fmean(rets),
                                          dollar_day=statistics.fmean(a/b for a,b in zip(rets,holds)))

    with open(OUT, 'w') as f:
        json.dump(res, f, indent=1, default=str)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
