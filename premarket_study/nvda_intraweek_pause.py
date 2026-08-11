"""
NVDA intra-week pause split. All nine in-sample NVDA reports are Wednesdays after
the close, so the report week divides into Mon-Wed (pre-report, includes report
day -- the report lands after that session's close) and Thu-Fri (post-report).
Diagnostic splits the week-of entries by side; interventions pause each side
separately, with the full-week P1 as reference. Basis identical to
earnings_pause.py (deployed NVDA vector, residual sigma, verified fills).

Result (10 Aug 2026): the damage is all Thursday/Friday after the report --
entries there averaged -0.82% with a 14% stop rate and 28-day holds, while
Mon-Wed entries earned +2.43% with none. Pausing Thu-Fri lifts full-sample
40.0 -> 41.9%/yr and tested-half 46.9 -> 51.2%; pausing Mon-Wed costs return.
The earlier 'week-of wash' was these two halves cancelling.
"""
import datetime
import numpy as np
from engine import run_model
from earnings_pause import EARNINGS, load_params, trades_from_frames, week_span
from fresh_opt_cands import daily_from_5min
from fresh_opt import SPLIT, annualise
from minute_index import make_checker


def main(stock='NVDA'):
    dts, O, H, L, C = daily_from_5min(stock)
    chk = make_checker(stock, dts, O)
    p = load_params(stock)
    earnings = [datetime.date.fromisoformat(s) for s in EARNINGS[stock]]
    N = len(C)
    cut = next(i for i, d in enumerate(dts) if d >= SPLIT)
    print('report weekdays:', sorted({e.strftime('%a') for e in earnings}))

    r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk, collect=True)
    fr = r.frames
    trades = (trades_from_frames(dts, fr, 't1', fr['X'])
              + trades_from_frames(dts, fr, 't2', fr['AM']))

    def fine_bucket(d):
        for e in earnings:
            mon, sun = week_span(e)
            if mon <= d <= sun:
                return 'pre' if d <= e else 'post'
        return None

    buck = {}
    for (i, j, bp, xp, st) in trades:
        b = fine_bucket(dts[i])
        if b is None or j is None:
            continue
        d = buck.setdefault(b, dict(ret=[], stops=0, hold=[]))
        d['ret'].append(xp / bp - 1)
        d['stops'] += st
        d['hold'].append((dts[j] - dts[i]).days)
    print('\nweek-of entries split by side of the report:')
    for b, label in [('pre', 'Mon-Wed (pre-report)'), ('post', 'Thu-Fri (post-report)')]:
        d = buck.get(b)
        if not d:
            continue
        rets = np.array(d['ret'])
        print(f'  {label:22s} n={len(rets):2d}  avg {rets.mean()*100:6.2f}%  '
              f'stops {d["stops"]}/{len(rets)}  hold {np.mean(d["hold"]):5.1f}d')

    def span_days(a, b):
        s, d = set(), a
        while d <= b:
            s.add(d)
            d += datetime.timedelta(days=1)
        return s

    pre = set().union(*[span_days(week_span(e)[0], e) for e in earnings])
    post = set().union(*[span_days(e + datetime.timedelta(days=1), week_span(e)[1])
                         for e in earnings])
    print('\ninterventions:')
    for label, days in [('baseline', set()), ('pause Mon-Wed', pre),
                        ('pause Thu-Fri', post), ('pause full week', pre | post)]:
        nb = [d in days for d in dts]
        res = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                        collect=True, no_buy=nb)
        eq = res.frames['equity']
        fa = annualise(eq[N - 1] / eq[0] - 1, dts, 0, N - 1)
        ta = annualise(eq[N - 1] / eq[cut] - 1, dts, cut, N - 1)
        print(f'  {label:18s} full {fa*100:5.1f}%  test {ta*100:5.1f}%  '
              f'buys {res.total_buys}  stops {res.stop_loss_exits}  paused {sum(nb)}')


if __name__ == '__main__':
    main()
