"""
cf_swap_test.py — can LEN or NEM take CF's slot? (user, 7 Oct 2026)

3.32 established what CF is: the book's only zero-beta name, and the price of
that is the worst profile in the book (24 trades/yr, 12-day holds, best third
of trades carrying 102% of P&L). It also set the bar for a replacement, in
numbers rather than sentiment:

    book correlation <= 0.3,  >= 50 trades/yr,  top-third share < 80%

and noted that turnover follows the FITTED PREMIUM, not the price series, so a
candidate has to be fitted and the profile read off the fit.

This reads the fitted vectors from fresh_opt_cands.json (produced by
`python fresh_opt_cands.py LEN NEM`, the same 3.14 path) and runs the two
tests that decide it:

  PROFILE  per-name shape in the pooled book, against the bar above and
           against CF's own numbers.
  G5       the marginal book test: swap CF out for the candidate, and
           separately add the candidate as a tenth name. Pooled, live config,
           both halves, drawdown and the stress windows -- because CF is
           carried for its correlation, not its return.

A candidate is only interesting if it clears the profile bar AND the swapped
book beats the nine-name book on BOTH halves without giving up drawdown.

Usage: BAYES_WORKBOOK=<workbook.xlsx> python cf_swap_test.py [LEN NEM]
"""
import datetime as dt
import json
import statistics
import sys

from engine import Params
from fresh_opt_cands import aw_params
from book_sim import load_all, simulate, NAMES as N8
from baseline_check import ROSTER

OUT = 'cf_swap_test.json'
SPLIT = dt.date(2025, 5, 23)
BAR = dict(corr=0.30, per_yr=50, top3=0.80)
WINDOWS = [('Jan-Apr 2025 AI drawdown', dt.date(2025, 1, 1), dt.date(2025, 4, 30)),
           ('Feb-Jun 2025 episode', dt.date(2025, 2, 1), dt.date(2025, 6, 30)),
           ('Jun-Jul 2026', dt.date(2026, 6, 1), dt.date(2026, 7, 31))]


def t0():
    return Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                  bayes_pct=0.5, years=2.2, ou_W=80)


def overrides(cands):
    c = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(c['MRVL']['reference']['vec'], t0()),
          'AVGO': aw_params(c['AVGO']['reference']['vec'], t0())}
    for s in cands:
        if s not in c or 'vec' not in c[s].get('reference', {}):
            raise SystemExit(f'{s}: no fitted reference in fresh_opt_cands.json — '
                             f'run `python fresh_opt_cands.py {s}` first')
        po[s] = aw_params(c[s]['reference']['vec'], t0())
    return po, c


def shape_of(trades, nm, years):
    ts = [t for t in trades if t['name'] == nm]
    if not ts:
        return None
    rets = [t['pnl'] / t['cost'] for t in ts]
    holds = [max((t['exit'] - t['entry']).days, 1) for t in ts]
    pos = sorted((t['pnl'] for t in ts), reverse=True)
    tot = sum(pos)
    k = max(1, round(len(pos) / 3))
    return dict(n=len(ts), per_yr=len(ts) / years, avg=statistics.fmean(rets),
                med_hold=statistics.median(holds), stops=sum(t['stopped'] for t in ts),
                losers=sum(1 for r in rets if r < 0) / len(ts),
                top3=(sum(pos[:k]) / tot) if tot > 0 else None,
                dollar_day=(sum(t['pnl'] for t in ts)
                            / sum(t['cost'] * max((t['exit'] - t['entry']).days, 1)
                                  for t in ts)),
                pnl=sum(t['pnl'] for t in ts))


def pm_rule_for(data, cut='09:00', thr=0.04):
    import pickle
    pm = pickle.load(open('data_pm/pm_last_cuts.pkl', 'rb'))[cut]

    def f(name, i, bid):
        p = pm.get(name, {}).get(data[name]['dts'][i])
        return p is not None and bid < p * (1 - thr)
    return f


def line(tag, r, b=None):
    d = ''
    if b:
        d = (f'   | {(r["full"]-b["full"])*100:+5.1f}{(r["train"]-b["train"])*100:+6.1f}'
             f'{(r["test"]-b["test"])*100:+6.1f}{(r["maxdd"]-b["maxdd"])*100:+6.1f}')
    print(f'  {tag:26s}{r["full"]*100:>7.1f}{r["train"]*100:>7.1f}{r["test"]*100:>7.1f}'
          f'{r["maxdd"]*100:>7.1f}{r["fills"]:>7d}{d}')
    return dict(full=r['full'], train=r['train'], test=r['test'],
                maxdd=r['maxdd'], fills=r['fills'])


def main():
    cands = sys.argv[1:] or ['LEN', 'NEM']
    po, raw = overrides(cands)
    res = {'candidates': {}}

    for s in cands:
        r = raw[s]
        print(f'{s}: fitted (3.14 path)')
        for k in ('reference', 'A', 'B'):
            v = r.get(k, {})
            if 'test' in v:
                print(f'    {k:10s} full {v.get("full", float("nan"))*100 if "full" in v else float("nan"):6.1f}'
                      f'  train {v["train"]*100:6.1f}  TEST {v["test"]*100:6.1f}')
        res['candidates'][s] = r
    print()

    # ---- the nine-name baseline, then each swap and each addition -----------
    data, sleeves, cal = load_all(names=ROSTER, params_override=po)
    years = len(cal) / 252
    kw = dict(excl_fn=pm_rule_for(data), collect_trades=True)
    base = simulate(data, sleeves, cal, **kw)
    print(f'pooled book, live config, {cal[0]} to {cal[-1]} ({years:.2f} yrs)\n')
    print(f'  {"":26s}{"full":>7s}{"train":>7s}{"test":>7s}{"maxDD":>7s}{"fills":>7s}'
          f'    | deltas')
    res['nine'] = line('nine names (with CF)', base)
    cf = shape_of(base['trades'], 'CF', years)

    rosters = {}
    for s in cands:
        rosters[f'swap CF -> {s}'] = [n for n in ROSTER if n != 'CF'] + [s]
        rosters[f'add {s} (ten names)'] = ROSTER + [s]
    rosters['drop CF (eight names)'] = [n for n in ROSTER if n != 'CF']

    shapes = {'CF': cf}
    for tag, names in rosters.items():
        d2, s2, c2 = load_all(names=names, params_override=po)
        kw2 = dict(excl_fn=pm_rule_for(d2), collect_trades=True)
        r = simulate(d2, s2, c2, **kw2)
        res[tag] = line(tag, r, base)
        for s in cands:
            if s in names and s not in shapes:
                shapes[s] = shape_of(r['trades'], s, len(c2) / 252)

    # ---- profile against the bar -------------------------------------------
    print(f'\nPROFILE against the 3.32 bar '
          f'(corr<={BAR["corr"]}, >={BAR["per_yr"]}/yr, top third<{BAR["top3"]*100:.0f}%)\n')
    print(f'  {"name":6s}{"/yr":>6s}{"avg":>8s}{"hold":>6s}{"stops":>7s}{"lose%":>7s}'
          f'{"%/$-day":>9s}{"top 3rd":>9s}   verdict')
    for nm, v in shapes.items():
        if not v:
            continue
        passes = (v['per_yr'] >= BAR['per_yr'] and (v['top3'] or 1) < BAR['top3'])
        print(f'  {nm:6s}{v["per_yr"]:>6.0f}{v["avg"]*100:>+7.2f}%{v["med_hold"]:>6.0f}'
              f'{v["stops"]:>7d}{v["losers"]*100:>6.0f}%{v["dollar_day"]*100:>8.3f}%'
              f'{(v["top3"] or 0)*100:>8.0f}%   '
              f'{"clears the shape bar" if passes else "fails the shape bar"}')
        res.setdefault('shapes', {})[nm] = v

    # ---- stress windows ----------------------------------------------------
    print(f'\nSTRESS WINDOWS (the reason a diversifier is carried)\n')
    print(f'  {"":26s}' + ''.join(f'{w[0][:21]:>23s}' for w in WINDOWS))
    for tag, names in [('nine names (with CF)', ROSTER)] + list(rosters.items()):
        d2, s2, c2 = load_all(names=names, params_override=po)
        kw2 = dict(excl_fn=pm_rule_for(d2), collect_trades=True)
        cells = []
        for _, lo, hi in WINDOWS:
            r = simulate(d2, s2, c2, date_lo=lo, date_hi=hi, **kw2)
            cells.append(f'{r["full"]*100:+9.1f}% DD{r["maxdd"]*100:5.1f}')
        print(f'  {tag:26s}' + ''.join(f'{c:>23s}' for c in cells))

    with open(OUT, 'w') as f:
        json.dump(res, f, indent=1, default=str)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
