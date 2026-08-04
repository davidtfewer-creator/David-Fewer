"""
MU: daily hybrid versus weekly Monday tranche, on identical footing.

MU currently earns its place in the daily book. Moving it to the weekly model means giving that
up, so the two have to be compared like for like rather than each against its own conventions.

Held identical: the corrected MU history to 3 August 2026, verified same-day exits against MU's
own 5-minute bars, marked to market with any open position valued at the close, annualised over
the true span, and the same 2025-05-23 half-sample boundary.

The weekly side carries the 12-week maximum hold, since that is the configuration that would
actually be adopted.
"""
import copy, datetime, statistics
from engine import run_model
from newcands import load as load_cand
from mu_rerun import from_workbook
import five_min
five_min.FILES.setdefault('MU', '/root/.claude/uploads/'
                          '2d71f10a-e19f-51b2-8457-2cd547c34dff/94f1080f-MU_5min_Apr2024Aug2026.xlsx')
import weekly_anchor_test as WAT
WAT.data['MU'] = from_workbook()
import weekly_name as WN
WN.DATA['MU'] = WAT.data['MU']
from max_hold_test import run as wrun
from weekly_name import Name

CUT = datetime.date(2025, 5, 23)
DTS, O, H, L, C = WAT.data['MU']
_, _, _, _, _, P0, _ = load_cand('MU')


def daily(bayes):
    chk = five_min.make_checker('MU', DTS, O)[0]
    p = copy.copy(P0); p.bayes_pct = bayes
    p.years = (DTS[-1]-DTS[0]).days/365.25
    r = run_model(DTS, O, H, L, C, p, collect=True, same_day_exit=chk)
    eq = r.frames['equity']
    k = next(i for i, d in enumerate(DTS) if d >= CUT)
    a = lambda lo, hi: (eq[hi]/eq[lo])**(365.25/max((DTS[hi]-DTS[lo]).days, 1))-1
    inv = sum(1 for t in ('t1', 't2') for x in r.frames[t]['AE'] if x == 1)/(2*len(DTS))
    return dict(full=a(0, len(DTS)-1)*100, h1=a(0, k)*100, h2=a(k, len(DTS)-1)*100,
                sharpe=r.sharpe, dd=r.max_drawdown*100,
                trades=r.total_buys/p.years, invested=inv*100)


def weekly(cap, prem, maxwk):
    nm = Name('MU')
    kc = next(i for i, w in enumerate(nm.WS) if nm.DTS[w['idxs'][0]] >= CUT)
    f = wrun(nm, cap, prem, maxwk)
    a = wrun(nm, cap, prem, maxwk, 1, kc-1)
    b = wrun(nm, cap, prem, maxwk, kc, nm.N-1)
    yrs = (nm.DTS[nm.WS[nm.N-1]['idxs'][-1]] - nm.DTS[nm.WS[1]['idxs'][0]]).days/365.25
    h = f['holds']
    invested = sum(h)/((nm.DTS[-1]-nm.DTS[0]).days)
    return dict(full=f['ann']*100, h1=a['ann']*100, h2=b['ann']*100,
                trades=f['trades']/yrs, median=h[len(h)//2], p95=h[int(len(h)*0.95)],
                mx=max(h), invested=invested*100, forced=f['forced'])


if __name__ == '__main__':
    d50, d75 = daily(0.5), daily(0.75)
    w = weekly(0.050, 0.165, 12)
    wnc = weekly(0.050, 0.165, None)
    print('MU — like for like, verified, marked to market, true span\n')
    print(f'{"":26s}{"full sample":>13s}{"1st half":>11s}{"tested half":>13s}'
          f'{"trades/yr":>11s}{"% invested":>12s}')
    print('-'*86)
    for lbl, r in (('daily hybrid, 50/50', d50), ('daily hybrid, 75% Bayes', d75)):
        print(f'{lbl:26s}{r["full"]:>12.1f}%{r["h1"]:>10.1f}%{r["h2"]:>12.1f}%'
              f'{r["trades"]:>11.0f}{r["invested"]:>11.0f}%')
    for lbl, r in (('weekly, 12-week cap', w), ('weekly, uncapped', wnc)):
        print(f'{lbl:26s}{r["full"]:>12.1f}%{r["h1"]:>10.1f}%{r["h2"]:>12.1f}%'
              f'{r["trades"]:>11.0f}{r["invested"]:>11.0f}%')
    print('\ndaily risk    Sharpe {:.2f} / {:.2f}   max drawdown {:.0f}% / {:.0f}%'
          .format(d50['sharpe'], d75['sharpe'], d50['dd'], d75['dd']))
    print(f'weekly holds  median {w["median"]}d   95th {w["p95"]}d   max {w["mx"]}d   '
          f'forced exits {w["forced"]}')
    print(f'\ncapital: the daily model runs two tranches and is invested {d75["invested"]:.0f}% of '
          f'tranche-days;\nthe weekly model runs one and holds stock {w["invested"]:.0f}% of '
          f'calendar days.')
