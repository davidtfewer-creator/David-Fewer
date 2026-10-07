"""
cf_profile.py — is CF the wrong SHAPE for this model, and what does dropping it
cost? (user, 7 Oct 2026)

User: "CF relies on a small number of high-margin trades to meet its return.
That is the wrong profile -- it lacks predictability. Fast turnover stocks are
a better fit. But CF is a diversifier, so replacing it probably needs another
diversifier."

Three questions, in the order that decides the thing:

  1. SHAPE. Is the claim true? Per name, in the pooled book: trades per year,
     median hold, and how much of the name's P&L rides on its best third of
     trades. 3.27 already found CF the book's lowest yield per invested
     dollar-day (0.186% vs 0.306%); this asks whether the return is also
     CONCENTRATED, which is the predictability claim and a different one.
  2. COST. What does the book actually lose by dropping CF? Pooled, live
     config, both halves, drawdown -- and the stress windows, because CF is
     carried for its correlation, not its return.
  3. BAR. What would a replacement have to clear to be worth admitting?
     Stated as a number, not a sentiment.

Everything is measured on the restored archive with verified fills, deployed
parameters, the 2025-05-23 split, and the same pre-market cache on both sides
so the A/B is clean (levels carry the 3.30b calibration caveat; deltas do not).

Usage: BAYES_WORKBOOK=<workbook.xlsx> python cf_profile.py
"""
import json
import statistics

import numpy as np

from book_sim import simulate
from baseline_check import load, ROSTER

OUT = 'cf_profile.json'
SPLIT = __import__('datetime').date(2025, 5, 23)


def top_third_share(pnls):
    pos = sorted(pnls, reverse=True)
    tot = sum(pos)
    if tot <= 0 or len(pos) < 3:
        return None
    k = max(1, round(len(pos) / 3))
    return sum(pos[:k]) / tot


def shape(trades, years):
    by = {}
    for t in trades:
        by.setdefault(t['name'], []).append(t)
    out = {}
    for nm, ts in by.items():
        rets = [t['pnl'] / t['cost'] for t in ts]
        holds = [max((t['exit'] - t['entry']).days, 1) for t in ts]
        out[nm] = dict(
            n=len(ts), per_yr=len(ts) / years,
            pnl=sum(t['pnl'] for t in ts),
            avg=statistics.fmean(rets), med=statistics.median(rets),
            med_hold=statistics.median(holds),
            stops=sum(t['stopped'] for t in ts),
            losers=sum(1 for r in rets if r < 0),
            dollar_day=(sum(t['pnl'] for t in ts)
                        / sum(t['cost'] * max((t['exit'] - t['entry']).days, 1) for t in ts)),
            top3=top_third_share([t['pnl'] for t in ts]),
            capital_days=sum(t['cost'] * max((t['exit'] - t['entry']).days, 1) for t in ts))
    return out


def main():
    data, sleeves, cal, pm_rule = load()
    years = len(cal) / 252
    kw = dict(excl_fn=pm_rule, collect_trades=True)
    base = simulate(data, sleeves, cal, **kw)
    sh = shape(base['trades'], years)

    print(f'pooled book, live config, {cal[0]} to {cal[-1]} ({years:.2f} years)\n')
    print('1. SHAPE — is CF a few big trades?\n')
    print(f'  {"name":6s}{"/yr":>6s}{"avg":>8s}{"med":>8s}{"hold":>6s}{"stops":>7s}'
          f'{"lose%":>7s}{"%/$-day":>9s}{"top 3rd":>9s}{"P&L share":>11s}')
    tot_pnl = sum(v['pnl'] for v in sh.values())
    for nm in sorted(sh, key=lambda n: -sh[n]['per_yr']):
        v = sh[nm]
        print(f'  {nm:6s}{v["per_yr"]:>6.0f}{v["avg"]*100:>+7.2f}%{v["med"]*100:>+7.2f}%'
              f'{v["med_hold"]:>6.0f}{v["stops"]:>7d}{v["losers"]/v["n"]*100:>6.0f}%'
              f'{v["dollar_day"]*100:>8.3f}%{(v["top3"] or 0)*100:>8.0f}%'
              f'{v["pnl"]/tot_pnl*100:>10.1f}%')

    print('\n  the two shape measures, ranked (low is good for both):')
    rank_dd = sorted(sh, key=lambda n: sh[n]['dollar_day'])
    rank_t3 = sorted(sh, key=lambda n: -(sh[n]['top3'] or 0))
    print(f'    worst yield per invested dollar-day : {", ".join(rank_dd[:3])}')
    print(f'    most concentrated P&L (top third)   : {", ".join(rank_t3[:3])}')

    print('\n2. COST — what the book loses by dropping CF\n')
    print(f'  {"":26s}{"full":>7s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"fills":>7s}')
    res = {'baseline': dict(full=base['full'], train=base['train'], test=base['test'],
                            maxdd=base['maxdd'], fills=base['fills'])}
    print(f'  {"nine names":26s}{base["full"]*100:>7.1f}{base["train"]*100:>7.1f}'
          f'{base["test"]*100:>7.1f}{base["maxdd"]*100:>7.1f}{base["fills"]:>7d}')
    for drop in ('CF', 'VLO', 'GM'):
        keep = [s for s in sleeves if s['name'] != drop]
        r = simulate(data, keep, cal, **kw)
        res[f'drop {drop}'] = dict(full=r['full'], train=r['train'], test=r['test'],
                                   maxdd=r['maxdd'], fills=r['fills'])
        print(f'  {"without " + drop:26s}{r["full"]*100:>7.1f}{r["train"]*100:>7.1f}'
              f'{r["test"]*100:>7.1f}{r["maxdd"]*100:>7.1f}{r["fills"]:>7d}'
              f'   | {(r["full"]-base["full"])*100:+5.1f}'
              f'{(r["train"]-base["train"])*100:+6.1f}{(r["test"]-base["test"])*100:+6.1f}'
              f'{(r["maxdd"]-base["maxdd"])*100:+6.1f}')

    print('\n  stress windows (pooled, the reason the diversifiers are carried):')
    import datetime as dt
    WINDOWS = [('Jan-Apr 2025 AI drawdown', dt.date(2025, 1, 1), dt.date(2025, 4, 30)),
               ('Feb-Jun 2025 episode', dt.date(2025, 2, 1), dt.date(2025, 6, 30)),
               ('Jun-Jul 2026', dt.date(2026, 6, 1), dt.date(2026, 7, 31))]
    print(f'  {"":26s}' + ''.join(f'{w[0][:20]:>22s}' for w in WINDOWS))
    for tag, keep in (('nine names', sleeves),
                      ('without CF', [s for s in sleeves if s['name'] != 'CF'])):
        cells = []
        for _, lo, hi in WINDOWS:
            r = simulate(data, keep, cal, date_lo=lo, date_hi=hi, **kw)
            cells.append(f'{r["full"]*100:+9.1f}% DD{r["maxdd"]*100:5.1f}')
        print(f'  {tag:26s}' + ''.join(f'{c:>22s}' for c in cells))

    print('\n3. BAR — what a replacement has to clear\n')
    cf = sh['CF']
    print(f'  CF today: {cf["per_yr"]:.0f} trades/yr, median hold {cf["med_hold"]:.0f}d, '
          f'{cf["dollar_day"]*100:.3f}%/dollar-day, {cf["pnl"]/tot_pnl*100:.1f}% of book P&L,')
    print(f'            {cf["capital_days"]/sum(v["capital_days"] for v in sh.values())*100:.1f}% '
          f'of the book\'s invested capital-days.')
    d = res['drop CF']
    print(f'  Dropping it moves the book {(d["full"]-base["full"])*100:+.1f} full / '
          f'{(d["train"]-base["train"])*100:+.1f} train / {(d["test"]-base["test"])*100:+.1f} test, '
          f'maxDD {(d["maxdd"]-base["maxdd"])*100:+.1f}pp.')

    with open(OUT, 'w') as f:
        json.dump(dict(shape=sh, book=res), f, indent=1, default=str)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
