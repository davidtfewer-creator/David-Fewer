"""
Every daily-book figure restated on the mark-to-market basis.

The engine's annual_return follows the workbook and takes the terminal from the Fund column,
which keeps its pre-purchase value while a tranche is holding. An open position at the end is
therefore counted at cost. Where tranches end holding that overstates by 3-11pp.

Everything here is computed from the equity curve instead -- shares valued at the close whenever
a tranche holds -- and annualised over each series' true span rather than the workbook's fixed
2.2 years. MU uses the corrected and extended history to 3 August 2026.

The two weekly names already used this basis: their runner returns fund + shares*close.
"""
import copy, datetime, statistics
from daily_window_split import data, params
from engine import run_model
from five_min import make_checker as fm
from mu_rerun import from_workbook
import five_min

CUT = datetime.date(2025, 5, 23)
DAILY = ['RKLB', 'TSM', 'VST', 'VRT', 'MU']

_mu = from_workbook()
data['MU'] = _mu                                   # corrected + extended


def curve(s, bayes):
    dts, O, H, L, C = data[s]
    chk = fm(s, dts, O)[0]
    p = copy.copy(params[s]); p.bayes_pct = bayes
    p.years = (dts[-1] - dts[0]).days/365.25
    r = run_model(dts, O, H, L, C, p, collect=True, same_day_exit=chk)
    return dts, r.frames['equity'], r


def ann(eq, dts, lo, hi):
    y = (dts[hi] - dts[lo]).days/365.25
    return (eq[hi]/eq[lo])**(1/y) - 1 if eq[lo] > 0 else float('nan')


if __name__ == '__main__':
    print('DAILY BOOK — mark to market, verified fills, true span\n')
    print(f'{"stock":7s}{"50/50":>8s}{"75%B":>8s}{"engine":>9s}{"1st half":>11s}'
          f'{"tested":>9s}{"Sharpe":>8s}{"maxDD":>7s}{"buys/yr":>9s}{"stops":>7s}{"plan":>7s}')
    print('-'*90)
    rows = {}
    for s in DAILY:
        dts, e5, r5 = curve(s, 0.5)
        _, e7, r7 = curve(s, 0.75)
        k = next(i for i, d in enumerate(dts) if d >= CUT)
        span = (dts[-1]-dts[0]).days/365.25
        a5 = ann(e5, dts, 0, len(dts)-1)*100
        a7 = ann(e7, dts, 0, len(dts)-1)*100
        h1 = ann(e7, dts, 0, k)*100
        h2 = ann(e7, dts, k, len(dts)-1)*100
        plan = a5 + 2                              # walk-forward-validated tilt gain
        rows[s] = dict(a5=a5, a7=a7, eng=r7.annual_return*100, h1=h1, h2=h2,
                       sh=r7.sharpe, dd=r7.max_drawdown*100, buys=r7.total_buys/span,
                       stops=r7.stop_loss_exits, plan=plan)
        d = rows[s]
        print(f'{s:7s}{a5:>7.0f}%{a7:>7.0f}%{d["eng"]:>8.0f}%{h1:>10.0f}%{h2:>8.0f}%'
              f'{d["sh"]:>8.2f}{d["dd"]:>6.0f}%{d["buys"]:>9.0f}{d["stops"]:>7d}{plan:>6.0f}%')
    print('-'*90)
    print(f'{"mean":7s}{statistics.mean(r["a5"] for r in rows.values()):>7.0f}%'
          f'{statistics.mean(r["a7"] for r in rows.values()):>7.0f}%'
          f'{statistics.mean(r["eng"] for r in rows.values()):>8.0f}%'
          f'{"":>10s}{"":>8s}{"":>8s}{"":>6s}{"":>9s}{"":>7s}'
          f'{statistics.mean(r["plan"] for r in rows.values()):>6.0f}%')

    WEEK = {'NVDA': dict(a=82.0, h1=44.2, h2=81.8, plan=58, nb=58.6, q=45.4),
            'AVGO': dict(a=90.7, h1=72.2, h2=96.4, plan=60, nb=64.8, q=57.5)}
    print('\nWEEKLY NAMES — single Monday tranche, already marked to market')
    print(f'{"stock":7s}{"full":>8s}{"1st half":>11s}{"tested":>9s}{"nbhd med":>11s}'
          f'{"25th":>7s}{"plan":>7s}')
    for s, w in WEEK.items():
        print(f'{s:7s}{w["a"]:>7.1f}%{w["h1"]:>10.1f}%{w["h2"]:>8.1f}%{w["nb"]:>10.1f}%'
              f'{w["q"]:>6.1f}%{w["plan"]:>6.0f}%')

    allplan = [rows[s]['plan'] for s in DAILY] + [w['plan'] for w in WEEK.values()]
    allver = [rows[s]['a7'] for s in DAILY] + [w['a'] for w in WEEK.values()]
    print(f'\nSEVEN-NAME BOOK, equal weight')
    print(f'  verified (m2m) {statistics.mean(allver):.0f}%   planning '
          f'{statistics.mean(allplan):.0f}%')
    print(f'  ex-RKLB        {statistics.mean(allver[1:]):.0f}%   planning '
          f'{statistics.mean(allplan[1:]):.0f}%')
