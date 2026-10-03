"""
frozen_reentry_book.py — the user's "second Today's orders", tested in the
pooled book with verified fills (3 Oct 2026).

HANDOVER 3.30 sized the opportunity from the captive Model sheets and costed a
carve-out standalone; it could not run the test that decides the question
because the 5-minute archive was lost. The archive came back on 3 Oct, so this
is that test.

THE RULE. A sleeve holds one position at a time, so a name whose Bayes and OU
sleeves are both occupied is frozen out of the book however far it falls. The
re-entry sleeve (book_sim `reentry`) is a THIRD sleeve per name, eligible only
on mornings when both base sleeves are held, bidding the shallower of the two
live bids with that sleeve's premium, and claiming its allocation FROM THE
SAME POOL as every other order. That last part is the whole point: on 2 Oct
the live book put all $2.57m into six free sleeves with nothing left over, so
a second list is funded by thinning the first. Measured any other way the
question is not being asked.

Everything else is the live config: 09:00 / 4% pre-market rule both sides,
verified same-day fills from the 5-minute bars, deployed parameters, the
2025-05-23 half-sample split. Grids are read on the train half, frozen, and
scored on the test half; the bar is a both-halves win, as it was for the ten
overlays that failed and the one (3.16) that did not.

Usage: BAYES_WORKBOOK=<workbook.xlsx> python frozen_reentry_book.py
"""
import json
import statistics
import sys

from book_sim import simulate
from baseline_check import load, ROSTER

OUT = 'frozen_reentry_book.json'


def row(tag, r, b=None):
    d = ''
    if b:
        d = (f'  | {(r["full"]-b["full"])*100:+6.1f}{(r["train"]-b["train"])*100:+7.1f}'
             f'{(r["test"]-b["test"])*100:+7.1f}{(r["maxdd"]-b["maxdd"])*100:+7.1f}')
    print(f'  {tag:30s}{r["full"]*100:7.1f}{r["train"]*100:7.1f}{r["test"]*100:7.1f}'
          f'{r["maxdd"]*100:7.1f}{r["fills"]:7d}{r["stops"] or 0:6d}{d}')
    return dict(full=r['full'], train=r['train'], test=r['test'],
                maxdd=r['maxdd'], fills=r['fills'], stops=r['stops'])


def main():
    data, sleeves, cal, pm_rule = load()
    base_kw = dict(excl_fn=pm_rule, collect_trades=True)
    print(f'roster {ROSTER}')
    print(f'{cal[0]} to {cal[-1]} ({len(cal)} sessions), live config '
          f'(09:00 / 4% PM rule), verified fills\n')
    print(f'  {"":30s}{"full":>7s}{"train":>7s}{"test":>7s}{"maxDD":>7s}'
          f'{"fills":>7s}{"stops":>6s}  |  deltas vs baseline')

    res = {}
    b = simulate(data, sleeves, cal, **base_kw)
    res['baseline'] = row('baseline (no re-entry)', b)

    print()
    for slots in (1, 2, 3, None):
        tag = f're-entry, {slots if slots else "no"} slot cap'
        r = simulate(data, sleeves, cal, reentry=dict(slots=slots), **base_kw)
        res[f'slots={slots}'] = row(tag, r, b)

    print()
    for md in (0.02, 0.04, 0.06):
        r = simulate(data, sleeves, cal,
                     reentry=dict(slots=3, max_depth=md), **base_kw)
        res[f'slots=3,depth={md}'] = row(f're-entry, 3 slots, bid <=-{md*100:.0f}%', r, b)

    # the trades the re-entry sleeve actually took, against the book's own
    print()
    r3 = simulate(data, sleeves, cal, reentry=dict(slots=3), **base_kw)
    re_tr = [t for t in r3['trades'] if t['kind'] == 'R']
    bk_tr = [t for t in r3['trades'] if t['kind'] != 'R']
    for tag, tr in (('re-entry trades', re_tr), ('the rest of the book', bk_tr),
                    ('baseline book', b['trades'])):
        if not tr:
            continue
        rets = [t['pnl'] / t['cost'] for t in tr]
        print(f'  {tag:30s} n={len(tr):5d}  avg {statistics.fmean(rets)*100:+6.2f}%'
              f'  med {statistics.median(rets)*100:+6.2f}%'
              f'  stops {sum(t["stopped"] for t in tr):4d}'
              f'  P&L {sum(t["pnl"] for t in tr):>14,.0f}')
        res[f'trades {tag}'] = dict(n=len(tr), avg=statistics.fmean(rets),
                                    med=statistics.median(rets),
                                    stops=sum(t['stopped'] for t in tr),
                                    pnl=sum(t['pnl'] for t in tr))

    with open(OUT, 'w') as f:
        json.dump({k: v for k, v in res.items()}, f, indent=1, default=str)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
