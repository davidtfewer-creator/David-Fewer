"""
The candidate screen, with a turnover gate (G4).

Every candidate programme in this file -- §3.14, §3.32, §3.38-3.45 -- judged
names on RETURN and on AI CORRELATION. §3.33 used turnover once, as an aside,
and measured it against the wrong yardstick: LEN was declined partly for being
"slower than the 24/yr CF it would replace". §3.49 showed CF is itself three
times slower than the book it sits in, so beating CF is not a bar worth clearing.

The bar is the BOOK. Measured at deployed parameters (book_turnover.py), the live
five trade 56-92 fills a year each, hold for a MEDIAN OF ONE DAY, and close 70-81%
of positions within five calendar days. That profile is the trading character of
the entity, and it is what a complementary book has to preserve.

G4 (new): on the frozen train-half vector,
    fills/yr >= 50   AND   median hold <= 3 days   AND   >= 70% closed within 5 days.
Gated on the TEST half (honest but thin -- a year and a bit, often 10-40 fills);
the full-sample figures are printed alongside as the better-estimated view, and
any name where the two disagree is flagged rather than decided.

Running order, cheapest first: G0 data, G1 correlation (no fit needed), then one
differential-evolution fit per name on the train half, which buys G2 (does the
frozen vector beat not fitting on the unseen half?) and G4 together.

The harness is two_day.Clock at n=1 -- literally the daily model, and the same
code that produced §3.49's control, so every figure here is comparable to it.

Usage:  python3 screen_speed.py              # the whole 5-minute universe
        python3 screen_speed.py NEM RTX DE   # named candidates only
"""
import json
import os
import sys

import numpy as np

from baseline_check import load as load_book_cal
from fresh_opt_cands import daily_from_5min
from g1_screen import rets_on
from two_day import Clock, FILLS_PER_YEAR_FLOOR, x0_vector

BOOK = ('TSM', 'VRT', 'VST', 'AVGO', 'MU')
AI = ('TSM', 'VRT', 'VST', 'AVGO', 'MU', 'MRVL')
# the book's own profile, from book_turnover.py
G4_FILLS_YR, G4_MED_D, G4_WITHIN5 = 50.0, 3, 70.0


def universe():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_5min')
    names = sorted(f[:-10] for f in os.listdir(here) if f.endswith('_5min.xlsx'))
    return [n for n in names if n not in BOOK]


def g1_factors():
    """AI factor and book-average return series on the book's calendar."""
    data, _sl, cal, _pm = load_book_cal()
    R = {}
    for nm in sorted(data):
        d = data[nm]
        C = [d['C'][d['idx'][x]] for x in cal]
        R[nm] = np.array([np.nan] + [C[i]/C[i-1] - 1 for i in range(1, len(C))])
    ai = [R[n] for n in AI if n in R]
    factor = np.nanmean(np.vstack(ai), axis=0)
    bookavg = np.nanmean(np.vstack([R[n] for n in sorted(R)]), axis=0)
    return cal, factor, bookavg


def g1(nm, cal, factor, bookavg):
    dts, O, H, L, C = daily_from_5min(nm)
    r = rets_on(cal, dts, C)
    m = ~(np.isnan(factor) | np.isnan(r))
    beta = float(np.polyfit(factor[m], r[m], 1)[0])
    mb = ~(np.isnan(bookavg) | np.isnan(r))
    cb = float(np.corrcoef(bookavg[mb], r[mb])[0, 1])
    cls = ('uncorrelated' if beta < 0.20 else
           'AI-related' if beta >= 0.27 else 'BORDERLINE')
    return beta, cb, cls


def turnover(hd, yrs):
    if not hd:
        return 0.0, None, 0.0
    hd = sorted(hd)
    return len(hd)/yrs, hd[len(hd)//2], sum(1 for h in hd if h <= 5)/len(hd)*100


def screen(names=None):
    cal, factor, bookavg = g1_factors()
    names = names or universe()
    rows = []
    for nm in names:
        try:
            c = Clock(nm, 1, 0)
        except Exception as e:                               # noqa: BLE001
            print(f'{nm}: G0 FAIL — {e}', flush=True)
            continue
        beta, cb, cls = g1(nm, cal, factor, bookavg)
        y_tr = (c.D[c.cut-1] - c.D[0]).days/365.25
        y_te = (c.D[c.N-1] - c.D[c.cut]).days/365.25
        f_tr = max(4, int(FILLS_PER_YEAR_FLOOR*y_tr))
        rt0, _ = c.seg(x0_vector(1), c.cut, c.N-1)
        a_no = c.ann(rt0, c.cut, c.N-1)

        v = c.fit(0, c.cut-1, f_tr, seed=42)
        r_te, b_te = c.seg(v, c.cut, c.N-1)
        a_te = c.ann(r_te, c.cut, c.N-1)
        hd_all, _hs, stops = c.holds(v)
        # split the holding record into the two halves by entry bar
        fr = c.run(v).frames
        hd_te = []
        for key in ('t1', 't2'):
            t = fr[key]
            e = None
            for i in range(c.N):
                if t['Z'][i] == 1:
                    e = i
                if t['AD'][i] == 1 and e is not None:
                    if e >= c.cut:
                        hd_te.append((c.D[i] - c.D[e]).days)
                    e = None
        fy_te, md_te, w5_te = turnover(hd_te, y_te)
        fy_fu, md_fu, w5_fu = turnover(hd_all, c.yrs)

        g2 = a_te > a_no
        g4 = (fy_te >= G4_FILLS_YR and md_te is not None
              and md_te <= G4_MED_D and w5_te >= G4_WITHIN5)
        g4_fu = (fy_fu >= G4_FILLS_YR and md_fu is not None
                 and md_fu <= G4_MED_D and w5_fu >= G4_WITHIN5)
        rows.append(dict(name=nm, beta=float(beta), corr_book=float(cb), g1=cls,
                         nofit_test=a_no, frozen_test=a_te, edge=a_te - a_no, g2=bool(g2),
                         fills_yr_test=fy_te, med_test=md_te, within5_test=w5_te, g4=bool(g4),
                         fills_yr_full=fy_fu, med_full=md_fu, within5_full=w5_fu,
                         g4_full=bool(g4_fu), disagree=bool(g4 != g4_fu),
                         test_fills=int(b_te), stops=int(stops), vec=[float(x) for x in v], bound=c.on_bound(v),
                         sessions=c.sessions))
        r = rows[-1]
        with open('screen_speed.json', 'w') as f:
            json.dump(rows, f, indent=1)
        print(f'{nm:6s} beta {beta:+.2f} {cls:13s} | G2 {"pass" if g2 else "FAIL"} '
              f'({a_te:6.1f}% vs {a_no:6.1f}% no-fit) | G4 {"pass" if g4 else "FAIL"} '
              f'({fy_te:5.1f}/yr, med {md_te}d, {w5_te:3.0f}% <=5d)'
              f'{"  [halves disagree]" if r["disagree"] else ""}', flush=True)
    return rows


def report(rows):
    print(f'\n{"="*104}\nSCREEN WITH THE TURNOVER GATE')
    print(f'  G1 AI beta <0.20 uncorrelated / >=0.27 AI-related')
    print(f'  G2 frozen train-half vector beats the no-fit baseline on the unseen half')
    print(f'  G4 the book\'s own profile: >={G4_FILLS_YR:.0f} fills/yr, median hold '
          f'<={G4_MED_D}d, >={G4_WITHIN5:.0f}% closed within 5 days\n')
    print(f'{"name":6s}{"beta":>7s}{"class":>14s}{"no-fit":>9s}{"frozen":>9s}{"G2":>5s}'
          f'{"fills/yr":>10s}{"med":>6s}{"<=5d":>7s}{"G4":>5s}   verdict')
    rows = sorted(rows, key=lambda r: (-(r['g1'] != 'AI-related'), -r['g4'], -r['frozen_test']))
    for r in rows:
        v = ('PASS' if (r['g2'] and r['g4'] and r['g1'] != 'AI-related') else
             'fails G4 (too slow)' if (r['g2'] and r['g1'] != 'AI-related') else
             'fails G2' if r['g1'] != 'AI-related' else 'G1 AI-related')
        print(f'{r["name"]:6s}{r["beta"]:>7.2f}{r["g1"]:>14s}{r["nofit_test"]:>8.1f}%'
              f'{r["frozen_test"]:>8.1f}%{("Y" if r["g2"] else "n"):>5s}'
              f'{r["fills_yr_test"]:>10.1f}{(r["med_test"] if r["med_test"] is not None else -1):>5d}d'
              f'{r["within5_test"]:>6.0f}%{("Y" if r["g4"] else "n"):>5s}   {v}')
    npass = sum(1 for r in rows if r['g2'] and r['g4'] and r['g1'] != 'AI-related')
    slow = sum(1 for r in rows if r['g2'] and not r['g4'] and r['g1'] != 'AI-related')
    print(f'\n  {npass} pass all three; {slow} clear G1 and G2 but FAIL ONLY ON SPEED.')


if __name__ == '__main__':
    names = [a for a in sys.argv[1:] if not a.startswith('--')] or None
    rows = screen(names)
    report(rows)
    with open('screen_speed.json', 'w') as f:
        json.dump(rows, f, indent=1)
    print('\nDONE', flush=True)
